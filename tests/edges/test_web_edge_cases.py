"""Web Layer 엣지 케이스 테스트"""

import pytest
from dataclasses import dataclass
from typing import Optional

from bloom import (
    Application,
    Component,
    Controller,
    Get,
    Post,
    RequestBody,
    HttpHeader,
    HttpCookie,
)
from bloom.web.http import HttpRequest, HttpResponse


class TestEmptyRequestBody:
    """빈 요청 바디 테스트"""

    @pytest.mark.asyncio
    async def test_empty_json_body(self, reset_container_manager):
        """빈 JSON 바디 {}"""

        @dataclass
        class EmptyModel:
            pass

        @Controller
        class EmptyBodyController:
            @Post("/empty")
            async def handle_empty(self, body: RequestBody[EmptyModel]) -> dict:
                return {"received": True}

        app = Application("empty_body").scan(EmptyBodyController).ready()

        request = HttpRequest(
            method="POST",
            path="/empty",
            body=b"{}",
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_optional_body_with_null(self, reset_container_manager):
        """Optional body에 null 전달"""

        @Controller
        class NullBodyController:
            @Post("/null")
            async def handle_null(
                self, body: RequestBody[Optional[dict]] = None
            ) -> dict:
                return {"body": body}

        app = Application("null_body").scan(NullBodyController).ready()

        request = HttpRequest(
            method="POST",
            path="/null",
            body=b"null",
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200


class TestSpecialCharactersInPath:
    """경로의 특수 문자 테스트"""

    @pytest.mark.asyncio
    async def test_korean_in_path_param(self, reset_container_manager):
        """경로 파라미터에 한글"""

        @Controller
        class KoreanPathController:
            @Get("/users/{name}")
            async def get_user(self, name: str) -> dict:
                return {"name": name}

        app = Application("korean_path").scan(KoreanPathController).ready()

        request = HttpRequest(method="GET", path="/users/홍길동")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["name"] == "홍길동"

    @pytest.mark.asyncio
    async def test_url_encoded_path_param(self, reset_container_manager):
        """URL 인코딩된 경로 파라미터"""

        @Controller
        class EncodedPathController:
            @Get("/files/{filename}")
            async def get_file(self, filename: str) -> dict:
                return {"filename": filename}

        app = Application("encoded_path").scan(EncodedPathController).ready()

        # URL 인코딩된 경로
        request = HttpRequest(method="GET", path="/files/my%20file.txt")
        response = await app.router.dispatch(request)

        assert response.status_code == 200


class TestQueryParamEdgeCases:
    """쿼리 파라미터 엣지 케이스 테스트"""

    @pytest.mark.asyncio
    async def test_query_param_basic(self, reset_container_manager):
        """기본 쿼리 파라미터"""

        @Controller
        class QueryController:
            @Get("/items")
            async def get_items(self, id: str) -> dict:
                return {"id": id}

        app = Application("query_param").scan(QueryController).ready()

        request = HttpRequest(
            method="GET",
            path="/items",
            query_params={"id": "test123"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["id"] == "test123"

    @pytest.mark.asyncio
    async def test_multiple_query_params(self, reset_container_manager):
        """여러 쿼리 파라미터"""

        @Controller
        class MultiQueryController:
            @Get("/search")
            async def search(self, q: str, limit: int) -> dict:
                return {"q": q, "limit": limit}

        app = Application("multi_query").scan(MultiQueryController).ready()

        request = HttpRequest(
            method="GET",
            path="/search",
            query_params={"q": "hello", "limit": "10"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["q"] == "hello"
        assert response.body["limit"] == 10


class TestMissingRequiredParams:
    """필수 파라미터 누락 테스트"""

    @pytest.mark.asyncio
    async def test_missing_required_query_param(self, reset_container_manager):
        """필수 쿼리 파라미터 누락"""

        @Controller
        class RequiredQueryController:
            @Get("/items")
            async def get_items(self, id: str) -> dict:
                return {"id": id}

        app = Application("required_query").scan(RequiredQueryController).ready()

        request = HttpRequest(method="GET", path="/items")
        response = await app.router.dispatch(request)

        # 필수 파라미터 누락 시 500 Internal Server Error (프레임워크 현재 동작)
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_optional_query_param_default(self, reset_container_manager):
        """Optional 쿼리 파라미터 기본값"""

        @Controller
        class OptionalQueryController:
            @Get("/items")
            async def get_items(self, id: Optional[str] = None) -> dict:
                return {"id": id}

        app = Application("optional_query").scan(OptionalQueryController).ready()

        request = HttpRequest(method="GET", path="/items")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["id"] is None


class TestHeaderEdgeCases:
    """헤더 엣지 케이스 테스트"""

    @pytest.mark.asyncio
    async def test_header_basic(self, reset_container_manager):
        """기본 헤더 추출"""

        @Controller
        class HeaderController:
            @Get("/check")
            async def check(self, accept: HttpHeader["Accept"]) -> dict:
                return {"accept": accept.value}

        app = Application("header_basic").scan(HeaderController).ready()

        request = HttpRequest(
            method="GET",
            path="/check",
            headers={"accept": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_custom_header_name(self, reset_container_manager):
        """커스텀 헤더 이름"""

        @Controller
        class CustomHeaderController:
            @Get("/check")
            async def check(self, token: HttpHeader["X-Custom-Token"]) -> dict:
                return {"token": token.value}

        app = Application("custom_header").scan(CustomHeaderController).ready()

        request = HttpRequest(
            method="GET",
            path="/check",
            headers={"x-custom-token": "my-token"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["token"] == "my-token"


class TestRouteConflicts:
    """라우트 충돌 테스트"""

    @pytest.mark.asyncio
    async def test_static_vs_dynamic_route(self, reset_container_manager):
        """정적 경로 vs 동적 경로 - 정적 우선"""

        @Controller
        class RouteController:
            @Get("/users/me")
            async def get_current_user(self) -> dict:
                return {"user": "current"}

            @Get("/users/{id}")
            async def get_user(self, id: str) -> dict:
                return {"user": id}

        app = Application("route_conflict").scan(RouteController).ready()

        # 정적 경로 우선
        request1 = HttpRequest(method="GET", path="/users/me")
        response1 = await app.router.dispatch(request1)
        assert response1.body["user"] == "current"

        # 동적 경로
        request2 = HttpRequest(method="GET", path="/users/123")
        response2 = await app.router.dispatch(request2)
        assert response2.body["user"] == "123"


class TestResponseEdgeCases:
    """응답 엣지 케이스 테스트"""

    @pytest.mark.asyncio
    async def test_return_none(self, reset_container_manager):
        """None 반환"""

        @Controller
        class NoneController:
            @Get("/none")
            async def return_none(self) -> None:
                return None

        app = Application("none_return").scan(NoneController).ready()

        request = HttpRequest(method="GET", path="/none")
        response = await app.router.dispatch(request)

        # None 반환 시 200 OK (프레임워크 현재 동작)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_return_empty_dict(self, reset_container_manager):
        """빈 딕셔너리 반환"""

        @Controller
        class EmptyDictController:
            @Get("/empty")
            async def return_empty(self) -> dict:
                return {}

        app = Application("empty_dict").scan(EmptyDictController).ready()

        request = HttpRequest(method="GET", path="/empty")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {}

    @pytest.mark.asyncio
    async def test_return_string(self, reset_container_manager):
        """문자열 반환"""

        @Controller
        class StringController:
            @Get("/text")
            async def return_text(self) -> str:
                return "Hello, World!"

        app = Application("string_return").scan(StringController).ready()

        request = HttpRequest(method="GET", path="/text")
        response = await app.router.dispatch(request)

        assert response.status_code == 200


class TestLongUrl:
    """긴 URL 테스트"""

    @pytest.mark.asyncio
    async def test_very_long_path(self, reset_container_manager):
        """매우 긴 경로"""

        @Controller
        class LongPathController:
            @Get("/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p")
            async def deep_nested(self) -> dict:
                return {"depth": 16}

        app = Application("long_path").scan(LongPathController).ready()

        request = HttpRequest(method="GET", path="/a/b/c/d/e/f/g/h/i/j/k/l/m/n/o/p")
        response = await app.router.dispatch(request)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_long_query_string(self, reset_container_manager):
        """긴 쿼리 문자열"""

        @Controller
        class LongQueryController:
            @Get("/search")
            async def search(self, q: str) -> dict:
                return {"length": len(q)}

        app = Application("long_query").scan(LongQueryController).ready()

        long_query = "a" * 1000
        request = HttpRequest(
            method="GET",
            path="/search",
            query_params={"q": long_query},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["length"] == 1000


class TestMethodNotAllowed:
    """허용되지 않은 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_wrong_http_method(self, reset_container_manager):
        """잘못된 HTTP 메서드"""

        @Controller
        class GetOnlyController:
            @Get("/resource")
            async def get_resource(self) -> dict:
                return {"method": "GET"}

        app = Application("wrong_method").scan(GetOnlyController).ready()

        request = HttpRequest(method="POST", path="/resource")
        response = await app.router.dispatch(request)

        # 잘못된 HTTP 메서드는 404 반환 (프레임워크 현재 동작)
        assert response.status_code == 404


class TestNotFound:
    """404 Not Found 테스트"""

    @pytest.mark.asyncio
    async def test_path_not_found(self, reset_container_manager):
        """존재하지 않는 경로"""

        @Controller
        class SomeController:
            @Get("/exists")
            async def exists(self) -> dict:
                return {"exists": True}

        app = Application("not_found").scan(SomeController).ready()

        request = HttpRequest(method="GET", path="/does-not-exist")
        response = await app.router.dispatch(request)

        assert response.status_code == 404
