"""웹 기능 테스트"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
import pytest
from bloom import Application, Component
from bloom.core import ContainerManager
from bloom.core.decorators import Factory
from bloom.web import (
    HttpRequest,
    HttpResponse,
    HttpMethodHandler,
    Get,
    Post,
    Put,
    Delete,
    Router,
    Controller,
    RequestMapping,
    ControllerContainer,
    ASGIApplication,
    create_asgi_app,
)

from .conftest import Module

from bloom.web.middleware import Middleware, MiddlewareChain


class TestMiddleware:
    """미들웨어 테스트"""

    @pytest.mark.asyncio
    async def test_middleware_execution_order(self):
        """미들웨어가 올바른 순서로 실행되는지 테스트"""
        execution_order: list[str] = []

        class M:
            pass

        @Module(M)
        @Component
        class LoggingService:
            def log(self, message: str):
                execution_order.append(message)

        @Module(M)
        @Component
        class MiddlewareA(Middleware):
            loggingService: LoggingService

            async def process_request(
                self, request: HttpRequest
            ) -> Optional[HttpResponse]:
                self.loggingService.log("A - before")
                return None

            async def process_response(
                self, request: HttpRequest, response: HttpResponse
            ) -> HttpResponse:
                self.loggingService.log("A - after")
                return response

        @Module(M)
        @Component
        class MiddlewareB(Middleware):
            loggingService: LoggingService

            async def process_request(
                self, request: HttpRequest
            ) -> Optional[HttpResponse]:
                self.loggingService.log("B - before")
                return None

            async def process_response(
                self, request: HttpRequest, response: HttpResponse
            ) -> HttpResponse:
                self.loggingService.log("B - after")
                return response

        @Module(M)
        @Component
        class MiddlewareC(Middleware):
            loggingService: LoggingService

            async def process_request(
                self, request: HttpRequest
            ) -> Optional[HttpResponse]:
                self.loggingService.log("C - before")
                return None

            async def process_response(
                self, request: HttpRequest, response: HttpResponse
            ) -> HttpResponse:
                self.loggingService.log("C - after")
                return response

        @Module(M)
        @Component
        class MiddlewareConfiguration:
            @Factory
            def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.add_group_after(*middlewares)
                return chain

        @Module(M)
        @Controller
        @RequestMapping("/api")
        class TestController:
            @Get("/test")
            async def test_handler(self):
                return "Test Response"

        app = Application("test").scan(M).ready()
        request = HttpRequest(method="GET", path="/api/test")
        response = await app.router.dispatch(request)
        assert response.status_code == 200
        assert response.body == "Test Response"

        # 미들웨어가 올바른 순서로 실행되었는지 확인
        assert execution_order == [
            "A - before",
            "B - before",
            "C - before",
            "C - after",
            "B - after",
            "A - after",
        ]
