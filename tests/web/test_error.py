"""에러 처리 테스트"""

import pytest
import json

from bloom.web.error import (
    HTTPException,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    MethodNotAllowedError,
    ConflictError,
    ValidationError,
    InternalServerError,
    UnprocessableEntityError,
    TooManyRequestsError,
    ExceptionHandler,
    ExceptionHandlerRegistry,
    json_error_response,
)
from bloom.web.middleware.error_handler import ErrorHandlerMiddleware, CORSMiddleware
from bloom.web import Request


# === Test Utilities ===


class MockReceive:
    def __init__(self, body: bytes = b""):
        self.body = body
        self._sent = False

    async def __call__(self):
        if not self._sent:
            self._sent = True
            return {"type": "http.request", "body": self.body, "more_body": False}
        return {"type": "http.disconnect"}


class MockSend:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def response_start(self):
        for msg in self.messages:
            if msg["type"] == "http.response.start":
                return msg
        return None

    @property
    def body(self) -> bytes:
        body_parts = []
        for msg in self.messages:
            if msg["type"] == "http.response.body":
                body_parts.append(msg.get("body", b""))
        return b"".join(body_parts)

    @property
    def status(self) -> int:
        start = self.response_start
        return start["status"] if start else 0

    def get_header(self, name: str) -> str | None:
        start = self.response_start
        if not start:
            return None
        headers = dict(start.get("headers", []))
        return headers.get(name.encode(), b"").decode()


def make_request(
    method: str = "GET",
    path: str = "/",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
    }
    return Request(scope, MockReceive())


# === HTTPException Tests ===


class TestHTTPExceptions:
    """HTTPException 계층 테스트"""

    def test_base_exception(self):
        """기본 HTTPException"""
        exc = HTTPException(status_code=500, detail="Server error")
        assert exc.status_code == 500
        assert exc.detail == "Server error"
        assert str(exc) == "Server error"

    def test_bad_request(self):
        """400 Bad Request"""
        exc = BadRequestError("Invalid input")
        assert exc.status_code == 400
        assert exc.detail == "Invalid input"

    def test_unauthorized(self):
        """401 Unauthorized"""
        exc = UnauthorizedError()
        assert exc.status_code == 401
        assert exc.detail == "Unauthorized"

    def test_forbidden(self):
        """403 Forbidden"""
        exc = ForbiddenError("Access denied")
        assert exc.status_code == 403
        assert exc.detail == "Access denied"

    def test_not_found(self):
        """404 Not Found"""
        exc = NotFoundError("User not found")
        assert exc.status_code == 404
        assert exc.detail == "User not found"

    def test_method_not_allowed(self):
        """405 Method Not Allowed"""
        exc = MethodNotAllowedError()
        assert exc.status_code == 405

    def test_conflict(self):
        """409 Conflict"""
        exc = ConflictError("Resource already exists")
        assert exc.status_code == 409

    def test_unprocessable_entity(self):
        """422 Unprocessable Entity"""
        exc = UnprocessableEntityError()
        assert exc.status_code == 422

    def test_too_many_requests(self):
        """429 Too Many Requests"""
        exc = TooManyRequestsError("Rate limit exceeded")
        assert exc.status_code == 429

    def test_internal_server_error(self):
        """500 Internal Server Error"""
        exc = InternalServerError()
        assert exc.status_code == 500

    def test_validation_error(self):
        """ValidationError with details"""
        errors = [
            {"field": "email", "message": "Invalid format"},
            {"field": "name", "message": "Required"},
        ]
        exc = ValidationError("Validation failed", errors=errors)

        assert exc.status_code == 422
        assert exc.errors == errors

        # to_dict 테스트
        result = exc.to_dict()
        assert result["error"]["details"] == errors

    def test_exception_to_dict(self):
        """예외를 딕셔너리로 변환"""
        exc = NotFoundError("Resource not found")
        result = exc.to_dict()

        assert result["error"]["status"] == 404
        assert result["error"]["message"] == "Resource not found"

    def test_exception_with_headers(self):
        """헤더가 있는 예외"""
        exc = UnauthorizedError(
            detail="Token expired", headers={"WWW-Authenticate": "Bearer"}
        )
        assert exc.headers == {"WWW-Authenticate": "Bearer"}


