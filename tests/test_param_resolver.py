"""Parameter Resolver 테스트"""

from __future__ import annotations
import pytest
from typing import Annotated, Any, Literal
from dataclasses import dataclass

from bloom.web.request import HttpRequest
from bloom.web.route import RouteMatch, Route
from bloom.web.resolver import (
    ResolverRegistry,
    ParameterInfo,
    PathVariableResolver,
    QueryResolver,
    RequestBodyResolver,
    RequestFieldResolver,
    HeaderResolver,
    CookieResolver,
    ImplicitVariableResolver,
)
from bloom.web.params import (
    PathVariable,
    PathVariableMarker,
    Query,
    QueryMarker,
    RequestBody,
    RequestBodyMarker,
    RequestField,
    RequestFieldMarker,
    Header,
    HeaderMarker,
    Cookie,
    CookieMarker,
    KeyValue,
    get_param_marker,
)


# =============================================================================
# Test Fixtures
# =============================================================================


def create_mock_request(
    method: str = "GET",
    path: str = "/",
    query_string: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    cookies: dict[str, str] | None = None,
) -> HttpRequest:
    """테스트용 Mock Request 생성"""
    raw_headers = []
    if headers:
        for key, value in headers.items():
            raw_headers.append((key.lower().encode("latin-1"), value.encode("latin-1")))

    # 쿠키 헤더 추가
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_str.encode("latin-1")))

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string.encode("utf-8"),
        "headers": raw_headers,
    }

    body_sent = False

    async def receive():
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    return HttpRequest(scope, receive)


def create_mock_route_match(
    path_params: dict[str, str] | None = None,
) -> RouteMatch:
    """테스트용 Mock RouteMatch 생성"""

    async def dummy_handler():
        pass

    route = Route(path="/test", method="GET", handler=dummy_handler, name="test")
    return RouteMatch(route=route, path_params=path_params or {})


def create_param_info(
    name: str,
    annotation: Any,
    default: Any = None,
    has_default: bool = False,
    is_optional: bool = False,
) -> ParameterInfo:
    """테스트용 ParameterInfo 생성"""
    actual_type, marker = get_param_marker(annotation)
    return ParameterInfo(
        name=name,
        annotation=annotation,
        actual_type=actual_type,
        marker=marker,
        default=default,
        has_default=has_default,
        is_optional=is_optional,
    )


# =============================================================================
# PathVariableResolver Tests
# =============================================================================


