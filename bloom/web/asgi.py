"""bloom.web.asgi - ASGI Application"""

from inspect import iscoroutine
import re
from typing import Callable

from bloom import Application
from bloom.web.decorators import RouteContainer

from .route import Route, Router

from .response import JSONResponse, ResponseConverterRegistry
from .request import HttpRequest

from .types import Receive, Scope, Send

from ..logger import get_logger


class ASGIApplication:
    logger = get_logger()

    def __init__(self, application: Application, debug: bool = False) -> None:
        self.application = application
        self.debug = debug
        self.response_converter = ResponseConverterRegistry()
        self.router = Router()
        # self.router.add_route(
        #     "/response", "GET", lambda request: {"message": "Hello, ASGI!"}
        # )
        # self.router.add_route("/response", "POST", lambda: {"message": "Hello, POST!"})
        # self.router.add_route(
        #     "/users/{user_id}",
        #     "POST",
        #     lambda request: {
        #         "message": f"Hello, {request.path_params.get('user_id')}!"
        #     },
        # )
        # path -> {method -> (handler, pattern, param_names)}

    async def ready(self):

        await self.application.ready()
        await self.collect_routes()

    async def collect_routes(self) -> None:
        """애플리케이션에서 모든 라우트 수집"""
        routes = self.application.container_manager.get_containers_by_container_type(
            RouteContainer
        )
        for route in routes:
            handler = self.application.container_manager.get_instance(
                route.component_id
            )
            prefix = ""
            if parent := route.parent_container:
                prefix = parent.get_element("path_prefix", "")
            path = prefix + route.get_element("path", "")
            method = route.get_element("method", "GET").upper()
            self.router.add_route(path, method, handler)

    # === Request Handler ===

    async def _handle_request(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        실제 요청 처리.

        라우트 매칭 후 핸들러 실행.
        """
        self.logger.debug(f"Received request scope: {scope}")
        if scope["type"] != "http":
            # WebSocket 등은 별도 처리 필요
            response = JSONResponse(
                {"error": "Not implemented"},
                status_code=501,
            )
            await response(scope, receive, send)
            return
        request = HttpRequest(scope, receive)
        route = self.router.match(
            str(scope.get("path", b"")), str(scope.get("method", b""))
        )
        if route is None:
            return await JSONResponse({})(scope, receive, send)
        request._scope["path_params"] = route.path_params

        params = await self.router.resolver.resolve_parameters(
            route.handler, request, route
        )
        result = route.handler(**params)
        if iscoroutine(result):
            result = await result
        response = self.response_converter.convert(result)

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
                    await self.ready()
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
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
            return

        """ASGI 진입점"""
        await self._handle_request(scope, receive, send)
