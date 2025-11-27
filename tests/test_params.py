"""파라미터 인젝션 테스트"""

from dataclasses import dataclass

import pytest

from tests.conftest import Module, reset_container_manager

from vessel import Application, Component, Controller, Get, Post, RequestBody
from vessel.web.http import HttpRequest, HttpResponse


class TestRequestBodyResolver:
    """RequestBody[T] 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_request_body_with_dataclass(self, reset_container_manager):
        """dataclass를 RequestBody로 파싱"""

        @dataclass
        class UserData:
            name: str
            age: int

        class M:
            pass

        @Module(M)
        @Controller
        class UserController:
            @Post("/users")
            async def create_user(self, data: RequestBody[UserData]) -> dict:
                return {"name": data.name, "age": data.age}

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="POST",
            path="/users",
            body=b'{"name": "Alice", "age": 30}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"name": "Alice", "age": 30}

    @pytest.mark.asyncio
    async def test_request_body_with_pydantic(self, reset_container_manager):
        """pydantic BaseModel을 RequestBody로 파싱"""
        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("pydantic not installed")

        class CreateUserRequest(BaseModel):
            username: str
            email: str

        class M:
            pass

        @Module(M)
        @Controller
        class UserController:
            @Post("/users")
            async def create_user(self, body: RequestBody[CreateUserRequest]) -> dict:
                return {"username": body.username, "email": body.email}

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="POST",
            path="/users",
            body=b'{"username": "bob", "email": "bob@example.com"}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"username": "bob", "email": "bob@example.com"}


class TestListBodyResolver:
    """list[T] 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_list_of_dataclass(self, reset_container_manager):
        """list[dataclass] 파싱"""

        @dataclass
        class Address:
            city: str
            country: str

        class M:
            pass

        @Module(M)
        @Controller
        class AddressController:
            @Post("/addresses")
            async def bulk_create(self, addresses: list[Address]) -> dict:
                return {"count": len(addresses), "cities": [a.city for a in addresses]}

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="POST",
            path="/addresses",
            body=b'[{"city": "Seoul", "country": "Korea"}, {"city": "Tokyo", "country": "Japan"}]',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["count"] == 2
        assert response.body["cities"] == ["Seoul", "Tokyo"]

    @pytest.mark.asyncio
    async def test_list_of_pydantic(self, reset_container_manager):
        """list[pydantic.BaseModel] 파싱"""
        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("pydantic not installed")

        class Item(BaseModel):
            name: str
            price: float

        class M:
            pass

        @Module(M)
        @Controller
        class ItemController:
            @Post("/items/bulk")
            async def bulk_create(self, items: list[Item]) -> dict:
                total = sum(i.price for i in items)
                return {"count": len(items), "total": total}

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="POST",
            path="/items/bulk",
            body=b'[{"name": "apple", "price": 1.5}, {"name": "banana", "price": 0.8}]',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["count"] == 2
        assert response.body["total"] == 2.3


class TestPathParamResolver:
    """Path parameter 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_single_path_param(self, reset_container_manager):
        """단일 경로 파라미터"""

        class M:
            pass

        @Module(M)
        @Controller
        class UserController:
            @Get("/users/{id}")
            async def get_user(self, id: str) -> dict:
                return {"id": id}

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/users/123")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"id": "123"}

    @pytest.mark.asyncio
    async def test_multiple_path_params(self, reset_container_manager):
        """여러 경로 파라미터"""

        class M:
            pass

        @Module(M)
        @Controller
        class ResourceController:
            @Get("/users/{user_id}/posts/{post_id}")
            async def get_post(self, user_id: str, post_id: str) -> dict:
                return {"user_id": user_id, "post_id": post_id}

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/users/42/posts/99")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"user_id": "42", "post_id": "99"}

    @pytest.mark.asyncio
    async def test_path_param_with_int_type(self, reset_container_manager):
        """int 타입 경로 파라미터"""

        class M:
            pass

        @Module(M)
        @Controller
        class UserController:
            @Get("/users/{id}")
            async def get_user(self, id: int) -> dict:
                return {"id": id, "id_type": type(id).__name__}

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/users/123")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"id": 123, "id_type": "int"}


class TestQueryParamResolver:
    """Query parameter 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_query_params(self, reset_container_manager):
        """쿼리 파라미터 추출"""

        class M:
            pass

        @Module(M)
        @Controller
        class SearchController:
            @Get("/search")
            async def search(self, q: str, limit: int) -> dict:
                return {"query": q, "limit": limit}

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET",
            path="/search",
            query_params={"q": "hello", "limit": "10"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"query": "hello", "limit": 10}


class TestHttpRequestResolver:
    """HttpRequest 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_http_request_injection(self, reset_container_manager):
        """HttpRequest 주입"""

        class M:
            pass

        @Module(M)
        @Controller
        class InfoController:
            @Get("/info")
            async def info(self, request: HttpRequest) -> dict:
                return {
                    "method": request.method,
                    "path": request.path,
                    "headers": dict(request.headers),
                }

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET",
            path="/info",
            headers={"user-agent": "test"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["method"] == "GET"
        assert response.body["path"] == "/info"
        assert response.body["headers"]["user-agent"] == "test"


class TestMixedParameters:
    """여러 종류의 파라미터 혼합 테스트"""

    @pytest.mark.asyncio
    async def test_path_and_body_params(self, reset_container_manager):
        """경로 파라미터 + 바디 파라미터"""

        @dataclass
        class UpdateData:
            name: str

        class M:
            pass

        @Module(M)
        @Controller
        class UserController:
            @Post("/users/{id}")
            async def update_user(self, id: str, data: RequestBody[UpdateData]) -> dict:
                return {"id": id, "name": data.name}

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="POST",
            path="/users/42",
            body=b'{"name": "Updated"}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"id": "42", "name": "Updated"}

    @pytest.mark.asyncio
    async def test_path_query_and_request(self, reset_container_manager):
        """경로 + 쿼리 + HttpRequest 혼합"""

        class M:
            pass

        @Module(M)
        @Controller
        class MixedController:
            @Get("/resources/{id}")
            async def get_resource(
                self, id: str, format: str, request: HttpRequest
            ) -> dict:
                return {
                    "id": id,
                    "format": format,
                    "user_agent": request.headers.get("user-agent", "unknown"),
                }

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET",
            path="/resources/123",
            query_params={"format": "json"},
            headers={"user-agent": "test-client"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {
            "id": "123",
            "format": "json",
            "user_agent": "test-client",
        }
