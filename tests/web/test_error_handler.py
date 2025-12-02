"""ErrorHandler 테스트"""

import pytest
from bloom import Application, Component, Controller
from bloom.web import Get, RequestMapping
from bloom.web.error import ErrorHandler
from bloom.web.http import HttpRequest, HttpResponse


class TestErrorHandlerBasic:
    """기본 ErrorHandler 테스트 - RuntimeError와 Exception 핸들링"""

    @pytest.mark.asyncio
    async def test_runtime_error_handler(self):
        """RuntimeError를 핸들링하는 글로벌 에러 핸들러 테스트"""

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(RuntimeError)
            def handle_runtime_error(self, error: RuntimeError) -> HttpResponse:
                return HttpResponse.bad_request(f"RuntimeError: {error}")

        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise RuntimeError("Something went wrong")

        app = Application("test").ready()

        request = HttpRequest(method="GET", path="/error")
        response = await app.router.dispatch(request)

        assert response.status_code == 400
        assert "RuntimeError: Something went wrong" in str(response.body)

    @pytest.mark.asyncio
    async def test_exception_handler(self):
        """일반 Exception을 핸들링하는 글로벌 에러 핸들러 테스트"""

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(Exception)
            def handle_exception(self, error: Exception) -> HttpResponse:
                return HttpResponse.internal_error(f"Caught: {error}")

        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise ValueError("value error")

        app = Application("test").ready()

        request = HttpRequest(method="GET", path="/error")
        response = await app.router.dispatch(request)

        assert response.status_code == 500
        assert "Caught: value error" in str(response.body)

    @pytest.mark.asyncio
    async def test_specific_exception_takes_priority_over_base(self):
        """더 구체적인 예외 타입이 기본 Exception보다 우선 처리됨"""

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(RuntimeError)
            def handle_runtime(self, error: RuntimeError) -> HttpResponse:
                return HttpResponse.bad_request("RuntimeError handled")

            @ErrorHandler(Exception)
            def handle_exception(self, error: Exception) -> HttpResponse:
                return HttpResponse.internal_error("Exception handled")

        @Controller
        class TestController:
            @Get("/runtime")
            async def raise_runtime(self) -> str:
                raise RuntimeError("runtime error")

            @Get("/value")
            async def raise_value(self) -> str:
                raise ValueError("value error")

        app = Application("test").ready()

        # RuntimeError는 RuntimeError 핸들러가 처리
        request1 = HttpRequest(method="GET", path="/runtime")
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 400
        assert "RuntimeError handled" in str(response1.body)

        # ValueError는 Exception 핸들러가 처리
        request2 = HttpRequest(method="GET", path="/value")
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 500
        assert "Exception handled" in str(response2.body)

    @pytest.mark.asyncio
    async def test_no_handler_returns_default_error(self):
        """핸들러가 없으면 기본 500 에러 응답 반환"""

        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise RuntimeError("unhandled error")

        app = Application("test").ready()

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

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(CustomBaseError)
            def handle_custom_base(self, error: CustomBaseError) -> HttpResponse:
                return HttpResponse.bad_request("CustomBaseError handled")

        @Controller
        class TestController:
            @Get("/child")
            async def raise_child(self) -> str:
                raise CustomChildError("child error")

        app = Application("test").ready()

        # CustomChildError는 CustomBaseError 핸들러가 처리 (상속 관계)
        request = HttpRequest(method="GET", path="/child")
        response = await app.router.dispatch(request)
        assert response.status_code == 400
        assert "CustomBaseError handled" in str(response.body)

    @pytest.mark.asyncio
    async def test_async_error_handler(self):
        """비동기 에러 핸들러 테스트"""

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(RuntimeError)
            async def handle_runtime(self, error: RuntimeError) -> HttpResponse:
                # 비동기 처리 시뮬레이션
                return HttpResponse.bad_request(f"Async handled: {error}")

        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise RuntimeError("async test")

        app = Application("test").ready()

        request = HttpRequest(method="GET", path="/error")
        response = await app.router.dispatch(request)

        assert response.status_code == 400
        assert "Async handled: async test" in str(response.body)

    @pytest.mark.asyncio
    async def test_error_handler_returns_dict(self):
        """에러 핸들러가 dict를 반환하면 HttpResponse.ok로 변환"""

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(RuntimeError)
            def handle_runtime(self, error: RuntimeError) -> dict:
                return {"error": str(error), "type": "RuntimeError"}

        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise RuntimeError("dict response")

        app = Application("test").ready()

        request = HttpRequest(method="GET", path="/error")
        response = await app.router.dispatch(request)

        # dict 반환 시 HttpResponse.ok로 변환 (200 상태 코드)
        assert response.status_code == 200
        assert "dict response" in str(response.body)


