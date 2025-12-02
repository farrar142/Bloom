"""Bloom pytest 플러그인

pytest 기반의 테스팅 지원을 제공합니다.

Usage:
    # conftest.py
    pytest_plugins = ["bloom.tests.pytest_plugin"]

    # 또는 pyproject.toml
    [tool.pytest.ini_options]
    asyncio_mode = "auto"

    # test_example.py
    from bloom.tests import BloomTestClient

    @pytest.fixture
    async def app():
        from bloom import Application, Component

        @Component
        class MyService:
            def get_data(self):
                return "data"

        app = Application("test").scan(MyService)
        await app.ready_async()
        return app

    async def test_service(app):
        service = app.manager.get_instance(MyService)
        assert service.get_data() == "data"

    async def test_http(app):
        async with BloomTestClient(app) as client:
            response = await client.get("/api/data")
            assert response.ok
            assert response.json() == {"data": "value"}
"""

from __future__ import annotations

import pytest
from typing import TYPE_CHECKING, Any, TypeVar, Callable, Awaitable
from contextlib import asynccontextmanager

if TYPE_CHECKING:
    from bloom.application import Application
    from bloom.core.manager import ContainerManager

T = TypeVar("T")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def bloom_app_factory():
    """Application 팩토리 fixture

    Usage:
        async def test_something(bloom_app_factory):
            app = await bloom_app_factory(MyComponent, MyService)
            service = app.manager.get_instance(MyService)
            assert service is not None
    """

    async def factory(*components, name: str = "test", config: dict | None = None):
        from bloom.application import Application

        app = Application(name)
        if config:
            app.load_config(config, source_type="dict")

        for component in components:
            app.scan(component)

        await app.ready_async()
        return app

    return factory


@pytest.fixture
def bloom_client_factory():
    """TestClient 팩토리 fixture

    Usage:
        async def test_http(bloom_client_factory, app):
            async with bloom_client_factory(app) as client:
                response = await client.get("/api/data")
                assert response.ok
    """

    @asynccontextmanager
    async def factory(app: "Application", **kwargs):
        from .client import TestClient

        client = TestClient(app, **kwargs)
        async with client as c:
            yield c

    return factory


# =============================================================================
# Test Client with Enhanced Assertions
# =============================================================================


class BloomTestClient:
    """향상된 Bloom 테스트 클라이언트

    체이닝 가능한 assertion 메서드를 제공합니다.

    Usage:
        async with BloomTestClient(app) as client:
            # 기본 사용
            response = await client.get("/api/users")
            assert response.ok
            assert response.json() == [{"id": 1}]

            # 체이닝 assertion
            (await client.get("/api/users"))
                .assert_ok()
                .assert_json([{"id": 1}])

            # POST with JSON
            (await client.post("/api/users", json={"name": "Alice"}))
                .assert_status(201)
                .assert_json_path("name", "Alice")
    """

    __test__ = False  # pytest가 테스트 클래스로 수집하지 않도록

    def __init__(
        self,
        app: "Application",
        base_url: str = "http://testserver",
        default_headers: dict[str, str] | None = None,
    ):
        from .client import TestClient

        self._client = TestClient(app, base_url, default_headers)
        self.app = app

    async def __aenter__(self) -> "BloomTestClient":
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    @property
    def manager(self) -> "ContainerManager":
        """ContainerManager 접근"""
        return self.app.manager

    def get_instance(self, type_: type[T]) -> T:
        """컨테이너에서 인스턴스 조회"""
        return self.manager.get_instance(type_)

    def get_instances(self, type_: type[T]) -> list[T]:
        """컨테이너에서 모든 인스턴스 조회"""
        return self.manager.get_instances(type_)

    # HTTP Methods
    async def get(self, path: str, **kwargs) -> "AssertableResponse":
        """GET 요청"""
        response = await self._client.get(path, **kwargs)
        return AssertableResponse(response)

    async def post(self, path: str, **kwargs) -> "AssertableResponse":
        """POST 요청"""
        response = await self._client.post(path, **kwargs)
        return AssertableResponse(response)

    async def put(self, path: str, **kwargs) -> "AssertableResponse":
        """PUT 요청"""
        response = await self._client.put(path, **kwargs)
        return AssertableResponse(response)

    async def patch(self, path: str, **kwargs) -> "AssertableResponse":
        """PATCH 요청"""
        response = await self._client.patch(path, **kwargs)
        return AssertableResponse(response)

    async def delete(self, path: str, **kwargs) -> "AssertableResponse":
        """DELETE 요청"""
        response = await self._client.delete(path, **kwargs)
        return AssertableResponse(response)

    async def request(self, method: str, path: str, **kwargs) -> "AssertableResponse":
        """임의 HTTP 요청"""
        response = await self._client.request(method, path, **kwargs)
        return AssertableResponse(response)

    # Cookie management
    def set_cookie(self, key: str, value: str) -> "BloomTestClient":
        """쿠키 설정 (체이닝)"""
        self._client.set_cookie(key, value)
        return self

    def clear_cookies(self) -> "BloomTestClient":
        """쿠키 초기화 (체이닝)"""
        self._client.clear_cookies()
        return self

    def set_header(self, key: str, value: str) -> "BloomTestClient":
        """기본 헤더 설정 (체이닝)"""
        self._client.default_headers[key] = value
        return self

    def set_auth(self, token: str, scheme: str = "Bearer") -> "BloomTestClient":
        """Authorization 헤더 설정 (체이닝)"""
        self._client.default_headers["Authorization"] = f"{scheme} {token}"
        return self