class TestPathVariableResolver:
    """PathVariableResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return PathVariableResolver()

    @pytest.mark.asyncio
    async def test_resolve_string_path_variable(self, resolver):
        """문자열 경로 변수 추출"""
        request = create_mock_request(path="/users/john")
        match = create_mock_route_match(path_params={"name": "john"})
        param = create_param_info("name", PathVariable[str])

        result = await resolver.resolve(param, request, match)
        assert result == "john"

    @pytest.mark.asyncio
    async def test_resolve_int_path_variable(self, resolver):
        """정수 경로 변수 추출 및 타입 변환"""
        request = create_mock_request(path="/users/123")
        match = create_mock_route_match(path_params={"user_id": "123"})
        param = create_param_info("user_id", PathVariable[int])

        result = await resolver.resolve(param, request, match)
        assert result == 123
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_resolve_float_path_variable(self, resolver):
        """실수 경로 변수 추출 및 타입 변환"""
        request = create_mock_request(path="/price/19.99")
        match = create_mock_route_match(path_params={"price": "19.99"})
        param = create_param_info("price", PathVariable[float])

        result = await resolver.resolve(param, request, match)
        assert result == 19.99
        assert isinstance(result, float)

    @pytest.mark.asyncio
    async def test_resolve_bool_path_variable(self, resolver):
        """불리언 경로 변수 추출 및 타입 변환"""
        request = create_mock_request()
        match = create_mock_route_match(path_params={"active": "true"})
        param = create_param_info("active", PathVariable[bool])

        result = await resolver.resolve(param, request, match)
        assert result is True

    @pytest.mark.asyncio
    async def test_resolve_missing_path_variable_with_default(self, resolver):
        """기본값이 있는 경우 누락된 경로 변수 처리"""
        request = create_mock_request()
        match = create_mock_route_match(path_params={})
        param = create_param_info(
            "user_id", PathVariable[int], default=0, has_default=True
        )

        result = await resolver.resolve(param, request, match)
        assert result == 0

    @pytest.mark.asyncio
    async def test_resolve_missing_path_variable_optional(self, resolver):
        """Optional인 경우 누락된 경로 변수 처리"""
        request = create_mock_request()
        match = create_mock_route_match(path_params={})
        param = create_param_info("user_id", PathVariable[int], is_optional=True)

        result = await resolver.resolve(param, request, match)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_missing_path_variable_raises_error(self, resolver):
        """필수 경로 변수 누락 시 에러"""
        request = create_mock_request()
        match = create_mock_route_match(path_params={})
        param = create_param_info("user_id", PathVariable[int])

        with pytest.raises(ValueError, match="Path variable 'user_id' not found"):
            await resolver.resolve(param, request, match)

    @pytest.mark.asyncio
    async def test_resolve_with_custom_name(self, resolver):
        """커스텀 이름으로 경로 변수 추출"""
        request = create_mock_request()
        match = create_mock_route_match(path_params={"id": "456"})
        param = create_param_info(
            "user_id", Annotated[int, PathVariableMarker(name="id")]
        )

        result = await resolver.resolve(param, request, match)
        assert result == 456


# =============================================================================
# QueryResolver Tests
# =============================================================================


class TestQueryResolver:
    """QueryResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return QueryResolver()

    @pytest.mark.asyncio
    async def test_resolve_string_query_param(self, resolver):
        """문자열 쿼리 파라미터 추출"""
        request = create_mock_request(query_string="name=john")
        match = create_mock_route_match()
        param = create_param_info("name", Query[str])

        result = await resolver.resolve(param, request, match)
        assert result == "john"

    @pytest.mark.asyncio
    async def test_resolve_int_query_param(self, resolver):
        """정수 쿼리 파라미터 추출 및 타입 변환"""
        request = create_mock_request(query_string="page=5")
        match = create_mock_route_match()
        param = create_param_info("page", Query[int])

        result = await resolver.resolve(param, request, match)
        assert result == 5
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_resolve_multiple_query_params(self, resolver):
        """여러 쿼리 파라미터 추출"""
        request = create_mock_request(query_string="page=1&size=20")
        match = create_mock_route_match()

        page_param = create_param_info("page", Query[int])
        size_param = create_param_info("size", Query[int])

        page_result = await resolver.resolve(page_param, request, match)
        size_result = await resolver.resolve(size_param, request, match)

        assert page_result == 1
        assert size_result == 20

    @pytest.mark.asyncio
    async def test_resolve_missing_query_param_with_default(self, resolver):
        """기본값이 있는 경우 누락된 쿼리 파라미터 처리"""
        request = create_mock_request(query_string="")
        match = create_mock_route_match()
        param = create_param_info("page", Query[int], default=1, has_default=True)

        result = await resolver.resolve(param, request, match)
        assert result == 1

    @pytest.mark.asyncio
    async def test_resolve_missing_query_param_optional(self, resolver):
        """Optional인 경우 누락된 쿼리 파라미터 처리"""
        request = create_mock_request(query_string="")
        match = create_mock_route_match()
        param = create_param_info("filter", Query[str], is_optional=True)

        result = await resolver.resolve(param, request, match)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_missing_query_param_raises_error(self, resolver):
        """필수 쿼리 파라미터 누락 시 에러"""
        request = create_mock_request(query_string="")
        match = create_mock_route_match()
        param = create_param_info("page", Query[int])

        with pytest.raises(ValueError, match="Query parameter 'page' not found"):
            await resolver.resolve(param, request, match)

    @pytest.mark.asyncio
    async def test_resolve_bool_query_param_true_values(self, resolver):
        """불리언 쿼리 파라미터 true 값들"""
        for true_value in ["true", "1", "yes"]:
            request = create_mock_request(query_string=f"active={true_value}")
            match = create_mock_route_match()
            param = create_param_info("active", Query[bool])

            result = await resolver.resolve(param, request, match)
            assert result is True, f"Expected True for '{true_value}'"

    @pytest.mark.asyncio
    async def test_resolve_bool_query_param_false_values(self, resolver):
        """불리언 쿼리 파라미터 false 값들"""
        for false_value in ["false", "0", "no"]:
            request = create_mock_request(query_string=f"active={false_value}")
            match = create_mock_route_match()
            param = create_param_info("active", Query[bool])

            result = await resolver.resolve(param, request, match)
            assert result is False, f"Expected False for '{false_value}'"

    @pytest.mark.asyncio
    async def test_resolve_with_custom_name(self, resolver):
        """커스텀 이름으로 쿼리 파라미터 추출"""
        request = create_mock_request(query_string="q=search_term")
        match = create_mock_route_match()
        param = create_param_info("query", Annotated[str, QueryMarker(name="q")])

        result = await resolver.resolve(param, request, match)
        assert result == "search_term"


