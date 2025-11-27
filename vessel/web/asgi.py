"""ASGI 애플리케이션 인터페이스"""

import json
from typing import Any, Callable, Coroutine
from urllib.parse import parse_qs

from .http import HttpRequest, HttpResponse
from .router import Router

# ASGI 타입 정의
Scope = dict[str, Any]
Receive = Callable[[], Coroutine[Any, Any, dict[str, Any]]]
Send = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class ASGIApplication:
    """
    ASGI 표준 애플리케이션

    사용 예시:
        # uvicorn으로 실행
        app = ASGIApplication(router)

        # uvicorn main:app
    """

    def __init__(self, router: Router):
        self.router = router

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 진입점"""
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        else:
            raise ValueError(f"Unknown scope type: {scope['type']}")

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        """HTTP 요청 처리"""
        # 요청 바디 수집
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break

        # HttpRequest 생성
        request = self._build_request(scope, body)

        # Router를 통해 핸들러 호출 (비동기)
        response = await self.router.dispatch(request)

        # 응답 전송
        await self._send_response(send, response)

    async def _handle_lifespan(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Lifespan 이벤트 처리 (startup/shutdown)"""
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

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
            body = response.to_json()
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


def create_asgi_app(router: Router | None = None) -> ASGIApplication:
    """
    ASGI 애플리케이션 팩토리

    Args:
        router: Router 인스턴스. None이면 새로 생성하고 라우트 수집

    Returns:
        ASGIApplication 인스턴스
    """
    if router is None:
        router = Router()
        router.collect_routes()

    return ASGIApplication(router)