# === ExceptionHandler Tests ===


class TestExceptionHandler:
    """ExceptionHandler 데코레이터 테스트"""

    def test_decorator_adds_metadata(self):
        """데코레이터가 메타데이터 추가"""

        @ExceptionHandler(ValueError)
        async def handle_value_error(request, exc):
            return {"error": str(exc)}

        # 메타데이터 확인
        assert hasattr(handle_value_error, "__bloom_exception_handlers__")
        handlers = handle_value_error.__bloom_exception_handlers__
        assert len(handlers) == 1
        assert handlers[0]["exception_type"] == ValueError

    def test_multiple_exception_types(self):
        """여러 예외 타입 처리"""

        @ExceptionHandler(ValueError, TypeError)
        async def handle_errors(request, exc):
            return {"error": str(exc)}

        handlers = handle_errors.__bloom_exception_handlers__
        assert len(handlers) == 2
        exc_types = [h["exception_type"] for h in handlers]
        assert ValueError in exc_types
        assert TypeError in exc_types

    def test_handler_order(self):
        """핸들러 순서"""

        @ExceptionHandler(ValueError, order=10)
        async def handle_value_error(request, exc):
            return {"error": str(exc)}

        handlers = handle_value_error.__bloom_exception_handlers__
        assert handlers[0]["order"] == 10


class TestExceptionHandlerRegistry:
    """ExceptionHandlerRegistry 테스트"""

    def test_register_handler(self):
        """핸들러 등록"""
        registry = ExceptionHandlerRegistry()

        async def handle_value_error(request, exc):
            return {"error": str(exc)}

        registry.register(ValueError, handle_value_error)

        exc = ValueError("test error")
        handler = registry.find_handler(exc)
        assert handler is not None

    def test_handler_inheritance(self):
        """예외 상속 처리"""
        registry = ExceptionHandlerRegistry()

        async def handle_all(request, exc):
            return {"error": "handled"}

        registry.register(Exception, handle_all)

        # ValueError는 Exception의 하위 클래스
        exc = ValueError("test")
        handler = registry.find_handler(exc)
        assert handler is not None

    def test_find_most_specific_handler(self):
        """핸들러 등록 순서 우선"""
        registry = ExceptionHandlerRegistry()

        async def handle_exception(request, exc):
            return {"type": "exception"}

        async def handle_value_error(request, exc):
            return {"type": "value_error"}

        # 더 구체적인 ValueError 핸들러 먼저 등록
        registry.register(ValueError, handle_value_error)
        # 덜 구체적인 Exception 핸들러 나중에 등록
        registry.register(Exception, handle_exception)

        exc = ValueError("test")
        handler = registry.find_handler(exc)
        # 먼저 등록된 ValueError 핸들러가 선택됨
        assert handler == handle_value_error


# === json_error_response Tests ===


class TestJsonErrorResponse:
    """json_error_response 테스트"""

    @pytest.mark.asyncio
    async def test_http_exception_response(self):
        """HTTPException 응답 생성"""
        exc = NotFoundError("User not found")
        response = json_error_response(exc)

        send = MockSend()
        await response(None, None, send)

        assert send.status == 404
        body = json.loads(send.body.decode())
        assert body["error"]["message"] == "User not found"

    @pytest.mark.asyncio
    async def test_generic_exception_response(self):
        """일반 예외 응답 생성"""
        exc = ValueError("Something went wrong")
        response = json_error_response(exc)

        send = MockSend()
        await response(None, None, send)

        assert send.status == 500


# === ErrorHandlerMiddleware Tests ===


