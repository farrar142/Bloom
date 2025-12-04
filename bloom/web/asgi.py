"""bloom.web.asgi - ASGI Application"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, Any

from .types import ASGIApp, Scope, Receive, Send
from .request import Request
from .response import Response, JSONResponse
from .middleware.base import Middleware, MiddlewareStack
from .middleware.request_scope import RequestScopeMiddleware

if TYPE_CHECKING:
    pass


class ASGIApplication:
    """
    Bloom ASGI Application.

    미들웨어 체인과 라우팅을 관리하는 ASGI 앱입니다.

    사용 예:
        app = ASGIApplication()

        # 미들웨어 추가
        app.add_middleware(RequestScopeMiddleware)
        app.add_middleware(LoggingMiddleware)

        # 라우트 추가
        @app.get("/")
        async def index(request: Request) -> Response:
            return JSONResponse({"message": "Hello, World!"})

        # uvicorn으로 실행
        # uvicorn app:app
    """

    def __init__(self, *, debug: bool = False) -> None:
        self.debug = debug
        # path -> {method -> (handler, pattern, param_names)}
        self._routes: dict[str, dict[str, tuple[Callable, re.Pattern, list[str]]]] = {}
        # 패턴 매칭용 라우트 리스트: (pattern, route_path, {method -> handler})
        self._route_patterns: list[tuple[re.Pattern, str, dict[str, Callable]]] = []
        self._middleware_stack = MiddlewareStack(self._handle_request)

        # REQUEST 스코프 미들웨어는 기본으로 추가
        self._middleware_stack.add(RequestScopeMiddleware)

        self._app: ASGIApp | None = None

    def _compile_path_pattern(self, path: str) -> tuple[re.Pattern, list[str]]:
        """경로 패턴을 정규식으로 컴파일

        /users/{id} → /users/(?P<id>[^/]+)
        """
        param_names: list[str] = []
        pattern_parts: list[str] = []

        for part in path.split("/"):
            if part.startswith("{") and part.endswith("}"):
                param_name = part[1:-1]
                param_names.append(param_name)
                pattern_parts.append(f"(?P<{param_name}>[^/]+)")
            else:
                pattern_parts.append(re.escape(part))

        pattern_str = "/".join(pattern_parts)
        # 정확히 매칭되도록 ^ $ 추가
        pattern = re.compile(f"^{pattern_str}$")
        return pattern, param_names

    # === Middleware ===

    def add_middleware(
        self,
        middleware_cls: type[Middleware],
        **kwargs: Any,
    ) -> "ASGIApplication":
        """미들웨어 추가"""
        self._middleware_stack.add(middleware_cls, **kwargs)
        self._app = None  # 캐시 무효화
        return self

    # === Routes ===

    def route(
        self,
        path: str,
        methods: list[str] | None = None,
    ) -> Callable[[Callable], Callable]:
        """라우트 데코레이터"""
        if methods is None:
            methods = ["GET"]

        # 패턴 컴파일
        pattern, param_names = self._compile_path_pattern(path)

        def decorator(handler: Callable) -> Callable:
            if path not in self._routes:
                self._routes[path] = {}
            for method in methods:
                self._routes[path][method.upper()] = (handler, pattern, param_names)

            # _route_patterns에 패턴 매칭용 데이터 추가
            # 이미 등록된 path의 handlers 업데이트
            for i, (p, rp, handlers) in enumerate(self._route_patterns):
                if rp == path:
                    for method in methods:
                        handlers[method.upper()] = handler
                    break
            else:
                # 새로운 패턴 등록
                handlers = {method.upper(): handler for method in methods}
                self._route_patterns.append((pattern, path, handlers))

            return handler

        return decorator

    def get(self, path: str) -> Callable[[Callable], Callable]:
        """GET 라우트 데코레이터"""
        return self.route(path, methods=["GET"])

    def post(self, path: str) -> Callable[[Callable], Callable]:
        """POST 라우트 데코레이터"""
        return self.route(path, methods=["POST"])

    def put(self, path: str) -> Callable[[Callable], Callable]:
        """PUT 라우트 데코레이터"""
        return self.route(path, methods=["PUT"])

    def delete(self, path: str) -> Callable[[Callable], Callable]:
        """DELETE 라우트 데코레이터"""
        return self.route(path, methods=["DELETE"])

    def patch(self, path: str) -> Callable[[Callable], Callable]:
        """PATCH 라우트 데코레이터"""
        return self.route(path, methods=["PATCH"])

    # === Request Handler ===

    async def _handle_request(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        실제 요청 처리.

        라우트 매칭 후 핸들러 실행.
        """
        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
            return

        if scope["type"] != "http":
            # WebSocket 등은 별도 처리 필요
            response = JSONResponse(
                {"error": "Not implemented"},
                status_code=501,
            )
            await response(scope, receive, send)
            return

        # 경로 추출
        path = scope.get("path", "/")
        method = scope.get("method", "GET")

        # 라우트 매칭 (패턴 매칭 + path params 추출)
        handler, path_params = self._match_route(path, method)

        if handler is None:
            # 404 Not Found
            response = JSONResponse(
                {"error": "Not Found", "path": path},
                status_code=404,
            )
            await response(scope, receive, send)
            return

        # path_params를 scope에 설정 (Request.path_params에서 읽음)
        scope["path_params"] = path_params

        request = Request(scope, receive)

        try:
            # 핸들러 실행
            result = await handler(request)

            # 응답 처리
            if isinstance(result, Response):
                response = result
            elif isinstance(result, dict):
                response = JSONResponse(result)
            elif isinstance(result, str):
                response = Response(content=result, media_type="text/plain")
            else:
                response = JSONResponse(result)

            await response(scope, receive, send)

        except Exception as e:
            # 500 Internal Server Error
            if self.debug:
                import traceback

                error_detail = traceback.format_exc()
            else:
                error_detail = str(e)

            response = JSONResponse(
                {"error": "Internal Server Error", "detail": error_detail},
                status_code=500,
            )
            await response(scope, receive, send)

    def _match_route(
        self, path: str, method: str
    ) -> tuple[Callable | None, dict[str, str]]:
        """
        라우트 매칭 (패턴 매칭 지원).

        Args:
            path: 요청 경로
            method: HTTP 메서드

        Returns:
            (handler, path_params) 튜플. 매칭 실패 시 (None, {})
        """
        for pattern, route_path, handlers in self._route_patterns:
            match = pattern.match(path)
            if match:
                handler = handlers.get(method)
                if handler:
                    return handler, match.groupdict()
        return None, {}

    async def _handle_lifespan(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """ASGI lifespan 프로토콜 처리"""
        while True:
            message = await receive()

            if message["type"] == "lifespan.startup":
                try:
                    # TODO: 앱 초기화 (ContainerManager.initialize())
                    await send({"type": "lifespan.startup.complete"})
                except Exception as e:
                    await send(
                        {
                            "type": "lifespan.startup.failed",
                            "message": str(e),
                        }
                    )
                    return

            elif message["type"] == "lifespan.shutdown":
                try:
                    # TODO: 앱 종료 (ContainerManager.shutdown())
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as e:
                    await send(
                        {
                            "type": "lifespan.shutdown.failed",
                            "message": str(e),
                        }
                    )
                return

    # === ASGI Interface ===

    def _build_app(self) -> ASGIApp:
        """미들웨어 체인 빌드"""
        if self._app is None:
            self._app = self._middleware_stack.build()
        return self._app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 진입점"""
        app = self._build_app()
        await app(scope, receive, send)
