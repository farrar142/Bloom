"""bloom.web.asgi - ASGI Application"""

from inspect import iscoroutine
import re

from bloom import Application

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
        self.response_converter_registry = ResponseConverterRegistry()
        self.router = Router()
        self.router.add_route("/response", "GET", lambda x: {"message": "Hello, ASGI!"})
        self.router.add_route(
            "/response", "POST", lambda x: {"message": "Hello, POST!"}
        )
        self.router.add_route(
            "/users/{user_id}",
            "POST",
            lambda x: {"message": f"Hello, {x.path_params.get('user_id')}!"},
        )
        # path -> {method -> (handler, pattern, param_names)}

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
        route = self.router.match(scope["path"], scope["method"])
        if route is None:
            return await JSONResponse({})(scope, receive, send)
        request._scope["path_params"] = route.path_params
        result = route.handler(request)
        if iscoroutine(result):
            result = await result
        response = self.response_converter_registry.convert(result)

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
                    await self.application.ready()
                    self.logger.info("Application startup")
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
