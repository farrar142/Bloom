"""bloom.web.middleware.base - Middleware Base Classes"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..types import ASGIApp, Scope, Receive, Send


class Middleware(ABC):
    """
    미들웨어 베이스 클래스.
    
    사용 예:
        class LoggingMiddleware(Middleware):
            async def __call__(self, scope, receive, send):
                print(f"Request: {scope['path']}")
                await self.app(scope, receive, send)
                print("Response sent")
    """

    def __init__(self, app: "ASGIApp") -> None:
        self.app = app

    @abstractmethod
    async def __call__(
        self, scope: "Scope", receive: "Receive", send: "Send"
    ) -> None:
        """미들웨어 실행"""
        pass


class MiddlewareStack:
    """
    미들웨어 스택 관리.
    
    미들웨어를 순서대로 쌓아서 체인을 구성합니다.
    
    사용 예:
        stack = MiddlewareStack(app)
        stack.add(LoggingMiddleware)
        stack.add(AuthMiddleware)
        
        # 실행 순서: LoggingMiddleware → AuthMiddleware → app
        final_app = stack.build()
    """

    def __init__(self, app: "ASGIApp") -> None:
        self._app = app
        self._middlewares: list[type[Middleware]] = []
        self._middleware_kwargs: list[dict] = []

    def add(
        self,
        middleware_cls: type[Middleware],
        **kwargs,
    ) -> "MiddlewareStack":
        """미들웨어 추가"""
        self._middlewares.append(middleware_cls)
        self._middleware_kwargs.append(kwargs)
        return self

    def build(self) -> "ASGIApp":
        """미들웨어 체인 빌드"""
        app = self._app
        
        # 역순으로 래핑 (마지막에 추가된 것이 가장 바깥)
        for middleware_cls, kwargs in zip(
            reversed(self._middlewares),
            reversed(self._middleware_kwargs),
        ):
            app = middleware_cls(app, **kwargs)
        
        return app

    def __len__(self) -> int:
        return len(self._middlewares)
