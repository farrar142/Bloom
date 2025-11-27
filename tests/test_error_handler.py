"""ErrorHandler 테스트"""

import pytest
from vessel import Application, Component, Controller
from vessel.web import Get, RequestMapping
from vessel.web.error_handler import ErrorHandler
from vessel.web.http import HttpRequest, HttpResponse

from .conftest import Module


class TestErrorHandlerBasic:
    """기본 ErrorHandler 테스트 - RuntimeError와 Exception 핸들링"""

    @pytest.mark.asyncio
    async def test_runtime_error_handler(self):
        """RuntimeError를 핸들링하는 글로벌 에러 핸들러 테스트"""

        class M:
            pass

        @Module(M)
        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(RuntimeError)
            def handle_runtime_error(self, error: RuntimeError) -> HttpResponse:
                return HttpResponse.bad_request(f"RuntimeError: {error}")

        @Module(M)
        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise RuntimeError("Something went wrong")

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/error")
        response = await app.router.dispatch(request)

        assert response.status_code == 400
        assert "RuntimeError: Something went wrong" in response.body

    @pytest.mark.asyncio
    async def test_exception_handler(self):
        """일반 Exception을 핸들링하는 글로벌 에러 핸들러 테스트"""

        class M:
            pass

        @Module(M)
        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(Exception)
            def handle_exception(self, error: Exception) -> HttpResponse:
                return HttpResponse.internal_error(f"Caught: {error}")

        @Module(M)
        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise ValueError("value error")

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/error")
        response = await app.router.dispatch(request)

        assert response.status_code == 500
        assert "Caught: value error" in response.body

    @pytest.mark.asyncio
    async def test_specific_exception_takes_priority_over_base(self):
        """더 구체적인 예외 타입이 기본 Exception보다 우선 처리됨"""

        class M:
            pass

        @Module(M)
        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(RuntimeError)
            def handle_runtime(self, error: RuntimeError) -> HttpResponse:
                return HttpResponse.bad_request("RuntimeError handled")

            @ErrorHandler(Exception)
            def handle_exception(self, error: Exception) -> HttpResponse:
                return HttpResponse.internal_error("Exception handled")

        @Module(M)
        @Controller
        class TestController:
            @Get("/runtime")
            async def raise_runtime(self) -> str:
                raise RuntimeError("runtime error")

            @Get("/value")
            async def raise_value(self) -> str:
                raise ValueError("value error")

        app = Application("test").scan(M).ready()

        # RuntimeError는 RuntimeError 핸들러가 처리
        request1 = HttpRequest(method="GET", path="/runtime")
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 400
        assert "RuntimeError handled" in response1.body

        # ValueError는 Exception 핸들러가 처리
        request2 = HttpRequest(method="GET", path="/value")
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 500
        assert "Exception handled" in response2.body

    @pytest.mark.asyncio
    async def test_no_handler_returns_default_error(self):
        """핸들러가 없으면 기본 500 에러 응답 반환"""

        class M:
            pass

        @Module(M)
        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise RuntimeError("unhandled error")

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/error")
        response = await app.router.dispatch(request)

        # 기본 에러 응답 (ErrorHandlerMiddleware의 fallback)
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_custom_exception_hierarchy(self):
        """커스텀 예외 계층 구조에서 올바른 핸들러 선택"""

        class CustomBaseError(Exception):
            pass

        class CustomChildError(CustomBaseError):
            pass

        class M:
            pass

        @Module(M)
        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(CustomBaseError)
            def handle_custom_base(self, error: CustomBaseError) -> HttpResponse:
                return HttpResponse.bad_request("CustomBaseError handled")

        @Module(M)
        @Controller
        class TestController:
            @Get("/child")
            async def raise_child(self) -> str:
                raise CustomChildError("child error")

        app = Application("test").scan(M).ready()

        # CustomChildError는 CustomBaseError 핸들러가 처리 (상속 관계)
        request = HttpRequest(method="GET", path="/child")
        response = await app.router.dispatch(request)
        assert response.status_code == 400
        assert "CustomBaseError handled" in response.body

    @pytest.mark.asyncio
    async def test_async_error_handler(self):
        """비동기 에러 핸들러 테스트"""

        class M:
            pass

        @Module(M)
        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(RuntimeError)
            async def handle_runtime(self, error: RuntimeError) -> HttpResponse:
                # 비동기 처리 시뮬레이션
                return HttpResponse.bad_request(f"Async handled: {error}")

        @Module(M)
        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise RuntimeError("async test")

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/error")
        response = await app.router.dispatch(request)

        assert response.status_code == 400
        assert "Async handled: async test" in response.body

    @pytest.mark.asyncio
    async def test_error_handler_returns_dict(self):
        """에러 핸들러가 dict를 반환하면 HttpResponse.ok로 변환"""

        class M:
            pass

        @Module(M)
        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(RuntimeError)
            def handle_runtime(self, error: RuntimeError) -> dict:
                return {"error": str(error), "type": "RuntimeError"}

        @Module(M)
        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise RuntimeError("dict response")

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/error")
        response = await app.router.dispatch(request)

        # dict 반환 시 HttpResponse.ok로 변환 (200 상태 코드)
        assert response.status_code == 200
        assert "dict response" in str(response.body)
