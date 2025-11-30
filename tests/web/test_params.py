"""파라미터 인젝션 테스트"""

from dataclasses import dataclass

import pytest


from bloom import (
    Application,
    Component,
    Controller,
    Get,
    Post,
    RequestBody,
    HttpHeader,
    HttpCookie,
    UploadedFile,
)
from bloom.web.http import HttpRequest, HttpResponse


class TestRequestBodyResolver:
    """RequestBody[T] 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_request_body_with_dataclass(self, reset_container_manager):
        """dataclass를 RequestBody로 파싱"""

        @dataclass
        class UserData:
            name: str
            age: int

        @Controller
        class UserController:
            @Post("/users")
            async def create_user(self, data: RequestBody[UserData]) -> dict:
                return {"name": data.name, "age": data.age}

        app = Application("test").ready()

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

        @Controller
        class UserController:
            @Post("/users")
            async def create_user(self, body: RequestBody[CreateUserRequest]) -> dict:
                return {"username": body.username, "email": body.email}

        app = Application("test").ready()

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

        @Controller
        class UserController:
            @Post("/users")
            async def create_user(self, data: UserData) -> dict:
                return {"name": data.name, "age": data.age}

        app = Application("test").ready()

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

        @Controller
        class ProfileController:
            @Post("/profile")
            async def update(self, profile: Profile) -> dict:
                return {"nickname": profile.nickname, "bio": profile.bio}

        app = Application("test").ready()

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

        @Controller
        class BookController:
            @Post("/books")
            async def create(self, author: Author, book: Book) -> dict:
                return {"author": author.name, "title": book.title}

        app = Application("test").ready()

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

        @Controller
        class AddressController:
            @Post("/addresses")
            async def bulk_create(self, addresses: list[Address]) -> dict:
                return {"count": len(addresses), "cities": [a.city for a in addresses]}

        app = Application("test").ready()

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

        @Controller
        class ItemController:
            @Post("/items/bulk")
            async def bulk_create(self, items: list[Item]) -> dict:
                total = sum(i.price for i in items)
                return {"count": len(items), "total": total}

        app = Application("test").ready()

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

        @Controller
        class UserController:
            @Get("/users/{id}")
            async def get_user(self, id: str) -> dict:
                return {"id": id}

        app = Application("test").ready()

        request = HttpRequest(method="GET", path="/users/123")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"id": "123"}

    @pytest.mark.asyncio
    async def test_multiple_path_params(self, reset_container_manager):
        """여러 경로 파라미터"""

        @Controller
        class ResourceController:
            @Get("/users/{user_id}/posts/{post_id}")
            async def get_post(self, user_id: str, post_id: str) -> dict:
                return {"user_id": user_id, "post_id": post_id}

        app = Application("test").ready()

        request = HttpRequest(method="GET", path="/users/42/posts/99")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"user_id": "42", "post_id": "99"}

    @pytest.mark.asyncio
    async def test_path_param_with_int_type(self, reset_container_manager):
        """int 타입 경로 파라미터"""

        @Controller
        class UserController:
            @Get("/users/{id}")
            async def get_user(self, id: int) -> dict:
                return {"id": id, "id_type": type(id).__name__}

        app = Application("test").ready()

        request = HttpRequest(method="GET", path="/users/123")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"id": 123, "id_type": "int"}


class TestQueryParamResolver:
    """Query parameter 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_query_params(self, reset_container_manager):
        """쿼리 파라미터 추출"""

        @Controller
        class SearchController:
            @Get("/search")
            async def search(self, q: str, limit: int) -> dict:
                return {"query": q, "limit": limit}

        app = Application("test").ready()

        request = HttpRequest(
            method="GET",
            path="/search",
            query_params={"q": "hello", "limit": "10"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"query": "hello", "limit": 10}

    @pytest.mark.asyncio
    async def test_primitive_params_from_body(self, reset_container_manager):
        """body에서 기본 타입 파라미터 추출"""

        @Controller
        class UserController:
            @Post("/users")
            async def create_user(self, name: str, age: int) -> dict:
                return {"name": name, "age": age}

        app = Application("test").ready()

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
    async def test_mixed_query_and_body_params(self, reset_container_manager):
        """query와 body 혼합 - query 우선"""

        @Controller
        class MixedController:
            @Post("/items")
            async def create(self, name: str, quantity: int) -> dict:
                return {"name": name, "quantity": quantity}

        app = Application("test").ready()

        # name은 query에서, quantity는 body에서
        request = HttpRequest(
            method="POST",
            path="/items",
            query_params={"name": "from_query"},
            body=b'{"name": "from_body", "quantity": 5}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"name": "from_query", "quantity": 5}


class TestHttpRequestResolver:
    """HttpRequest 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_http_request_injection(self, reset_container_manager):
        """HttpRequest 주입"""

        @Controller
        class InfoController:
            @Get("/info")
            async def info(self, request: HttpRequest) -> dict:
                return {
                    "method": request.method,
                    "path": request.path,
                    "headers": dict(request.headers),
                }

        app = Application("test").ready()

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

        @Controller
        class UserController:
            @Post("/users/{id}")
            async def update_user(self, id: str, data: RequestBody[UpdateData]) -> dict:
                return {"id": id, "name": data.name}

        app = Application("test").ready()

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

        app = Application("test").ready()

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

        @Controller
        class HeaderController:
            @Get("/info")
            async def info(self, user_agent: HttpHeader) -> dict:
                return {
                    "key": user_agent.key,
                    "value": user_agent.value,
                }

        app = Application("test").ready()

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

        @Controller
        class HeaderController:
            @Get("/info")
            async def info(self, ua: HttpHeader["User-Agent"]) -> dict:
                return {"key": ua.key, "value": ua.value}

        app = Application("test").ready()

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

        app = Application("test").ready()

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

        @Controller
        class CookieController:
            @Get("/session")
            async def session(self, session_id: HttpCookie) -> dict:
                return {"key": session_id.key, "value": session_id.value}

        app = Application("test").ready()

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

        @Controller
        class CookieController:
            @Get("/token")
            async def token(self, t: HttpCookie["auth_token"]) -> dict:
                return {"key": t.key, "value": t.value}

        app = Application("test").ready()

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

        app = Application("test").ready()

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


class TestUploadedFileResolver:
    """UploadedFile 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_single_file_by_param_name(self, reset_container_manager):
        """파라미터 이름으로 단일 파일 추출"""

        @Controller
        class UploadController:
            @Post("/upload")
            async def upload(self, file: UploadedFile) -> dict:
                return {
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "size": file.size,
                }

        app = Application("test").ready()

        uploaded = UploadedFile(
            filename="test.txt",
            content_type="text/plain",
            content=b"Hello, World!",
        )
        request = HttpRequest(
            method="POST",
            path="/upload",
            files={"file": [uploaded]},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {
            "filename": "test.txt",
            "content_type": "text/plain",
            "size": 13,
        }

    @pytest.mark.asyncio
    async def test_single_file_with_explicit_field(self, reset_container_manager):
        """지정된 필드명으로 단일 파일 추출"""

        @Controller
        class UploadController:
            @Post("/avatar")
            async def upload_avatar(self, image: UploadedFile["avatar"]) -> dict:
                return {"filename": image.filename}

        app = Application("test").ready()

        uploaded = UploadedFile(
            filename="profile.png",
            content_type="image/png",
            content=b"\x89PNG...",
        )
        request = HttpRequest(
            method="POST",
            path="/avatar",
            files={"avatar": [uploaded]},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"filename": "profile.png"}

    @pytest.mark.asyncio
    async def test_multiple_files_by_param_name(self, reset_container_manager):
        """파라미터 이름으로 여러 파일 추출"""

        @Controller
        class UploadController:
            @Post("/upload-multiple")
            async def upload_many(self, files: list[UploadedFile]) -> dict:
                return {
                    "count": len(files),
                    "filenames": [f.filename for f in files],
                }

        app = Application("test").ready()

        file1 = UploadedFile(
            filename="doc1.pdf",
            content_type="application/pdf",
            content=b"PDF1...",
        )
        file2 = UploadedFile(
            filename="doc2.pdf",
            content_type="application/pdf",
            content=b"PDF2...",
        )
        request = HttpRequest(
            method="POST",
            path="/upload-multiple",
            files={"files": [file1, file2]},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {
            "count": 2,
            "filenames": ["doc1.pdf", "doc2.pdf"],
        }

    @pytest.mark.asyncio
    async def test_multiple_files_with_explicit_field(self, reset_container_manager):
        """지정된 필드명으로 여러 파일 추출"""

        @Controller
        class UploadController:
            @Post("/gallery")
            async def upload_images(self, photos: list[UploadedFile["images"]]) -> dict:
                return {"count": len(photos)}

        app = Application("test").ready()

        img1 = UploadedFile(
            filename="photo1.jpg",
            content_type="image/jpeg",
            content=b"JPEG1...",
        )
        img2 = UploadedFile(
            filename="photo2.jpg",
            content_type="image/jpeg",
            content=b"JPEG2...",
        )
        request = HttpRequest(
            method="POST",
            path="/gallery",
            files={"images": [img1, img2]},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"count": 2}

    @pytest.mark.asyncio
    async def test_file_content_access(self, reset_container_manager):
        """파일 내용 접근"""

        @Controller
        class UploadController:
            @Post("/read")
            async def read_file(self, file: UploadedFile) -> dict:
                return {"content": file.content.decode("utf-8")}

        app = Application("test").ready()

        uploaded = UploadedFile(
            filename="message.txt",
            content_type="text/plain",
            content=b"Hello from file!",
        )
        request = HttpRequest(
            method="POST",
            path="/read",
            files={"file": [uploaded]},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"content": "Hello from file!"}


class TestOptionalParameters:
    """Optional 파라미터 테스트"""

    @pytest.mark.asyncio
    async def test_optional_query_param(self, reset_container_manager):
        """Optional 쿼리 파라미터"""

        @Controller
        class SearchController:
            @Get("/search")
            async def search(self, q: str, limit: int | None = None) -> dict:
                return {"q": q, "limit": limit}

        app = Application("test").ready()

        # limit 없이 요청
        request = HttpRequest(
            method="GET",
            path="/search",
            query_params={"q": "hello"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"q": "hello", "limit": None}

        # limit 있는 요청
        request2 = HttpRequest(
            method="GET",
            path="/search",
            query_params={"q": "hello", "limit": "10"},
        )
        response2 = await app.router.dispatch(request2)

        assert response2.status_code == 200
        assert response2.body == {"q": "hello", "limit": 10}

    @pytest.mark.asyncio
    async def test_optional_header(self, reset_container_manager):
        """Optional 헤더"""

        @Controller
        class HeaderController:
            @Get("/info")
            async def info(self, authorization: HttpHeader | None = None) -> dict:
                if authorization is None:
                    return {"auth": None}
                return {"auth": authorization.value}

        app = Application("test").ready()

        # 헤더 없이
        request = HttpRequest(method="GET", path="/info")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"auth": None}

        # 헤더 있이
        request2 = HttpRequest(
            method="GET",
            path="/info",
            headers={"authorization": "Bearer token123"},
        )
        response2 = await app.router.dispatch(request2)

        assert response2.status_code == 200
        assert response2.body == {"auth": "Bearer token123"}

    @pytest.mark.asyncio
    async def test_optional_cookie(self, reset_container_manager):
        """Optional 쿠키"""

        @Controller
        class CookieController:
            @Get("/session")
            async def session(self, session_id: HttpCookie | None = None) -> dict:
                if session_id is None:
                    return {"session": None}
                return {"session": session_id.value}

        app = Application("test").ready()

        # 쿠키 없이
        request = HttpRequest(method="GET", path="/session")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"session": None}

    @pytest.mark.asyncio
    async def test_optional_model(self, reset_container_manager):
        """Optional dataclass/BaseModel"""

        @dataclass
        class Metadata:
            key: str

        @dataclass
        class Data:
            value: str

        @Controller
        class DataController:
            @Post("/data")
            async def create(
                self, data: Data, metadata: Metadata | None = None
            ) -> dict:
                if metadata is None:
                    return {"data": data.value, "metadata": None}
                return {"data": data.value, "metadata": metadata.key}

        app = Application("test").ready()

        # metadata 없이
        request = HttpRequest(
            method="POST",
            path="/data",
            body=b'{"data": {"value": "hello"}}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"data": "hello", "metadata": None}

    @pytest.mark.asyncio
    async def test_optional_uploaded_file(self, reset_container_manager):
        """Optional UploadedFile"""

        @Controller
        class UploadController:
            @Post("/upload")
            async def upload(self, file: UploadedFile | None = None) -> dict:
                if file is None:
                    return {"uploaded": False}
                return {"uploaded": True, "filename": file.filename}

        app = Application("test").ready()

        # 파일 없이
        request = HttpRequest(method="POST", path="/upload")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"uploaded": False}


class TestAuthenticationResolver:
    """Authentication 리졸버 테스트"""

    @pytest.mark.asyncio
    async def test_authentication_injection(self, reset_container_manager):
        """Authentication 주입"""
        from bloom.web.auth import Authentication

        @Controller
        class UserController:
            @Get("/me")
            async def me(self, auth: Authentication) -> dict:
                return {
                    "user_id": auth.user_id,
                    "authenticated": auth.authenticated,
                }

        app = Application("test").ready()

        # auth가 설정된 request
        auth = Authentication(user_id="user123", authenticated=True)
        request = HttpRequest(method="GET", path="/me", auth=auth)
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["user_id"] == "user123"
        assert response.body["authenticated"] is True

    @pytest.mark.asyncio
    async def test_authentication_none_when_not_set(self, reset_container_manager):
        """Authentication이 설정되지 않으면 None"""
        from bloom.web.auth import Authentication

        @Controller
        class UserController:
            @Get("/me")
            async def me(self, auth: Authentication) -> dict:
                if auth is None:
                    return {"authenticated": False}
                return {"authenticated": auth.authenticated}

        app = Application("test").ready()

        # auth 없이
        request = HttpRequest(method="GET", path="/me")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["authenticated"] is False

    @pytest.mark.asyncio
    async def test_optional_authentication(self, reset_container_manager):
        """Optional[Authentication] 주입"""
        from bloom.web.auth import Authentication

        @Controller
        class UserController:
            @Get("/me")
            async def me(self, auth: Authentication | None) -> dict:
                if auth is None:
                    return {"guest": True}
                return {"user_id": auth.user_id}

        app = Application("test").ready()

        # auth 없이
        request = HttpRequest(method="GET", path="/me")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"guest": True}

        # auth 있을 때
        auth = Authentication(user_id="user456", authenticated=True)
        request = HttpRequest(method="GET", path="/me", auth=auth)
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"user_id": "user456"}

    @pytest.mark.asyncio
    async def test_authentication_with_authorities(self, reset_container_manager):
        """authorities 포함한 Authentication 주입"""
        from bloom.web.auth import Authentication

        @Controller
        class AdminController:
            @Get("/admin")
            async def admin(self, auth: Authentication) -> dict:
                return {
                    "user_id": auth.user_id,
                    "is_admin": "ADMIN" in auth.authorities,
                    "authorities": auth.authorities,
                }

        app = Application("test").ready()

        auth = Authentication(
            user_id="admin1",
            authenticated=True,
            authorities=["USER", "ADMIN"],
        )
        request = HttpRequest(method="GET", path="/admin", auth=auth)
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["user_id"] == "admin1"
        assert response.body["is_admin"] is True
        assert response.body["authorities"] == ["USER", "ADMIN"]

    @pytest.mark.asyncio
    async def test_authentication_with_request_and_path_param(
        self, reset_container_manager
    ):
        """Authentication + HttpRequest + path param 조합"""
        from bloom.web.auth import Authentication

        @Controller
        class PostController:
            @Get("/posts/{id}")
            async def get_post(
                self, id: str, auth: Authentication, request: HttpRequest
            ) -> dict:
                return {
                    "post_id": id,
                    "viewer": auth.user_id if auth else None,
                    "method": request.method,
                }

        app = Application("test").ready()

        auth = Authentication(user_id="viewer1", authenticated=True)
        request = HttpRequest(method="GET", path="/posts/123", auth=auth)
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["post_id"] == "123"
        assert response.body["viewer"] == "viewer1"
        assert response.body["method"] == "GET"


class TestValidationError:
    """ValidationError 처리 테스트"""

    @pytest.mark.asyncio
    async def test_pydantic_validation_error_simple(self, reset_container_manager):
        """pydantic 단순 필드 유효성 검사 실패"""
        try:
            from pydantic import BaseModel, Field
        except ImportError:
            pytest.skip("pydantic not installed")

        class CreateUserRequest(BaseModel):
            username: str = Field(min_length=3)
            email: str
            age: int = Field(ge=0, le=150)

        @Controller
        class UserController:
            @Post("/users")
            async def create_user(self, body: RequestBody[CreateUserRequest]) -> dict:
                return {"username": body.username}

        app = Application("test").ready()

        # 잘못된 데이터: username 너무 짧음, age가 문자열
        request = HttpRequest(
            method="POST",
            path="/users",
            body=b'{"username": "ab", "email": "test@example.com", "age": "not-a-number"}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 400
        assert response.body["error"] == "ValidationError"
        assert "details" in response.body
        assert len(response.body["details"]) >= 2  # username, age 에러

        # 에러 위치 확인
        locs = [tuple(e["loc"]) for e in response.body["details"]]
        assert any("username" in loc for loc in locs)
        assert any("age" in loc for loc in locs)

    @pytest.mark.asyncio
    async def test_pydantic_validation_error_nested(self, reset_container_manager):
        """pydantic 중첩 모델 유효성 검사 실패"""
        try:
            from pydantic import BaseModel, Field
        except ImportError:
            pytest.skip("pydantic not installed")

        class Address(BaseModel):
            street: str
            city: str
            zipcode: str = Field(min_length=5)

        class Contact(BaseModel):
            email: str
            phone: str = Field(min_length=10)

        class CreateUserRequest(BaseModel):
            username: str
            address: Address
            contact: Contact

        @Controller
        class UserController:
            @Post("/users")
            async def create_user(self, body: RequestBody[CreateUserRequest]) -> dict:
                return {"username": body.username}

        app = Application("test").ready()

        # 중첩 필드에 잘못된 데이터
        request = HttpRequest(
            method="POST",
            path="/users",
            body=b'{"username": "bob", "address": {"street": "123 Main"}, "contact": {"email": "test@test.com", "phone": "123"}}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 400
        assert response.body["error"] == "ValidationError"
        assert "details" in response.body

        # 에러 위치에 중첩 경로가 포함되어야 함
        details = response.body["details"]
        locs = [tuple(e["loc"]) for e in details]

        # address.city, address.zipcode 누락
        assert any("address" in str(loc) for loc in locs)
        # contact.phone 길이 오류
        assert any("contact" in str(loc) and "phone" in str(loc) for loc in locs)

    @pytest.mark.asyncio
    async def test_pydantic_validation_error_list_items(self, reset_container_manager):
        """pydantic 리스트 아이템 유효성 검사 실패"""
        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("pydantic not installed")

        class Item(BaseModel):
            name: str
            price: float

        class OrderRequest(BaseModel):
            items: list[Item]

        @Controller
        class OrderController:
            @Post("/orders")
            async def create_order(self, body: RequestBody[OrderRequest]) -> dict:
                return {"count": len(body.items)}

        app = Application("test").ready()

        # 리스트 내 아이템 중 일부가 잘못됨
        request = HttpRequest(
            method="POST",
            path="/orders",
            body=b'{"items": [{"name": "A", "price": 100}, {"name": "B", "price": "invalid"}]}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 400
        assert response.body["error"] == "ValidationError"

        # items.1.price에 에러가 있어야 함 (인덱스 포함)
        details = response.body["details"]
        locs = [e["loc"] for e in details]
        # ["body", "items", 1, "price"] 형태
        assert any(1 in loc and "price" in loc for loc in locs)

    @pytest.mark.asyncio
    async def test_dataclass_validation_error(self, reset_container_manager):
        """dataclass 생성 실패 시 ValidationError"""

        @dataclass
        class UserData:
            name: str
            age: int

        @Controller
        class UserController:
            @Post("/users")
            async def create_user(self, body: RequestBody[UserData]) -> dict:
                return {"name": body.name}

        app = Application("test").ready()

        # 필수 필드 누락
        request = HttpRequest(
            method="POST",
            path="/users",
            body=b'{"name": "Alice"}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 400
        assert response.body["error"] == "ValidationError"
        assert "details" in response.body

    @pytest.mark.asyncio
    async def test_validation_error_includes_input(self, reset_container_manager):
        """ValidationError에 입력값이 포함됨"""
        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("pydantic not installed")

        class AgeRequest(BaseModel):
            age: int

        @Controller
        class TestController:
            @Post("/test")
            async def test_age(self, body: RequestBody[AgeRequest]) -> dict:
                return {"age": body.age}

        app = Application("test").ready()

        request = HttpRequest(
            method="POST",
            path="/test",
            body=b'{"age": "twenty"}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 400
        details = response.body["details"]
        # input 필드가 포함되어 있어야 함
        assert any("input" in e for e in details)
        # 입력값이 "twenty"
        assert any(e.get("input") == "twenty" for e in details)


# =============================================================================
# Enum Parameter Tests
# =============================================================================


from enum import Enum


class Status(str, Enum):
    """테스트용 상태 Enum"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class Priority(int, Enum):
    """테스트용 우선순위 Enum (int 기반)"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


class TestEnumPathParameter:
    """Enum 경로 파라미터 테스트"""

    @pytest.mark.asyncio
    async def test_enum_path_param_by_value(self, reset_container_manager):
        """Enum 값으로 경로 파라미터 변환"""

        @Controller
        class ItemController:
            @Get("/items/{status}")
            async def get_items_by_status(self, status: Status) -> dict:
                return {"status": status.value, "name": status.name}

        app = Application("test").ready()

        request = HttpRequest(method="GET", path="/items/active")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"status": "active", "name": "ACTIVE"}

    @pytest.mark.asyncio
    async def test_enum_path_param_by_name(self, reset_container_manager):
        """Enum 이름으로 경로 파라미터 변환"""

        @Controller
        class ItemController:
            @Get("/items/{status}")
            async def get_items_by_status(self, status: Status) -> dict:
                return {"status": status.value, "name": status.name}

        app = Application("test").ready()

        # Enum name으로 접근 (value 실패 시 name으로 시도)
        request = HttpRequest(method="GET", path="/items/PENDING")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"status": "pending", "name": "PENDING"}

    @pytest.mark.asyncio
    async def test_int_enum_path_param(self, reset_container_manager):
        """int 기반 Enum 경로 파라미터"""

        @Controller
        class TaskController:
            @Get("/tasks/priority/{priority}")
            async def get_by_priority(self, priority: Priority) -> dict:
                return {"priority": priority.value, "name": priority.name}

        app = Application("test").ready()

        request = HttpRequest(method="GET", path="/tasks/priority/2")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"priority": 2, "name": "MEDIUM"}

    @pytest.mark.asyncio
    async def test_invalid_enum_path_param_returns_400(self, reset_container_manager):
        """잘못된 Enum 값은 400 Bad Request 반환"""

        @Controller
        class ItemController:
            @Get("/items/{status}")
            async def get_items_by_status(self, status: Status) -> dict:
                return {"status": status.value}

        app = Application("test").ready()

        # 존재하지 않는 Enum 값
        request = HttpRequest(method="GET", path="/items/unknown")
        response = await app.router.dispatch(request)

        # 잘못된 Enum 값이므로 400
        assert response.status_code == 400
        assert "TypeConversionError" in response.body.get("error", "")


class TestEnumQueryParameter:
    """Enum 쿼리 파라미터 테스트"""

    @pytest.mark.asyncio
    async def test_enum_query_param(self, reset_container_manager):
        """Enum 쿼리 파라미터"""

        @Controller
        class ItemController:
            @Get("/items")
            async def list_items(self, status: Status) -> dict:
                return {"status": status.value}

        app = Application("test").ready()

        request = HttpRequest(
            method="GET",
            path="/items",
            query_params={"status": "active"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"status": "active"}

    @pytest.mark.asyncio
    async def test_optional_enum_query_param(self, reset_container_manager):
        """Optional Enum 쿼리 파라미터"""

        @Controller
        class ItemController:
            @Get("/items")
            async def list_items(self, status: Status | None = None) -> dict:
                if status is None:
                    return {"status": "all"}
                return {"status": status.value}

        app = Application("test").ready()

        # status 없이 요청
        request = HttpRequest(method="GET", path="/items")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"status": "all"}

        # status 있이 요청
        request = HttpRequest(
            method="GET",
            path="/items",
            query_params={"status": "inactive"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"status": "inactive"}

    @pytest.mark.asyncio
    async def test_enum_from_json_body(self, reset_container_manager):
        """JSON body에서 Enum 쿼리 파라미터"""

        @Controller
        class ItemController:
            @Post("/items")
            async def create_item(self, status: Status) -> dict:
                return {"status": status.value}

        app = Application("test").ready()

        request = HttpRequest(
            method="POST",
            path="/items",
            body=b'{"status": "pending"}',
            headers={"content-type": "application/json"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"status": "pending"}
