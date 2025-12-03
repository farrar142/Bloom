"""bloom.web.middleware.request_scope - REQUEST Scope Middleware"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Middleware
from ...core import get_container_manager

if TYPE_CHECKING:
    from ..types import ASGIApp, Scope, Receive, Send


class RequestScopeMiddleware(Middleware):
    """
    REQUEST 스코프 컨텍스트 관리 미들웨어.

    HTTP 요청마다 새로운 REQUEST 스코프 컨텍스트를 시작하고,
    요청 종료 시 자동으로 정리합니다.

    사용 예:
        app = ASGIApplication()
        app.add_middleware(RequestScopeMiddleware)

        @Component(scope=Scope.REQUEST)
        class RequestContext:
            def __init__(self):
                self.request_id = uuid.uuid4()

            @PreDestroy
            async def cleanup(self):
                print(f"Request {self.request_id} finished")
    """

    def __init__(self, app: "ASGIApp") -> None:
        super().__init__(app)
        self._manager = get_container_manager()

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        """
        HTTP 요청에 대해 REQUEST 스코프 컨텍스트를 관리합니다.

        - http 요청: request_scope() 컨텍스트 내에서 처리
        - websocket/lifespan: 그대로 통과
        """
        if scope["type"] == "http":
            # REQUEST 스코프 컨텍스트 시작
            async with self._manager.scope_manager.request_scope():
                await self.app(scope, receive, send)
        else:
            # http가 아닌 경우 (websocket, lifespan 등)는 그대로 통과
            await self.app(scope, receive, send)