class AssertableResponse:
    """체이닝 가능한 assertion을 제공하는 응답 래퍼

    모든 assertion 메서드는 self를 반환하여 체이닝이 가능합니다.

    Usage:
        response = await client.get("/api/users")

        # 체이닝
        response.assert_ok().assert_json([{"id": 1}])

        # 개별 assertion
        response.assert_status(200)
        response.assert_header("Content-Type", "application/json")
        response.assert_json_path("data.users[0].name", "Alice")
    """

    __test__ = False

    def __init__(self, response):
        self._response = response

    # Response 속성 위임
    @property
    def status_code(self) -> int:
        return self._response.status_code

    @property
    def headers(self) -> dict[str, str]:
        return self._response.headers

    @property
    def body(self) -> bytes:
        return self._response.body

    @property
    def ok(self) -> bool:
        """2xx 상태 코드 여부"""
        return self._response.is_success

    @property
    def is_success(self) -> bool:
        return self._response.is_success

    @property
    def is_redirect(self) -> bool:
        return self._response.is_redirect

    @property
    def is_client_error(self) -> bool:
        return self._response.is_client_error

    @property
    def is_server_error(self) -> bool:
        return self._response.is_server_error

    def json(self) -> Any:
        """JSON 파싱"""
        return self._response.json()

    def text(self) -> str:
        """텍스트 디코딩"""
        return self._response.text()

    # ==========================================================================
    # Status Assertions
    # ==========================================================================

    def assert_status(
        self, expected: int, msg: str | None = None
    ) -> "AssertableResponse":
        """상태 코드 검증"""
        actual = self.status_code
        message = msg or f"Expected status {expected}, got {actual}"
        assert actual == expected, message
        return self

    def assert_ok(self, msg: str | None = None) -> "AssertableResponse":
        """2xx 상태 코드 검증"""
        message = msg or f"Expected 2xx status, got {self.status_code}"
        assert self.ok, message
        return self

    def assert_success(self, msg: str | None = None) -> "AssertableResponse":
        """assert_ok 별칭"""
        return self.assert_ok(msg)

    def assert_created(self, msg: str | None = None) -> "AssertableResponse":
        """201 상태 코드 검증"""
        return self.assert_status(201, msg or "Expected 201 Created")

    def assert_no_content(self, msg: str | None = None) -> "AssertableResponse":
        """204 상태 코드 검증"""
        return self.assert_status(204, msg or "Expected 204 No Content")

    def assert_redirect(self, msg: str | None = None) -> "AssertableResponse":
        """3xx 상태 코드 검증"""
        message = msg or f"Expected 3xx redirect, got {self.status_code}"
        assert self.is_redirect, message
        return self

    def assert_bad_request(self, msg: str | None = None) -> "AssertableResponse":
        """400 상태 코드 검증"""
        return self.assert_status(400, msg or "Expected 400 Bad Request")

    def assert_unauthorized(self, msg: str | None = None) -> "AssertableResponse":
        """401 상태 코드 검증"""
        return self.assert_status(401, msg or "Expected 401 Unauthorized")

    def assert_forbidden(self, msg: str | None = None) -> "AssertableResponse":
        """403 상태 코드 검증"""
        return self.assert_status(403, msg or "Expected 403 Forbidden")

    def assert_not_found(self, msg: str | None = None) -> "AssertableResponse":
        """404 상태 코드 검증"""
        return self.assert_status(404, msg or "Expected 404 Not Found")

    def assert_method_not_allowed(self, msg: str | None = None) -> "AssertableResponse":
        """405 상태 코드 검증"""
        return self.assert_status(405, msg or "Expected 405 Method Not Allowed")

    def assert_unprocessable(self, msg: str | None = None) -> "AssertableResponse":
        """422 상태 코드 검증"""
        return self.assert_status(422, msg or "Expected 422 Unprocessable Entity")

    def assert_server_error(self, msg: str | None = None) -> "AssertableResponse":
        """5xx 상태 코드 검증"""
        message = msg or f"Expected 5xx server error, got {self.status_code}"
        assert self.is_server_error, message
        return self

    # ==========================================================================
    # Header Assertions
    # ==========================================================================

    def assert_header(
        self, key: str, expected: str, msg: str | None = None
    ) -> "AssertableResponse":
        """헤더 값 검증"""
        actual = self.headers.get(key.lower())
        message = msg or f"Header '{key}': expected '{expected}', got '{actual}'"
        assert actual == expected, message
        return self

    def assert_header_contains(
        self, key: str, substring: str, msg: str | None = None
    ) -> "AssertableResponse":
        """헤더가 특정 문자열을 포함하는지 검증"""
        actual = self.headers.get(key.lower(), "")
        message = msg or f"Header '{key}' should contain '{substring}', got '{actual}'"
        assert substring in actual, message
        return self

    def assert_header_exists(
        self, key: str, msg: str | None = None
    ) -> "AssertableResponse":
        """헤더 존재 검증"""
        message = msg or f"Header '{key}' should exist"
        assert key.lower() in self.headers, message
        return self

    def assert_content_type(
        self, expected: str, msg: str | None = None
    ) -> "AssertableResponse":
        """Content-Type 검증"""
        return self.assert_header_contains("content-type", expected, msg)

    def assert_json_content_type(self, msg: str | None = None) -> "AssertableResponse":
        """JSON Content-Type 검증"""
        return self.assert_content_type("application/json", msg)

    # ==========================================================================
    # Body Assertions
    # ==========================================================================

    def assert_json(
        self, expected: Any, msg: str | None = None
    ) -> "AssertableResponse":
        """JSON 본문 전체 검증"""
        actual = self.json()
        message = msg or f"JSON body mismatch:\nExpected: {expected}\nActual: {actual}"
        assert actual == expected, message
        return self

    def assert_json_path(
        self, path: str, expected: Any, msg: str | None = None
    ) -> "AssertableResponse":
        """JSON 경로의 값 검증

        Args:
            path: dot notation 경로 (예: "data.users[0].name")
            expected: 예상 값
            msg: 커스텀 메시지
        """
        actual = self._get_json_path(path)
        message = msg or f"JSON path '{path}': expected {expected!r}, got {actual!r}"
        assert actual == expected, message
        return self

    def assert_json_has_key(
        self, key: str, msg: str | None = None
    ) -> "AssertableResponse":
        """JSON에 특정 키가 존재하는지 검증"""
        data = self.json()
        message = msg or f"JSON should have key '{key}'"
        assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}"
        assert key in data, message
        return self

    def assert_json_has_keys(
        self, *keys: str, msg: str | None = None
    ) -> "AssertableResponse":
        """JSON에 여러 키가 존재하는지 검증"""
        data = self.json()
        assert isinstance(data, dict), f"Expected dict, got {type(data).__name__}"
        missing = [k for k in keys if k not in data]
        message = msg or f"JSON missing keys: {missing}"
        assert not missing, message
        return self

    def assert_json_length(
        self, expected: int, path: str | None = None, msg: str | None = None
    ) -> "AssertableResponse":
        """JSON 배열 길이 검증"""
        data = self._get_json_path(path) if path else self.json()
        message = msg or f"Expected length {expected}, got {len(data)}"
        assert len(data) == expected, message
        return self

    def assert_json_contains(
        self, item: Any, msg: str | None = None
    ) -> "AssertableResponse":
        """JSON 배열에 특정 항목이 포함되어 있는지 검증"""
        data = self.json()
        message = msg or f"JSON array should contain {item!r}"
        assert item in data, message
        return self

    def assert_json_matches(
        self, predicate: Callable[[Any], bool], msg: str | None = None
    ) -> "AssertableResponse":
        """JSON이 조건을 만족하는지 검증"""
        data = self.json()
        message = msg or "JSON did not match predicate"
        assert predicate(data), message
        return self

    def assert_text(
        self, expected: str, msg: str | None = None
    ) -> "AssertableResponse":
        """텍스트 본문 검증"""
        actual = self.text()
        message = msg or f"Text body mismatch:\nExpected: {expected}\nActual: {actual}"
        assert actual == expected, message
        return self

    def assert_text_contains(
        self, substring: str, msg: str | None = None
    ) -> "AssertableResponse":
        """텍스트에 특정 문자열이 포함되어 있는지 검증"""
        actual = self.text()
        message = msg or f"Text should contain '{substring}'"
        assert substring in actual, message
        return self

    def assert_empty(self, msg: str | None = None) -> "AssertableResponse":
        """본문이 비어있는지 검증"""
        message = msg or f"Expected empty body, got {len(self.body)} bytes"
        assert len(self.body) == 0, message
        return self

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _get_json_path(self, path: str | None) -> Any:
        """dot notation 경로로 JSON 값 추출

        지원 형식:
        - "key" -> data["key"]
        - "key.subkey" -> data["key"]["subkey"]
        - "array[0]" -> data["array"][0]
        - "key.array[0].name" -> data["key"]["array"][0]["name"]
        """
        if path is None:
            return self.json()

        import re

        data = self.json()

        # 경로 파싱
        parts = re.split(r"\.(?![^\[]*\])", path)

        for part in parts:
            # 배열 인덱스 처리: "array[0]" -> ("array", 0)
            match = re.match(r"(\w+)\[(\d+)\]", part)
            if match:
                key, index = match.groups()
                data = data[key][int(index)]
            else:
                data = data[part]

        return data