class TestErrorHandlerMiddleware:
    """ErrorHandlerMiddleware 테스트"""

    @pytest.mark.asyncio
    async def test_pass_through(self):
        """에러 없으면 통과"""

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"OK",
                }
            )

        middleware = ErrorHandlerMiddleware(app)

        scope = {"type": "http", "method": "GET", "path": "/"}
        send = MockSend()

        await middleware(scope, MockReceive(), send)

        assert send.status == 200

    @pytest.mark.asyncio
    async def test_catch_http_exception(self):
        """HTTPException 처리"""

        async def app(scope, receive, send):
            raise NotFoundError("Not found")

        middleware = ErrorHandlerMiddleware(app)

        scope = {"type": "http", "method": "GET", "path": "/"}
        send = MockSend()

        await middleware(scope, MockReceive(), send)

        assert send.status == 404
        body = json.loads(send.body.decode())
        assert "Not found" in body["error"]["message"]

    @pytest.mark.asyncio
    async def test_catch_generic_exception(self):
        """일반 예외 처리"""

        async def app(scope, receive, send):
            raise RuntimeError("Unexpected error")

        middleware = ErrorHandlerMiddleware(app, debug=False)

        scope = {"type": "http", "method": "GET", "path": "/"}
        send = MockSend()

        await middleware(scope, MockReceive(), send)

        assert send.status == 500

    @pytest.mark.asyncio
    async def test_debug_mode(self):
        """디버그 모드"""

        async def app(scope, receive, send):
            raise RuntimeError("Debug error message")

        middleware = ErrorHandlerMiddleware(app, debug=True)

        scope = {"type": "http", "method": "GET", "path": "/"}
        send = MockSend()

        await middleware(scope, MockReceive(), send)

        assert send.status == 500
        body = json.loads(send.body.decode())
        # 디버그 모드에서는 상세 정보 포함
        assert "Debug error message" in body["error"][
            "message"
        ] or "traceback" in body.get("error", {})


# === CORSMiddleware Tests ===


class TestCORSMiddleware:
    """CORSMiddleware 테스트"""

    @pytest.mark.asyncio
    async def test_cors_headers(self):
        """CORS 헤더 추가"""

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"OK",
                }
            )

        middleware = CORSMiddleware(
            app,
            allow_origins=["http://localhost:3000"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "headers": [(b"origin", b"http://localhost:3000")],
        }
        send = MockSend()

        await middleware(scope, MockReceive(), send)

        # CORS 헤더 확인
        headers = dict(send.response_start.get("headers", []))
        assert headers.get(b"access-control-allow-origin") == b"http://localhost:3000"

    @pytest.mark.asyncio
    async def test_preflight_request(self):
        """Preflight OPTIONS 요청 처리"""

        async def app(scope, receive, send):
            # 실제 앱이 호출되면 안 됨
            raise RuntimeError("Should not be called")

        middleware = CORSMiddleware(
            app,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Content-Type", "Authorization"],
        )

        scope = {
            "type": "http",
            "method": "OPTIONS",
            "path": "/api/test",
            "headers": [
                (b"origin", b"http://example.com"),
                (b"access-control-request-method", b"POST"),
            ],
        }
        send = MockSend()

        await middleware(scope, MockReceive(), send)

        # Preflight는 204 응답
        assert send.status in (200, 204)

        headers = dict(send.response_start.get("headers", []))
        assert b"access-control-allow-methods" in headers

    @pytest.mark.asyncio
    async def test_wildcard_origin(self):
        """와일드카드 Origin 처리"""

        async def app(scope, receive, send):
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b"OK",
                }
            )

        middleware = CORSMiddleware(app, allow_origins=["*"])

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"origin", b"http://any-origin.com")],
        }
        send = MockSend()

        await middleware(scope, MockReceive(), send)

        headers = dict(send.response_start.get("headers", []))
        assert headers.get(b"access-control-allow-origin") == b"*"