# =============================================================================
# RequestBodyResolver Tests
# =============================================================================


class TestRequestBodyResolver:
    """RequestBodyResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return RequestBodyResolver()

    @pytest.mark.asyncio
    async def test_resolve_dict_body(self, resolver):
        """dict로 body 추출"""
        body = b'{"name": "john", "age": 30}'
        request = create_mock_request(
            method="POST",
            body=body,
            headers={"content-type": "application/json"},
        )
        match = create_mock_route_match()
        param = create_param_info("data", RequestBody[dict])

        result = await resolver.resolve(param, request, match)
        assert result == {"name": "john", "age": 30}

    @pytest.mark.asyncio
    async def test_resolve_dataclass_body(self, resolver):
        """dataclass로 body 추출"""

        @dataclass
        class UserData:
            name: str
            age: int

        body = b'{"name": "john", "age": 30}'
        request = create_mock_request(
            method="POST",
            body=body,
            headers={"content-type": "application/json"},
        )
        match = create_mock_route_match()
        param = create_param_info("user", Annotated[UserData, RequestBodyMarker()])

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, UserData)
        assert result.name == "john"
        assert result.age == 30

    @pytest.mark.asyncio
    async def test_resolve_empty_body_with_default(self, resolver):
        """기본값이 있는 경우 빈 body 처리"""
        request = create_mock_request(method="POST", body=b"")
        match = create_mock_route_match()
        param = create_param_info(
            "data", RequestBody[dict], default={}, has_default=True
        )

        result = await resolver.resolve(param, request, match)
        assert result == {}

    @pytest.mark.asyncio
    async def test_resolve_empty_body_optional(self, resolver):
        """Optional인 경우 빈 body 처리"""
        request = create_mock_request(method="POST", body=b"")
        match = create_mock_route_match()
        param = create_param_info("data", RequestBody[dict], is_optional=True)

        result = await resolver.resolve(param, request, match)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_empty_body_raises_error(self, resolver):
        """필수 body 누락 시 에러"""
        request = create_mock_request(method="POST", body=b"")
        match = create_mock_route_match()
        param = create_param_info("data", RequestBody[dict])

        with pytest.raises(ValueError, match="Request body is empty"):
            await resolver.resolve(param, request, match)


# =============================================================================
# RequestFieldResolver Tests
# =============================================================================


class TestRequestFieldResolver:
    """RequestFieldResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return RequestFieldResolver()

    @pytest.mark.asyncio
    async def test_resolve_string_field(self, resolver):
        """문자열 필드 추출"""
        body = b'{"username": "john", "email": "john@example.com"}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info("username", RequestField[str])

        result = await resolver.resolve(param, request, match)
        assert result == "john"

    @pytest.mark.asyncio
    async def test_resolve_int_field(self, resolver):
        """정수 필드 추출"""
        body = b'{"count": 42}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info("count", RequestField[int])

        result = await resolver.resolve(param, request, match)
        assert result == 42

    @pytest.mark.asyncio
    async def test_resolve_nested_dataclass_field(self, resolver):
        """중첩된 dataclass 필드 추출"""

        @dataclass
        class Address:
            city: str
            zip_code: str

        body = b'{"address": {"city": "Seoul", "zip_code": "12345"}}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info("address", Annotated[Address, RequestFieldMarker()])

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, Address)
        assert result.city == "Seoul"
        assert result.zip_code == "12345"

    @pytest.mark.asyncio
    async def test_resolve_missing_field_with_default(self, resolver):
        """기본값이 있는 경우 누락된 필드 처리"""
        body = b'{"name": "john"}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info("age", RequestField[int], default=0, has_default=True)

        result = await resolver.resolve(param, request, match)
        assert result == 0

    @pytest.mark.asyncio
    async def test_resolve_missing_field_optional(self, resolver):
        """Optional인 경우 누락된 필드 처리"""
        body = b'{"name": "john"}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info("nickname", RequestField[str], is_optional=True)

        result = await resolver.resolve(param, request, match)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_missing_field_raises_error(self, resolver):
        """필수 필드 누락 시 에러"""
        body = b'{"name": "john"}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info("email", RequestField[str])

        with pytest.raises(ValueError, match="Field 'email' not found in request body"):
            await resolver.resolve(param, request, match)

    @pytest.mark.asyncio
    async def test_resolve_with_custom_field_name(self, resolver):
        """커스텀 필드명으로 추출"""
        body = b'{"userName": "john"}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info(
            "user_name", Annotated[str, RequestFieldMarker(name="userName")]
        )

        result = await resolver.resolve(param, request, match)
        assert result == "john"