# =============================================================================
# Assertion Helpers (standalone functions)
# =============================================================================


def assert_instance(obj: Any, type_: type[T], msg: str | None = None) -> T:
    """타입 검증 및 반환

    Usage:
        service = assert_instance(app.manager.get_instance(MyService), MyService)
    """
    message = msg or f"Expected {type_.__name__}, got {type(obj).__name__}"
    assert isinstance(obj, type_), message
    return obj


def assert_injected_field(
    obj: Any, field: str, type_: type[T] | None = None, msg: str | None = None
) -> T:
    """필드 주입 검증

    Usage:
        repo = assert_injected_field(service, "repository", Repository)
    """
    assert hasattr(obj, field), (
        msg or f"Field '{field}' not found in {type(obj).__name__}"
    )
    value = getattr(obj, field)
    assert value is not None, msg or f"Field '{field}' is None (not injected)"

    if type_ is not None:
        assert isinstance(value, type_), (
            msg
            or f"Field '{field}': expected {type_.__name__}, got {type(value).__name__}"
        )

    return value


def assert_container_exists(type_: type, msg: str | None = None) -> None:
    """컨테이너 존재 검증"""
    from bloom.core.container import Container

    container = Container.get_container(type_)
    message = msg or f"Container not found for {type_.__name__}"
    assert container is not None, message


def assert_raises_http(status_code: int):
    """HTTP 예외 검증 컨텍스트 매니저

    Usage:
        with assert_raises_http(404):
            await client.get("/not-found")
    """
    import pytest
    from bloom.core.exceptions import HttpException

    class HttpExceptionContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                raise AssertionError(
                    f"Expected HTTP {status_code} exception, but none was raised"
                )
            if not isinstance(exc_val, HttpException):
                return False
            if exc_val.status_code != status_code:
                raise AssertionError(
                    f"Expected HTTP {status_code}, got {exc_val.status_code}"
                )
            return True

    return HttpExceptionContext()
