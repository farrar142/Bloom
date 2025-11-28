"""ASGI 애플리케이션 인터페이스"""

from __future__ import annotations

import asyncio
import json
import signal
from typing import Any, Callable, Coroutine, TYPE_CHECKING
from urllib.parse import parse_qs

from .http import HttpRequest, HttpResponse, StreamingResponse
from .router import Router

if TYPE_CHECKING:
    from .messaging import StompProtocolHandler
    from .static import StaticFilesManager
    from bloom.application import Application

# ASGI 타입 정의
Scope = dict[str, Any]
Receive = Callable[[], Coroutine[Any, Any, dict[str, Any]]]
Send = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class ASGIApplication:
    """
    ASGI 표준 애플리케이션

    HTTP 요청과 WebSocket 연결을 모두 처리.
    멀티 워커 환경에서도 안전하게 동작합니다.

    사용 예시:
        # uvicorn으로 실행
        app = ASGIApplication(router)

        # WebSocket 메시징 활성화
        app = ASGIApplication(router, stomp_handler=stomp_handler)

        # 멀티 워커 실행
        # uvicorn main:app --workers 4

    멀티 워커 지원:
        각 워커 프로세스에서 lifespan.startup 이벤트 시 자동으로
        Application.ready()가 호출되어 DI 컨테이너가 초기화됩니다.
    """

    def __init__(
        self,
        router: Router,
        stomp_handler: "StompProtocolHandler | None" = None,
        websocket_path: str = "/ws",
        application: "Application | None" = None,
    ):
        self.router = router
        self.stomp_handler = stomp_handler
        self.websocket_path = websocket_path
        self.application = application

        # 멀티워커 지원을 위한 상태
        self._active_requests = 0
        self._shutdown_event: asyncio.Event | None = None
        self._is_shutting_down = False

        # 라이프사이클 콜백
        self._on_startup: list[Callable[[], Coroutine[Any, Any, None] | None]] = []
        self._on_shutdown: list[Callable[[], Coroutine[Any, Any, None] | None]] = []

        # 정적 파일 매니저
        self._static_files_manager: "StaticFilesManager | None" = None

    def mount_static(
        self,
        path_prefix: str,
        directory: str,
        html: bool = False,
        check_exists: bool = True,
    ) -> "ASGIApplication":
        """
        정적 파일 디렉토리 마운트

        Args:
            path_prefix: URL 경로 프리픽스 (예: "/static")
            directory: 서빙할 디렉토리 경로
            html: True면 디렉토리 접근 시 index.html 자동 서빙
            check_exists: 디렉토리 존재 확인 여부

        Returns:
            self (메서드 체이닝 지원)

        사용 예시:
            app.asgi.mount_static("/static", "public")
            app.asgi.mount_static("/", "dist", html=True)  # SPA용
        """
        from .static import StaticFilesManager

        if self._static_files_manager is None:
            self._static_files_manager = StaticFilesManager()

        self._static_files_manager.mount(
            path_prefix=path_prefix,
            directory=directory,
            html=html,
            check_exists=check_exists,
        )
        return self

    def on_startup(
        self, func: Callable[[], Coroutine[Any, Any, None] | None]
    ) -> Callable[[], Coroutine[Any, Any, None] | None]:
        """
        startup 이벤트 콜백 등록

        사용 예시:
            @app.on_startup
            async def init_database():
                await db.connect()
        """
        self._on_startup.append(func)
        return func

    def on_shutdown(
        self, func: Callable[[], Coroutine[Any, Any, None] | None]
    ) -> Callable[[], Coroutine[Any, Any, None] | None]:
        """
        shutdown 이벤트 콜백 등록

        사용 예시:
            @app.on_shutdown
            async def close_database():
                await db.disconnect()
        """
        self._on_shutdown.append(func)
        return func

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 진입점"""
        if scope["type"] == "http":
            # Graceful shutdown 중이면 503 반환
            if self._is_shutting_down:
                await self._send_service_unavailable(send)
                return
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
        elif scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        else:
            raise ValueError(f"Unknown scope type: {scope['type']}")

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        """HTTP 요청 처리"""
        # 활성 요청 카운트 증가
        self._active_requests += 1
        try:
            # 요청 바디 수집
            body = b""
            while True:
                message = await receive()
                body += message.get("body", b"")
                if not message.get("more_body", False):
                    break

            # HttpRequest 생성
            request = self._build_request(scope, body)

            # 정적 파일 확인 (마운트된 경우)
            if self._static_files_manager and self._static_files_manager.matches(
                request.path
            ):
                static_response = await self._static_files_manager.handle_request(
                    request
                )
                if static_response is not None:
                    if isinstance(static_response, StreamingResponse):
                        await self._send_streaming_response(send, static_response)
                    else:
                        await self._send_response(send, static_response)
                    return

            # Router를 통해 핸들러 호출 (비동기)
            response = await self.router.dispatch(request)

            # 응답 전송 (스트리밍 여부에 따라 분기)
            if isinstance(response, StreamingResponse):
                await self._send_streaming_response(send, response)
            else:
                await self._send_response(send, response)
        finally:
            # 활성 요청 카운트 감소
            self._active_requests -= 1
            # shutdown 대기 중이고 모든 요청이 완료되면 이벤트 설정
            if self._shutdown_event and self._active_requests == 0:
                self._shutdown_event.set()

    async def _handle_websocket(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """WebSocket 연결 처리"""
        if not self.stomp_handler:
            # WebSocket 지원 비활성화 - 연결 거부
            await send({"type": "websocket.close", "code": 1000})
            return

        # WebSocket 연결 이벤트 대기
        message = await receive()
        if message["type"] != "websocket.connect":
            return

        # 헤더 파싱
        headers = {
            key.decode("utf-8"): value.decode("utf-8")
            for key, value in scope.get("headers", [])
        }

        # 쿼리 파라미터 파싱
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = {k: v[0] for k, v in parse_qs(query_string).items()}

        # WebSocketSession 생성
        from .messaging.session import WebSocketSession

        session = WebSocketSession(
            path=scope["path"],
            headers=headers,
            query_params=query_params,
            _receive=receive,
            _send=send,
        )

        # STOMP 핸들러로 위임
        await self.stomp_handler.handle_session(session)

    async def _handle_lifespan(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """
        Lifespan 이벤트 처리 (startup/shutdown)

        멀티 워커 환경에서 각 워커 프로세스마다 호출됩니다.
        - startup: Application 초기화, DI 컨테이너 준비
        - shutdown: 진행 중 요청 대기, 리소스 정리
        """
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                try:
                    await self._startup()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as e:
                    await send({"type": "lifespan.startup.failed", "message": str(e)})
                    return

            elif message["type"] == "lifespan.shutdown":
                await self._shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _startup(self) -> None:
        """startup 이벤트 처리"""
        # Application이 있으면 ready() 호출 (멀티워커 환경 지원)
        if self.application and not self.application._is_ready:
            self.application.ready()

        # WebSocketManager에서 설정 가져오기 (ready()에서 이미 초기화됨)
        self._apply_websocket_from_manager()

        # 등록된 startup 콜백 실행
        for callback in self._on_startup:
            result = callback()
            if asyncio.iscoroutine(result):
                await result

    def _apply_websocket_from_manager(self) -> None:
        """WebSocketManager에서 WebSocket 설정을 가져와 적용"""
        if not self.application:
            return

        ws_manager = self.application.websocket_manager

        # @EnableWebSocket이 없으면 패스
        if not ws_manager.enabled:
            return

        # StompProtocolHandler 설정
        if ws_manager.stomp_handler:
            self.stomp_handler = ws_manager.stomp_handler
        else:
            # StompProtocolHandler가 없으면 생성
            self._create_stomp_handler()

        # 엔드포인트 경로 설정
        endpoint_paths = ws_manager.get_endpoint_paths()
        if endpoint_paths:
            self.websocket_path = endpoint_paths[0]

    def _create_stomp_handler(self) -> None:
        """StompProtocolHandler를 생성하고 설정 적용"""
        if not self.application:
            return

        from .messaging import (
            SimpleBroker,
            WebSocketSessionManager,
            StompProtocolHandler,
        )

        ws_manager = self.application.websocket_manager
        manager = self.application.manager

        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        self.stomp_handler = StompProtocolHandler(broker, session_manager, manager)
        self.stomp_handler.collect_handlers(manager)

    async def _shutdown(self, timeout: float = 30.0) -> None:
        """
        shutdown 이벤트 처리 (Graceful Shutdown)

        1. 새 요청 거부 시작
        2. 진행 중인 요청이 완료될 때까지 대기 (타임아웃 있음)
        3. Application shutdown 호출
        4. 등록된 shutdown 콜백 실행
        """
        # 새 요청 거부 시작
        self._is_shutting_down = True

        # 진행 중인 요청이 있으면 대기
        if self._active_requests > 0:
            self._shutdown_event = asyncio.Event()
            try:
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass  # 타임아웃 시 강제 종료

        # Application shutdown 호출
        if self.application:
            self.application.shutdown()

        # 등록된 shutdown 콜백 실행
        for callback in self._on_shutdown:
            result = callback()
            if asyncio.iscoroutine(result):
                await result

    async def _send_service_unavailable(self, send: Send) -> None:
        """503 Service Unavailable 응답 전송 (Graceful Shutdown 중)"""
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", b"5"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"error": "Service is shutting down"}',
            }
        )

    def _build_request(self, scope: Scope, body: bytes) -> HttpRequest:
        """ASGI scope로부터 HttpRequest 생성"""
        # 헤더 파싱
        headers = {
            key.decode("utf-8"): value.decode("utf-8")
            for key, value in scope.get("headers", [])
        }

        # 쿼리 파라미터 파싱
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = {k: v[0] for k, v in parse_qs(query_string).items()}

        return HttpRequest(
            method=scope["method"],
            path=scope["path"],
            headers=headers,
            query_params=query_params,
            body=body if body else None,
        )

    async def _send_response(self, send: Send, response: HttpResponse) -> None:
        """HttpResponse를 ASGI 응답으로 전송"""
        # 응답 바디 생성
        if response.body is not None:
            body = response.to_bytes()
            content_type = response.content_type
        else:
            body = b""
            content_type = "text/plain"

        # 헤더 구성
        headers = [
            (b"content-type", content_type.encode("utf-8")),
            (b"content-length", str(len(body)).encode("utf-8")),
        ]
        # 추가 헤더
        for key, value in response.headers.items():
            headers.append((key.encode("utf-8"), value.encode("utf-8")))

        # HTTP 응답 시작
        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": headers,
            }
        )

        # HTTP 응답 바디
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )

    async def _send_streaming_response(
        self, send: Send, response: StreamingResponse
    ) -> None:
        """StreamingResponse를 청크 단위로 전송"""
        # 헤더 구성 (Content-Length 없음 - Transfer-Encoding: chunked 사용)
        headers = [
            (b"content-type", response.content_type.encode("utf-8")),
        ]
        # 추가 헤더
        for key, value in response.headers.items():
            headers.append((key.encode("utf-8"), value.encode("utf-8")))

        # HTTP 응답 시작
        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": headers,
            }
        )

        # 청크 단위로 바디 전송
        async for chunk in response:
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": True,
                }
            )

        # 스트림 종료
        await send(
            {
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            }
        )


def create_asgi_app(router: Router | None = None) -> ASGIApplication:
    """
    ASGI 애플리케이션 팩토리

    Args:
        router: Router 인스턴스. None이면 get_current_manager()를 사용해 생성

    Returns:
        ASGIApplication 인스턴스
    """
    if router is None:
        from bloom.core.manager import get_current_manager

        router = Router(get_current_manager())
        router.collect_routes()

    return ASGIApplication(router)
