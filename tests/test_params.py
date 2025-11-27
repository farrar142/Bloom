"""파라미터 인젝션 테스트"""

from dataclasses import dataclass

import pytest

from tests.conftest import Module, reset_container_manager

from vessel import (
    Application,
    Component,
    Controller,
    Get,
    Post,
    RequestBody,
    HttpHeader,
    HttpCookie,
)
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


class TestModelParamResolver:
    """마커 없는 dataclass/BaseModel 리졸버 테스트 (body[param_name] 추출)"""

    @pytest.mark.asyncio
    async def test_dataclass_from_body_key(self, reset_container_manager):
        """dataclass - body[param_name]에서 추출"""

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
            async def create_user(self, data: UserData) -> dict:
                return {"name": data.name, "age": data.age}

        app = Application("test").scan(M).ready()

        # body["data"]에서 UserData 생성
        request = HttpRequest(
            method="POST",
            path="/users",
            body=b'{"data": {"name": "Alice", "age": 30}}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"name": "Alice", "age": 30}

    @pytest.mark.asyncio
    async def test_pydantic_from_body_key(self, reset_container_manager):
        """pydantic BaseModel - body[param_name]에서 추출"""
        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("pydantic not installed")

        class Profile(BaseModel):
            nickname: str
            bio: str

        class M:
            pass

        @Module(M)
        @Controller
        class ProfileController:
            @Post("/profile")
            async def update(self, profile: Profile) -> dict:
                return {"nickname": profile.nickname, "bio": profile.bio}

        app = Application("test").scan(M).ready()

        # body["profile"]에서 Profile 생성
        request = HttpRequest(
            method="POST",
            path="/profile",
            body=b'{"profile": {"nickname": "alice", "bio": "Hello!"}}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"nickname": "alice", "bio": "Hello!"}

    @pytest.mark.asyncio
    async def test_multiple_models_from_body(self, reset_container_manager):
        """여러 모델을 각각의 body key에서 추출"""

        @dataclass
        class Author:
            name: str

        @dataclass
        class Book:
            title: str

        class M:
            pass

        @Module(M)
        @Controller
        class BookController:
            @Post("/books")
            async def create(self, author: Author, book: Book) -> dict:
                return {"author": author.name, "title": book.title}

        app = Application("test").scan(M).ready()

        # body["author"]와 body["book"]에서 각각 추출
        request = HttpRequest(
            method="POST",
            path="/books",
            body=b'{"author": {"name": "Kim"}, "book": {"title": "Python Guide"}}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"author": "Kim", "title": "Python Guide"}


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


class TestHttpHeaderResolver:
    """HttpHeader 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_header_by_param_name(self, reset_container_manager):
        """파라미터 이름으로 헤더 키 추론 (user_agent -> user-agent)"""

        class M:
            pass

        @Module(M)
        @Controller
        class HeaderController:
            @Get("/info")
            async def info(self, user_agent: HttpHeader) -> dict:
                return {
                    "key": user_agent.key,
                    "value": user_agent.value,
                }

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET",
            path="/info",
            headers={"user-agent": "Mozilla/5.0"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"key": "user-agent", "value": "Mozilla/5.0"}

    @pytest.mark.asyncio
    async def test_header_with_explicit_key(self, reset_container_manager):
        """정확한 헤더 키 지정"""

        class M:
            pass

        @Module(M)
        @Controller
        class HeaderController:
            @Get("/info")
            async def info(self, ua: HttpHeader["User-Agent"]) -> dict:
                return {"key": ua.key, "value": ua.value}

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET",
            path="/info",
            headers={"user-agent": "Chrome/100"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"key": "User-Agent", "value": "Chrome/100"}

    @pytest.mark.asyncio
    async def test_multiple_headers(self, reset_container_manager):
        """여러 헤더 추출"""

        class M:
            pass

        @Module(M)
        @Controller
        class HeaderController:
            @Get("/info")
            async def info(
                self,
                content_type: HttpHeader,
                accept: HttpHeader["Accept"],
            ) -> dict:
                return {
                    "content_type": content_type.value,
                    "accept": accept.value,
                }

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET",
            path="/info",
            headers={"content-type": "application/json", "accept": "text/html"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {
            "content_type": "application/json",
            "accept": "text/html",
        }


class TestHttpCookieResolver:
    """HttpCookie 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_cookie_by_param_name(self, reset_container_manager):
        """파라미터 이름으로 쿠키 키 추론"""

        class M:
            pass

        @Module(M)
        @Controller
        class CookieController:
            @Get("/session")
            async def session(self, session_id: HttpCookie) -> dict:
                return {"key": session_id.key, "value": session_id.value}

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET",
            path="/session",
            headers={"cookie": "session_id=abc123; user=john"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"key": "session_id", "value": "abc123"}

    @pytest.mark.asyncio
    async def test_cookie_with_explicit_key(self, reset_container_manager):
        """정확한 쿠키 키 지정 - KeyValue 반환"""

        class M:
            pass

        @Module(M)
        @Controller
        class CookieController:
            @Get("/token")
            async def token(self, t: HttpCookie["auth_token"]) -> dict:
                return {"key": t.key, "value": t.value}

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET",
            path="/token",
            headers={"cookie": "auth_token=xyz789; other=value"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"key": "auth_token", "value": "xyz789"}

    @pytest.mark.asyncio
    async def test_multiple_cookies(self, reset_container_manager):
        """여러 쿠키 추출 - KeyValue 반환"""

        class M:
            pass

        @Module(M)
        @Controller
        class CookieController:
            @Get("/auth")
            async def auth(
                self,
                session_id: HttpCookie,
                token: HttpCookie["auth_token"],
            ) -> dict:
                return {
                    "session_key": session_id.key,
                    "session_value": session_id.value,
                    "token_key": token.key,
                    "token_value": token.value,
                }

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET",
            path="/auth",
            headers={"cookie": "session_id=sess123; auth_token=tok456"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {
            "session_key": "session_id",
            "session_value": "sess123",
            "token_key": "auth_token",
            "token_value": "tok456",
        }