# =============================================================================
# HeaderResolver Tests
# =============================================================================


class TestHeaderResolver:
    """HeaderResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return HeaderResolver()

    @pytest.mark.asyncio
    async def test_resolve_header_with_custom_name(self, resolver):
        """커스텀 이름으로 헤더 추출"""
        request = create_mock_request(headers={"Authorization": "Bearer token123"})
        match = create_mock_route_match()
        param = create_param_info(
            "auth", Annotated[str, HeaderMarker(name="Authorization")]
        )

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, KeyValue)
        assert result.key == "Authorization"
        assert result.value == "Bearer token123"

    @pytest.mark.asyncio
    async def test_resolve_header_snake_case_conversion(self, resolver):
        """snake_case 파라미터 이름이 Header-Case로 변환"""
        request = create_mock_request(headers={"User-Agent": "TestClient/1.0"})
        match = create_mock_route_match()
        param = create_param_info("user_agent", Header)

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, KeyValue)
        assert result.key == "User-Agent"
        assert result.value == "TestClient/1.0"

    @pytest.mark.asyncio
    async def test_resolve_header_with_literal_name(self, resolver):
        """Literal 타입으로 헤더 이름 지정"""
        request = create_mock_request(headers={"X-Custom-Header": "custom_value"})
        match = create_mock_route_match()
        param = create_param_info("custom", Header[Literal["X-Custom-Header"]])

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, KeyValue)
        assert result.key == "X-Custom-Header"
        assert result.value == "custom_value"

    @pytest.mark.asyncio
    async def test_resolve_missing_header_with_default(self, resolver):
        """기본값이 있는 경우 누락된 헤더 처리"""
        request = create_mock_request(headers={})
        match = create_mock_route_match()
        param = create_param_info(
            "auth",
            Annotated[str, HeaderMarker(name="Authorization")],
            default="",
            has_default=True,
        )

        result = await resolver.resolve(param, request, match)
        assert result == ""

    @pytest.mark.asyncio
    async def test_resolve_missing_header_optional(self, resolver):
        """Optional인 경우 누락된 헤더 처리"""
        request = create_mock_request(headers={})
        match = create_mock_route_match()
        param = create_param_info(
            "auth", Annotated[str, HeaderMarker(name="Authorization")], is_optional=True
        )

        result = await resolver.resolve(param, request, match)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_missing_header_raises_error(self, resolver):
        """필수 헤더 누락 시 에러"""
        request = create_mock_request(headers={})
        match = create_mock_route_match()
        param = create_param_info(
            "auth", Annotated[str, HeaderMarker(name="Authorization")]
        )

        with pytest.raises(ValueError, match="Header 'Authorization' not found"):
            await resolver.resolve(param, request, match)

    @pytest.mark.asyncio
    async def test_resolve_header_marker_class_directly(self, resolver):
        """Header 마커 클래스를 직접 사용 (제네릭 없이)"""
        request = create_mock_request(headers={"Content-Type": "application/json"})
        match = create_mock_route_match()
        param = create_param_info("content_type", Header)

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, KeyValue)
        assert result.key == "Content-Type"
        assert result.value == "application/json"


# =============================================================================
# CookieResolver Tests
# =============================================================================


class TestCookieResolver:
    """CookieResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return CookieResolver()

    @pytest.mark.asyncio
    async def test_resolve_cookie_by_param_name(self, resolver):
        """파라미터 이름으로 쿠키 추출"""
        request = create_mock_request(cookies={"session_id": "abc123"})
        match = create_mock_route_match()
        param = create_param_info("session_id", Cookie[str])

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, KeyValue)
        assert result.key == "session_id"
        assert result.value == "abc123"

    @pytest.mark.asyncio
    async def test_resolve_cookie_with_custom_name(self, resolver):
        """커스텀 이름으로 쿠키 추출"""
        request = create_mock_request(cookies={"auth_token": "xyz789"})
        match = create_mock_route_match()
        param = create_param_info(
            "token", Annotated[str, CookieMarker(name="auth_token")]
        )

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, KeyValue)
        assert result.key == "auth_token"
        assert result.value == "xyz789"

    @pytest.mark.asyncio
    async def test_resolve_cookie_with_literal_name(self, resolver):
        """Literal 타입으로 쿠키 이름 지정"""
        request = create_mock_request(cookies={"X-AUTH-TOKEN": "secret"})
        match = create_mock_route_match()
        param = create_param_info("auth", Cookie[Literal["X-AUTH-TOKEN"]])

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, KeyValue)
        assert result.key == "X-AUTH-TOKEN"
        assert result.value == "secret"

    @pytest.mark.asyncio
    async def test_resolve_missing_cookie_with_default(self, resolver):
        """기본값이 있는 경우 누락된 쿠키 처리"""
        request = create_mock_request(cookies={})
        match = create_mock_route_match()
        param = create_param_info(
            "session_id", Cookie[str], default="", has_default=True
        )

        result = await resolver.resolve(param, request, match)
        assert result == ""

    @pytest.mark.asyncio
    async def test_resolve_missing_cookie_optional(self, resolver):
        """Optional인 경우 누락된 쿠키 처리"""
        request = create_mock_request(cookies={})
        match = create_mock_route_match()
        param = create_param_info("session_id", Cookie[str], is_optional=True)

        result = await resolver.resolve(param, request, match)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_missing_cookie_raises_error(self, resolver):
        """필수 쿠키 누락 시 에러"""
        request = create_mock_request(cookies={})
        match = create_mock_route_match()
        param = create_param_info("session_id", Cookie[str])

        with pytest.raises(ValueError, match="Cookie 'session_id' not found"):
            await resolver.resolve(param, request, match)

    @pytest.mark.asyncio
    async def test_resolve_cookie_marker_class_directly(self, resolver):
        """Cookie 마커 클래스를 직접 사용 (제네릭 없이)"""
        request = create_mock_request(cookies={"theme": "dark"})
        match = create_mock_route_match()
        param = create_param_info("theme", Cookie)

        result = await resolver.resolve(param, request, match)
        assert isinstance(result, KeyValue)
        assert result.key == "theme"
        assert result.value == "dark"

    @pytest.mark.asyncio
    async def test_resolve_multiple_cookies(self, resolver):
        """여러 쿠키 추출"""
        request = create_mock_request(
            cookies={"session": "sess123", "user": "john", "theme": "light"}
        )
        match = create_mock_route_match()

        session_param = create_param_info("session", Cookie[str])
        user_param = create_param_info("user", Cookie[str])
        theme_param = create_param_info("theme", Cookie[str])

        session = await resolver.resolve(session_param, request, match)
        user = await resolver.resolve(user_param, request, match)
        theme = await resolver.resolve(theme_param, request, match)

        assert session.value == "sess123"
        assert user.value == "john"
        assert theme.value == "light"


