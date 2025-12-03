"""bloom.web.asgi - ASGI Application"""

from __future__ import annotations

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
        self._routes: dict[str, dict[str, Callable]] = {}  # path -> {method -> handler}
        self._middleware_stack = MiddlewareStack(self._handle_request)
        
        # REQUEST 스코프 미들웨어는 기본으로 추가
        self._middleware_stack.add(RequestScopeMiddleware)
        
        self._app: ASGIApp | None = None

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

        def decorator(handler: Callable) -> Callable:
            if path not in self._routes:
                self._routes[path] = {}
            for method in methods:
                self._routes[path][method.upper()] = handler
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

    async def _handle_request(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
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

        request = Request(scope, receive)
        
        # 라우트 매칭 (단순 exact match)
        # TODO: 패턴 매칭, path params 추출
        handler = self._routes.get(request.path, {}).get(request.method)
        
        if handler is None:
            # 404 Not Found
            response = JSONResponse(
                {"error": "Not Found", "path": request.path},
                status_code=404,
            )
            await response(scope, receive, send)
            return

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
                    await send({
                        "type": "lifespan.startup.failed",
                        "message": str(e),
                    })
                    return
            
            elif message["type"] == "lifespan.shutdown":
                try:
                    # TODO: 앱 종료 (ContainerManager.shutdown())
                    await send({"type": "lifespan.shutdown.complete"})
                except Exception as e:
                    await send({
                        "type": "lifespan.shutdown.failed",
                        "message": str(e),
                    })
                return

    # === ASGI Interface ===

    def _build_app(self) -> ASGIApp:
        """미들웨어 체인 빌드"""
        if self._app is None:
            self._app = self._middleware_stack.build()
        return self._app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """ASGI 진입점"""
        app = self._build_app()
        await app(scope, receive, send)
