"""bloom.web.middleware.error_handler - 에러 핸들링 미들웨어"""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from ..error import (
    HTTPException,
    ExceptionHandlerRegistry,
    json_error_response,
)
from .base import Middleware

if TYPE_CHECKING:
    from ..types import Scope, Receive, Send, ASGIApp
    from ..request import Request
    from ..response import Response


class ErrorHandlerMiddleware(Middleware):
    """
    전역 에러 핸들링 미들웨어.

    모든 예외를 잡아서 적절한 HTTP 응답으로 변환합니다.

    사용 예:
        middleware_stack = MiddlewareStack(app)
        middleware_stack.add(ErrorHandlerMiddleware(debug=True))

        # 커스텀 핸들러 등록
        error_middleware = ErrorHandlerMiddleware()
        error_middleware.add_handler(ValidationError, custom_validation_handler)
    """

    def __init__(
        self,
        app: "ASGIApp | None" = None,
        debug: bool = False,
        log_exceptions: bool = True,
    ) -> None:
        """
        Args:
            app: 다음 ASGI 앱
            debug: 디버그 모드 (traceback 포함)
            log_exceptions: 예외 로깅 여부
        """
        super().__init__(app)
        self.debug = debug
        self.log_exceptions = log_exceptions
        self._registry = ExceptionHandlerRegistry()

    def add_handler(
        self,
        exception_type: type[Exception],
        handler,
        order: int = 0,
    ) -> None:
        """
        예외 핸들러 추가.

        Args:
            exception_type: 처리할 예외 타입
            handler: 핸들러 함수 (request, exc) -> Response
            order: 우선순위 (낮을수록 먼저)
        """
        self._registry.register(exception_type, handler, order)

    async def __call__(
        self,
        scope: "Scope",
        receive: "Receive",
        send: "Send",
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if response_started:
                # 이미 응답이 시작됐으면 다시 보낼 수 없음
                if self.log_exceptions:
                    self._log_exception(exc)
                raise

            # 로깅
            if self.log_exceptions:
                self._log_exception(exc)

            # 응답 생성
            response = await self._handle_exception(scope, exc)
            await response(scope, receive, send)

    async def _handle_exception(
        self,
        scope: "Scope",
        exc: Exception,
    ) -> "Response":
        """예외 처리하여 응답 생성"""
        from ..request import Request

        # 더미 receive (이미 body를 읽었을 수 있음)
        async def dummy_receive():
            return {"type": "http.disconnect"}

        request = Request(scope, dummy_receive)

        # 커스텀 핸들러 찾기
        handler = self._registry.find_handler(exc)
        if handler:
            try:
                response = handler(request, exc)
                # async handler 지원
                if hasattr(response, "__await__"):
                    response = await response
                return response
            except Exception:
                # 핸들러에서 에러 발생 시 기본 처리로 폴백
                pass

        # 기본 처리
        return json_error_response(exc, include_traceback=self.debug)

    def _log_exception(self, exc: Exception) -> None:
        """예외 로깅"""
        import logging

        logger = logging.getLogger("bloom.web.error")

        if isinstance(exc, HTTPException):
            if exc.status_code >= 500:
                logger.error(f"HTTP {exc.status_code}: {exc.detail}")
                logger.debug(traceback.format_exc())
            else:
                logger.warning(f"HTTP {exc.status_code}: {exc.detail}")
        else:
            logger.exception(f"Unhandled exception: {exc}")


class CORSMiddleware(Middleware):
    """
    CORS (Cross-Origin Resource Sharing) 미들웨어.

    브라우저의 교차 출처 요청을 허용합니다.

    사용 예:
        middleware_stack.add(CORSMiddleware(
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["*"],
        ))
    """

    def __init__(
        self,
        app: "ASGIApp | None" = None,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        allow_credentials: bool = False,
        expose_headers: list[str] | None = None,
        max_age: int = 600,
    ) -> None:
        super().__init__(app)
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or [
            "GET",
            "POST",
            "PUT",
            "DELETE",
            "OPTIONS",
            "PATCH",
        ]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.expose_headers = expose_headers or []
        self.max_age = max_age

    async def __call__(
        self,
        scope: "Scope",
        receive: "Receive",
        send: "Send",
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET")
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("latin-1")

        # Preflight 요청 (OPTIONS)
        if method == "OPTIONS" and origin:
            await self._handle_preflight(scope, receive, send, origin)
            return

        # 일반 요청에 CORS 헤더 추가
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                cors_headers = self._get_cors_headers(origin)
                existing_headers = list(message.get("headers", []))
                existing_headers.extend(cors_headers)
                message["headers"] = existing_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)

    async def _handle_preflight(
        self,
        scope: "Scope",
        receive: "Receive",
        send: "Send",
        origin: str,
    ) -> None:
        """Preflight 요청 처리"""
        cors_headers = self._get_cors_headers(origin)
        cors_headers.extend(
            [
                (
                    b"access-control-allow-methods",
                    ", ".join(self.allow_methods).encode(),
                ),
                (
                    b"access-control-allow-headers",
                    ", ".join(self.allow_headers).encode(),
                ),
                (b"access-control-max-age", str(self.max_age).encode()),
            ]
        )

        await send(
            {
                "type": "http.response.start",
                "status": 204,
                "headers": cors_headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"",
            }
        )

    def _get_cors_headers(self, origin: str) -> list[tuple[bytes, bytes]]:
        """CORS 헤더 생성"""
        headers: list[tuple[bytes, bytes]] = []

        # Allow-Origin
        if "*" in self.allow_origins:
            headers.append((b"access-control-allow-origin", b"*"))
        elif origin in self.allow_origins:
            headers.append((b"access-control-allow-origin", origin.encode()))

        # Allow-Credentials
        if self.allow_credentials:
            headers.append((b"access-control-allow-credentials", b"true"))

        # Expose-Headers
        if self.expose_headers:
            headers.append(
                (
                    b"access-control-expose-headers",
                    ", ".join(self.expose_headers).encode(),
                )
            )

        return headers