# =============================================================================
# ImplicitVariableResolver Tests
# =============================================================================


class TestImplicitVariableResolver:
    """ImplicitVariableResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return ImplicitVariableResolver()

    @pytest.mark.asyncio
    async def test_resolve_from_path_params(self, resolver):
        """path_params에서 값 추출"""
        request = create_mock_request(path="/users/123")
        match = create_mock_route_match(path_params={"user_id": "123"})
        param = create_param_info("user_id", int)
        # marker가 None이어야 ImplicitVariableResolver가 처리
        param = ParameterInfo(
            name="user_id",
            annotation=int,
            actual_type=int,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        result = await resolver.resolve(param, request, match)
        assert result == 123

    @pytest.mark.asyncio
    async def test_resolve_from_query_params(self, resolver):
        """query_params에서 값 추출"""
        request = create_mock_request(query_string="page=5")
        match = create_mock_route_match()
        param = ParameterInfo(
            name="page",
            annotation=int,
            actual_type=int,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        result = await resolver.resolve(param, request, match)
        assert result == 5

    @pytest.mark.asyncio
    async def test_resolve_from_body(self, resolver):
        """body에서 값 추출"""
        body = b'{"name": "john"}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = ParameterInfo(
            name="name",
            annotation=str,
            actual_type=str,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        result = await resolver.resolve(param, request, match)
        assert result == "john"

    @pytest.mark.asyncio
    async def test_resolve_path_params_priority_over_query(self, resolver):
        """path_params가 query_params보다 우선"""
        request = create_mock_request(query_string="id=999")
        match = create_mock_route_match(path_params={"id": "123"})
        param = ParameterInfo(
            name="id",
            annotation=int,
            actual_type=int,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        result = await resolver.resolve(param, request, match)
        assert result == 123  # path_params의 값

    @pytest.mark.asyncio
    async def test_resolve_with_default_when_not_found(self, resolver):
        """값을 찾지 못하면 기본값 사용"""
        request = create_mock_request()
        match = create_mock_route_match()
        param = ParameterInfo(
            name="missing",
            annotation=int,
            actual_type=int,
            marker=None,
            default=42,
            has_default=True,
            is_optional=False,
        )

        result = await resolver.resolve(param, request, match)
        assert result == 42

    @pytest.mark.asyncio
    async def test_resolve_optional_returns_none(self, resolver):
        """Optional이고 값을 찾지 못하면 None 반환"""
        request = create_mock_request()
        match = create_mock_route_match()
        param = ParameterInfo(
            name="missing",
            annotation=int,
            actual_type=int,
            marker=None,
            default=None,
            has_default=False,
            is_optional=True,
        )

        result = await resolver.resolve(param, request, match)
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_raises_error_when_required_not_found(self, resolver):
        """필수 파라미터를 찾지 못하면 에러"""
        request = create_mock_request()
        match = create_mock_route_match()
        param = ParameterInfo(
            name="required_param",
            annotation=int,
            actual_type=int,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        with pytest.raises(ValueError, match="Parameter 'required_param' not found"):
            await resolver.resolve(param, request, match)


# =============================================================================
# ResolverRegistry Tests
# =============================================================================


class TestResolverRegistry:
    """ResolverRegistry 테스트"""

    @pytest.fixture
    def registry(self):
        return ResolverRegistry()

    def test_find_resolver_for_path_variable(self, registry):
        """PathVariable 리졸버 찾기"""
        param = create_param_info("id", PathVariable[int])
        resolver = registry.find_resolver(param)
        assert isinstance(resolver, PathVariableResolver)

    def test_find_resolver_for_query(self, registry):
        """Query 리졸버 찾기"""
        param = create_param_info("page", Query[int])
        resolver = registry.find_resolver(param)
        assert isinstance(resolver, QueryResolver)

    def test_find_resolver_for_request_body(self, registry):
        """RequestBody 리졸버 찾기"""
        param = create_param_info("data", RequestBody[dict])
        resolver = registry.find_resolver(param)
        assert isinstance(resolver, RequestBodyResolver)

    def test_find_resolver_for_request_field(self, registry):
        """RequestField 리졸버 찾기"""
        param = create_param_info("username", RequestField[str])
        resolver = registry.find_resolver(param)
        assert isinstance(resolver, RequestFieldResolver)

    def test_find_resolver_for_header(self, registry):
        """Header 리졸버 찾기"""
        param = create_param_info("authorization", Header[str])
        resolver = registry.find_resolver(param)
        assert isinstance(resolver, HeaderResolver)

    def test_find_resolver_for_cookie(self, registry):
        """Cookie 리졸버 찾기"""
        param = create_param_info("session", Cookie[str])
        resolver = registry.find_resolver(param)
        assert isinstance(resolver, CookieResolver)

    def test_find_resolver_for_implicit_variable(self, registry):
        """암시적 변수 리졸버 찾기"""
        param = ParameterInfo(
            name="id",
            annotation=int,
            actual_type=int,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )
        resolver = registry.find_resolver(param)
        assert isinstance(resolver, ImplicitVariableResolver)

    @pytest.mark.asyncio
    async def test_resolve_parameters_integration(self, registry):
        """핸들러 파라미터 전체 해결 통합 테스트"""
        body = b'{"field": 100}'
        request = create_mock_request(
            method="POST",
            path="/users/42",
            query_string="page=1",
            headers={"Authorization": "Bearer token"},
            body=body,
            cookies={"session": "sess123"},
        )
        match = create_mock_route_match(path_params={"user_id": "42"})

        async def handler(
            user_id: PathVariable[int],
            page: Query[int],
            field: RequestField[int],
            auth: Annotated[str, HeaderMarker(name="Authorization")],
            session: Cookie[str],
        ) -> dict:
            return {}

        result = await registry.resolve_parameters(handler, request, match)

        assert result["user_id"] == 42
        assert result["page"] == 1
        assert result["field"] == 100
        assert result["auth"].value == "Bearer token"
        assert result["session"].value == "sess123"


# =============================================================================
# Edge Cases and Special Scenarios
# =============================================================================


class TestEdgeCases:
    """엣지 케이스 테스트"""

    @pytest.mark.asyncio
    async def test_empty_query_string(self):
        """빈 쿼리 스트링"""
        resolver = QueryResolver()
        request = create_mock_request(query_string="")
        match = create_mock_route_match()
        param = create_param_info("page", Query[int], default=1, has_default=True)

        result = await resolver.resolve(param, request, match)
        assert result == 1

    @pytest.mark.asyncio
    async def test_special_characters_in_query_param(self):
        """쿼리 파라미터의 특수 문자"""
        resolver = QueryResolver()
        request = create_mock_request(query_string="search=hello%20world")
        match = create_mock_route_match()
        param = create_param_info("search", Query[str])

        result = await resolver.resolve(param, request, match)
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_unicode_in_path_variable(self):
        """경로 변수의 유니코드"""
        resolver = PathVariableResolver()
        request = create_mock_request(path="/users/김철수")
        match = create_mock_route_match(path_params={"name": "김철수"})
        param = create_param_info("name", PathVariable[str])

        result = await resolver.resolve(param, request, match)
        assert result == "김철수"

    @pytest.mark.asyncio
    async def test_header_case_insensitivity(self):
        """헤더 대소문자 무관"""
        resolver = HeaderResolver()
        request = create_mock_request(headers={"content-type": "application/json"})
        match = create_mock_route_match()
        param = create_param_info(
            "content_type", Annotated[str, HeaderMarker(name="Content-Type")]
        )

        result = await resolver.resolve(param, request, match)
        assert result.value == "application/json"

    @pytest.mark.asyncio
    async def test_json_body_with_nested_objects(self):
        """중첩된 JSON 객체"""
        resolver = RequestBodyResolver()
        body = b'{"user": {"name": "john", "profile": {"age": 30}}}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info("data", RequestBody[dict])

        result = await resolver.resolve(param, request, match)
        assert result["user"]["name"] == "john"
        assert result["user"]["profile"]["age"] == 30

    @pytest.mark.asyncio
    async def test_json_body_with_array(self):
        """배열이 포함된 JSON body"""
        resolver = RequestBodyResolver()
        body = b'{"items": [1, 2, 3], "tags": ["a", "b"]}'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info("data", RequestBody[dict])

        result = await resolver.resolve(param, request, match)
        assert result["items"] == [1, 2, 3]
        assert result["tags"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_cookie_with_equals_in_value(self):
        """쿠키 값에 = 포함"""
        request = create_mock_request(cookies={"token": "abc=def=ghi"})
        match = create_mock_route_match()
        resolver = CookieResolver()
        param = create_param_info("token", Cookie[str])

        result = await resolver.resolve(param, request, match)
        assert result.value == "abc=def=ghi"

    @pytest.mark.asyncio
    async def test_int_conversion_error(self):
        """정수 변환 실패"""
        resolver = PathVariableResolver()
        request = create_mock_request()
        match = create_mock_route_match(path_params={"id": "not_a_number"})
        param = create_param_info("id", PathVariable[int])

        with pytest.raises(ValueError):
            await resolver.resolve(param, request, match)

    @pytest.mark.asyncio
    async def test_float_conversion_error(self):
        """실수 변환 실패"""
        resolver = QueryResolver()
        request = create_mock_request(query_string="price=invalid")
        match = create_mock_route_match()
        param = create_param_info("price", Query[float])

        with pytest.raises(ValueError):
            await resolver.resolve(param, request, match)

    @pytest.mark.asyncio
    async def test_malformed_json_body(self):
        """잘못된 형식의 JSON body"""
        resolver = RequestBodyResolver()
        body = b'{"invalid json'
        request = create_mock_request(method="POST", body=body)
        match = create_mock_route_match()
        param = create_param_info("data", RequestBody[dict])

        with pytest.raises(Exception):  # json.JSONDecodeError
            await resolver.resolve(param, request, match)


# =============================================================================
# get_param_marker Function Tests
# =============================================================================


class TestGetParamMarker:
    """get_param_marker 함수 테스트"""

    def test_path_variable_generic(self):
        """PathVariable[int] 형태"""
        actual_type, marker = get_param_marker(PathVariable[int])
        assert actual_type is int
        assert isinstance(marker, PathVariableMarker)

    def test_query_generic(self):
        """Query[str] 형태"""
        actual_type, marker = get_param_marker(Query[str])
        assert actual_type is str
        assert isinstance(marker, QueryMarker)

    def test_annotated_with_marker(self):
        """Annotated[str, QueryMarker()] 형태"""
        actual_type, marker = get_param_marker(
            Annotated[str, QueryMarker(name="custom")]
        )
        assert actual_type is str
        assert isinstance(marker, QueryMarker)
        assert marker.name == "custom"

    def test_plain_type(self):
        """일반 타입 (마커 없음)"""
        actual_type, marker = get_param_marker(str)
        assert actual_type is str
        assert marker is None

    def test_marker_class_directly(self):
        """마커 클래스 직접 사용 (예: Header)"""
        actual_type, marker = get_param_marker(Header)
        assert actual_type is str
        assert isinstance(marker, HeaderMarker)

    def test_cookie_class_directly(self):
        """Cookie 클래스 직접 사용"""
        actual_type, marker = get_param_marker(Cookie)
        assert actual_type is str
        assert isinstance(marker, CookieMarker)

    def test_cookie_with_literal(self):
        """Cookie[Literal["name"]] 형태"""
        actual_type, marker = get_param_marker(Cookie[Literal["session_id"]])
        assert actual_type == KeyValue[str]
        assert isinstance(marker, CookieMarker)
        assert marker.name == "session_id"

    def test_header_with_literal(self):
        """Header[Literal["name"]] 형태"""
        actual_type, marker = get_param_marker(Header[Literal["X-Custom"]])
        assert actual_type == KeyValue[str]
        assert isinstance(marker, HeaderMarker)
        assert marker.name == "X-Custom"