class TestCustomExceptionCases:
    """다양한 커스텀 예외 케이스 테스트"""

    @pytest.mark.asyncio
    async def test_deep_exception_hierarchy(self):
        """깊은 예외 계층 구조에서 가장 구체적인 핸들러 선택"""

        class Level1Error(Exception):
            pass

        class Level2Error(Level1Error):
            pass

        class Level3Error(Level2Error):
            pass

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(Level1Error)
            def handle_level1(self, error: Level1Error) -> HttpResponse:
                return HttpResponse(status_code=400, body="Level1")

            @ErrorHandler(Level2Error)
            def handle_level2(self, error: Level2Error) -> HttpResponse:
                return HttpResponse(status_code=401, body="Level2")

            @ErrorHandler(Level3Error)
            def handle_level3(self, error: Level3Error) -> HttpResponse:
                return HttpResponse(status_code=402, body="Level3")

        @Controller
        class TestController:
            @Get("/level1")
            async def raise_level1(self) -> str:
                raise Level1Error("level1")

            @Get("/level2")
            async def raise_level2(self) -> str:
                raise Level2Error("level2")

            @Get("/level3")
            async def raise_level3(self) -> str:
                raise Level3Error("level3")

        app = Application("test").ready()

        # 각 레벨에 맞는 핸들러가 선택되어야 함
        r1 = await app.router.dispatch(HttpRequest(method="GET", path="/level1"))
        assert r1.status_code == 400
        assert r1.body == "Level1"

        r2 = await app.router.dispatch(HttpRequest(method="GET", path="/level2"))
        assert r2.status_code == 401
        assert r2.body == "Level2"

        r3 = await app.router.dispatch(HttpRequest(method="GET", path="/level3"))
        assert r3.status_code == 402
        assert r3.body == "Level3"

    @pytest.mark.asyncio
    async def test_multiple_custom_exceptions_same_component(self):
        """같은 컴포넌트에서 여러 커스텀 예외 핸들러"""

        class NotFoundError(Exception):
            pass

        class UnauthorizedError(Exception):
            pass

        class ForbiddenError(Exception):
            pass

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(NotFoundError)
            def handle_not_found(self, error: NotFoundError) -> HttpResponse:
                return HttpResponse.not_found(str(error))

            @ErrorHandler(UnauthorizedError)
            def handle_unauthorized(self, error: UnauthorizedError) -> HttpResponse:
                return HttpResponse(status_code=401, body=str(error))

            @ErrorHandler(ForbiddenError)
            def handle_forbidden(self, error: ForbiddenError) -> HttpResponse:
                return HttpResponse(status_code=403, body=str(error))

        @Controller
        class TestController:
            @Get("/not-found")
            async def raise_not_found(self) -> str:
                raise NotFoundError("Resource not found")

            @Get("/unauthorized")
            async def raise_unauthorized(self) -> str:
                raise UnauthorizedError("Please login")

            @Get("/forbidden")
            async def raise_forbidden(self) -> str:
                raise ForbiddenError("Access denied")

        app = Application("test").ready()

        r1 = await app.router.dispatch(HttpRequest(method="GET", path="/not-found"))
        assert r1.status_code == 404
        assert "Resource not found" in str(r1.body)

        r2 = await app.router.dispatch(HttpRequest(method="GET", path="/unauthorized"))
        assert r2.status_code == 401
        assert "Please login" in str(r2.body)

        r3 = await app.router.dispatch(HttpRequest(method="GET", path="/forbidden"))
        assert r3.status_code == 403
        assert "Access denied" in str(r3.body)

    @pytest.mark.asyncio
    async def test_exception_with_custom_attributes(self):
        """커스텀 속성을 가진 예외 처리"""

        class ValidationError(Exception):
            def __init__(self, field: str, message: str):
                self.field = field
                self.message = message
                super().__init__(f"{field}: {message}")

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(ValidationError)
            def handle_validation(self, error: ValidationError) -> HttpResponse:
                return HttpResponse(
                    status_code=400,
                    body={"field": error.field, "message": error.message},
                )

        @Controller
        class TestController:
            @Get("/validate")
            async def validate(self) -> str:
                raise ValidationError("email", "Invalid email format")

        app = Application("test").ready()

        response = await app.router.dispatch(
            HttpRequest(method="GET", path="/validate")
        )
        assert response.status_code == 400
        assert "email" in str(response.body)
        assert "Invalid email format" in str(response.body)

    @pytest.mark.asyncio
    async def test_exception_handler_with_request_context(self):
        """에러 핸들러에서 request 정보 사용"""

        class ApiError(Exception):
            pass

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(ApiError)
            def handle_api_error(
                self, error: ApiError, request: HttpRequest
            ) -> HttpResponse:
                return HttpResponse(
                    status_code=400,
                    body={
                        "error": str(error),
                        "path": request.path,
                        "method": request.method,
                    },
                )

        @Controller
        class TestController:
            @Get("/api/test")
            async def api_test(self) -> str:
                raise ApiError("API failed")

        app = Application("test").ready()

        response = await app.router.dispatch(
            HttpRequest(method="GET", path="/api/test")
        )
        assert response.status_code == 400
        assert "API failed" in str(response.body)
        assert "/api/test" in str(response.body)
        assert "GET" in str(response.body)

    @pytest.mark.asyncio
    async def test_builtin_exceptions(self):
        """내장 예외 타입들 핸들링"""

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(ValueError)
            def handle_value_error(self, error: ValueError) -> HttpResponse:
                return HttpResponse.bad_request(f"ValueError: {error}")

            @ErrorHandler(TypeError)
            def handle_type_error(self, error: TypeError) -> HttpResponse:
                return HttpResponse.bad_request(f"TypeError: {error}")

            @ErrorHandler(KeyError)
            def handle_key_error(self, error: KeyError) -> HttpResponse:
                return HttpResponse.not_found(f"KeyError: {error}")

        @Controller
        class TestController:
            @Get("/value-error")
            async def raise_value_error(self) -> str:
                raise ValueError("invalid value")

            @Get("/type-error")
            async def raise_type_error(self) -> str:
                raise TypeError("wrong type")

            @Get("/key-error")
            async def raise_key_error(self) -> str:
                raise KeyError("missing_key")

        app = Application("test").ready()

        r1 = await app.router.dispatch(HttpRequest(method="GET", path="/value-error"))
        assert r1.status_code == 400
        assert "ValueError" in str(r1.body)

        r2 = await app.router.dispatch(HttpRequest(method="GET", path="/type-error"))
        assert r2.status_code == 400
        assert "TypeError" in str(r2.body)

        r3 = await app.router.dispatch(HttpRequest(method="GET", path="/key-error"))
        assert r3.status_code == 404
        assert "KeyError" in str(r3.body)

    @pytest.mark.asyncio
    async def test_exception_handler_raises_exception(self):
        """에러 핸들러 자체에서 예외 발생 시 기본 에러 응답"""

        class CustomError(Exception):
            pass

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(CustomError)
            def handle_custom(self, error: CustomError) -> HttpResponse:
                # 핸들러에서 또 다른 예외 발생
                raise RuntimeError("Handler failed!")

        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise CustomError("original error")

        app = Application("test").ready()

        response = await app.router.dispatch(HttpRequest(method="GET", path="/error"))
        # 핸들러 실패 시 기본 500 에러
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_multiple_inheritance_exception(self):
        """다중 상속 예외 처리"""

        class NetworkError(Exception):
            pass

        class TimeoutError(Exception):
            pass

        class NetworkTimeoutError(NetworkError, TimeoutError):
            pass

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(NetworkError)
            def handle_network(self, error: NetworkError) -> HttpResponse:
                return HttpResponse(status_code=502, body="NetworkError")

            @ErrorHandler(TimeoutError)
            def handle_timeout(self, error: TimeoutError) -> HttpResponse:
                return HttpResponse(status_code=504, body="TimeoutError")

        @Controller
        class TestController:
            @Get("/network-timeout")
            async def raise_network_timeout(self) -> str:
                raise NetworkTimeoutError("connection timed out")

        app = Application("test").ready()

        response = await app.router.dispatch(
            HttpRequest(method="GET", path="/network-timeout")
        )
        # 다중 상속 시 첫 번째 부모 클래스(NetworkError) 핸들러가 선택됨
        assert response.status_code in [502, 504]  # MRO 순서에 따라 결정

    @pytest.mark.asyncio
    async def test_error_handler_returns_string(self):
        """에러 핸들러가 문자열 반환"""

        class SimpleError(Exception):
            pass

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(SimpleError)
            def handle_simple(self, error: SimpleError) -> str:
                return f"Error occurred: {error}"

        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise SimpleError("simple message")

        app = Application("test").ready()

        response = await app.router.dispatch(HttpRequest(method="GET", path="/error"))
        assert response.status_code == 200
        assert "Error occurred: simple message" in str(response.body)

    @pytest.mark.asyncio
    async def test_error_handler_returns_list(self):
        """에러 핸들러가 리스트 반환"""

        class MultiError(Exception):
            def __init__(self, errors: list[str]):
                self.errors = errors
                super().__init__(str(errors))

        @Component
        class GlobalErrorHandlers:
            @ErrorHandler(MultiError)
            def handle_multi(self, error: MultiError) -> list:
                return [{"error": e} for e in error.errors]

        @Controller
        class TestController:
            @Get("/error")
            async def raise_error(self) -> str:
                raise MultiError(["error1", "error2", "error3"])

        app = Application("test").ready()

        response = await app.router.dispatch(HttpRequest(method="GET", path="/error"))
        assert response.status_code == 200
        assert "error1" in str(response.body)
        assert "error2" in str(response.body)
