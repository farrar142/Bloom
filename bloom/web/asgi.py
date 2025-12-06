"""bloom.web.asgi - ASGI Application"""

import re


from .response import JSONResponse, ResponseConverterRegistry
from .request import HttpRequest

from .types import Receive, Scope, Send

from ..logger import get_logger


class ASGIApplication:
    logger = get_logger()

    def __init__(self, *, debug: bool = False) -> None:
        self.debug = debug
        self.response_converter_registry = ResponseConverterRegistry()
        # path -> {method -> (handler, pattern, param_names)}

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

    # === Request Handler ===

    async def _handle_request(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        실제 요청 처리.

        라우트 매칭 후 핸들러 실행.
        """
        self.logger.debug(f"Received request scope: {scope}")
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
        request = HttpRequest
        self.logger.info(f"Handling request: {request}")
        # 경로 추출
        path = scope.get("path", "/")
        method = scope.get("method", "GET")
        result = {}
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
        """ASGI 진입점"""
        await self._handle_request(scope, receive, send)
