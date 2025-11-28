"""웹 기능 테스트"""

import pytest
import asyncio
from io import BytesIO
from pathlib import Path
import tempfile
from bloom import Application, Component
from bloom.core import ContainerManager
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
from bloom.web.http import StreamingResponse, FileResponse


class TestHttpModels:
    """HTTP 요청/응답 모델 테스트"""

    def test_http_request_basic(self):
        """기본 HTTP 요청 생성"""
        request = HttpRequest(method="GET", path="/users")
        assert request.method == "GET"
        assert request.path == "/users"

    def test_http_request_with_body(self):
        """바디가 있는 HTTP 요청"""
        body = b'{"name": "test"}'
        request = HttpRequest(method="POST", path="/users", body=body)
        assert request.json == {"name": "test"}
        assert request.text == '{"name": "test"}'

    def test_http_response_factory_methods(self):
        """HTTP 응답 팩토리 메서드들"""
        assert HttpResponse.ok({"data": 1}).status_code == 200
        assert HttpResponse.created().status_code == 201
        assert HttpResponse.no_content().status_code == 204
        assert HttpResponse.bad_request().status_code == 400
        assert HttpResponse.not_found().status_code == 404
        assert HttpResponse.internal_error().status_code == 500

    def test_http_response_to_json(self):
        """응답 JSON 직렬화"""
        response = HttpResponse.ok({"message": "안녕"})
        json_bytes = response.to_json()
        assert b'"message"' in json_bytes
        assert "안녕".encode("utf-8") in json_bytes


class TestHttpMethodHandler:
    """HTTP 메서드 핸들러 테스트"""

    def test_get_decorator(self):
        """@Get 데코레이터"""

        @Component
        class TestController:
            @Get("/items")
            def list_items(self) -> list[str]:
                return ["a", "b"]

        container = TestController.list_items.__container__
        assert isinstance(container, HttpMethodHandler)
        assert container.get_metadata("http_method") == "GET"
        assert container.get_metadata("http_path") == "/items"
        assert container.handler_key == ("GET", "/items")

    def test_post_decorator(self):
        """@Post 데코레이터"""

        @Component
        class TestController:
            @Post("/items")
            def create_item(self) -> dict:
                return {"id": 1}

        container = TestController.create_item.__container__
        assert container.get_metadata("http_method") == "POST"
        assert container.get_metadata("http_path") == "/items"

    @pytest.mark.asyncio
    async def test_handler_invocation(self):
        """핸들러 호출 (비동기)"""

        @Component
        class TestController:
            @Get("/hello")
            def say_hello(self) -> str:
                return "hello"

        app = Application("test_handler").ready()

        handler = TestController.say_hello.__container__
        result = await handler()
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_async_handler_invocation(self):
        """비동기 핸들러 호출"""

        @Component
        class AsyncController:
            @Get("/async")
            async def async_hello(self) -> str:
                return "async hello"

        app = Application("test_async_handler").ready()

        handler = AsyncController.async_hello.__container__
        result = await handler()
        assert result == "async hello"


class TestRouter:
    """Router 테스트"""

    def test_router_collect_routes(self):
        """라우터가 핸들러들을 수집"""

        @Component
        class ApiController:
            @Get("/api/users")
            def list_users(self) -> list:
                return []

            @Post("/api/users")
            def create_user(self) -> dict:
                return {"id": 1}

        app = Application("test_router").ready()

        routes = app.router.get_routes()
        assert ("GET", "/api/users", "list_users") in routes
        assert ("POST", "/api/users", "create_user") in routes

    @pytest.mark.asyncio
    async def test_router_dispatch_simple(self):
        """단순 경로 디스패치 (비동기)"""

        @Component
        class SimpleController:
            @Get("/ping")
            def ping(self, **kwargs) -> str:
                return "pong"

        app = Application("test_dispatch").ready()

        request = HttpRequest(method="GET", path="/ping")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == "pong"

    @pytest.mark.asyncio
    async def test_router_dispatch_with_path_params(self):
        """경로 파라미터가 있는 디스패치 (비동기)"""

        @Component
        class UserController:
            @Get("/users/{user_id}")
            def get_user(self, user_id: str, **kwargs) -> dict:
                return {"id": user_id}

            @Delete("/users/{user_id}/posts/{post_id}")
            def delete_post(self, user_id: str, post_id: str, **kwargs) -> dict:
                return {"user_id": user_id, "post_id": post_id}

        app = Application("test_path_params").ready()

        # 단일 파라미터
        request = HttpRequest(method="GET", path="/users/123")
        response = await app.router.dispatch(request)
        assert response.body == {"id": "123"}

        # 복수 파라미터
        request = HttpRequest(method="DELETE", path="/users/123/posts/456")
        response = await app.router.dispatch(request)
        assert response.body == {"user_id": "123", "post_id": "456"}

    @pytest.mark.asyncio
    async def test_router_not_found(self):
        """존재하지 않는 경로 (비동기)"""

        @Component
        class EmptyController:
            pass

        app = Application("test_not_found").ready()

        request = HttpRequest(method="GET", path="/nonexistent")
        response = await app.router.dispatch(request)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_router_returns_http_response(self):
        """핸들러가 HttpResponse를 직접 반환 (비동기)"""

        @Component
        class ResponseController:
            @Post
            def create(self, **kwargs) -> HttpResponse:
                return HttpResponse.created({"id": 1})

        app = Application("test_response").ready()

        # @Post만 사용하면 path는 /함수명
        request = HttpRequest(method="POST", path="/create")
        response = await app.router.dispatch(request)

        assert response.status_code == 201
        assert response.body == {"id": 1}

    @pytest.mark.asyncio
    async def test_router_dispatch_async_handler(self):
        """비동기 핸들러 디스패치"""

        @Component
        class AsyncController:
            @Get("/async-data")
            async def get_async_data(self, **kwargs) -> dict:
                return {"async": True}

        app = Application("test_async_dispatch").ready()

        request = HttpRequest(method="GET", path="/async-data")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"async": True}


class TestController:
    """Controller 및 RequestMapping 테스트"""

    def test_controller_creates_container(self):
        """@Controller가 ControllerContainer를 생성"""

        @Controller
        class TestController:
            pass

        assert hasattr(TestController, "__container__")
        assert isinstance(
            TestController.__container__, ControllerContainer  # type:ignore
        )

    def test_request_mapping_sets_path(self):
        """@RequestMapping이 경로를 설정"""

        @Controller
        @RequestMapping("/api/v1")
        class ApiController:
            pass

        container = ApiController.__container__  # type:ignore
        # get_metadatas returns a list of metadata values for the given key
        assert container.get_metadatas("request_mapping")[0] == "/api/v1"

    @pytest.mark.asyncio
    async def test_controller_with_request_mapping_routes(self):
        """Controller + RequestMapping + Handler 조합 라우팅 (비동기)"""

        @Controller
        @RequestMapping("/api")
        class UserController:
            @Get("/users")
            def list_users(self, **kwargs) -> list[str]:
                return ["user1", "user2"]

            @Post("/users")
            def create_user(self, **kwargs) -> dict:
                return {"id": 1}

            @Get("/users/{id}")
            def get_user(self, id: str, **kwargs) -> dict:
                return {"id": id}

        app = Application("test_controller").ready()

        routes = app.router.get_routes()
        # RequestMapping prefix가 적용됨
        assert ("GET", "/api/users", "list_users") in routes
        assert ("POST", "/api/users", "create_user") in routes
        assert ("GET", "/api/users/{id}", "get_user") in routes

        # 실제 디스패치 테스트 (비동기)
        request = HttpRequest(method="GET", path="/api/users")
        response = await app.router.dispatch(request)
        assert response.body == ["user1", "user2"]

        request = HttpRequest(method="GET", path="/api/users/123")
        response = await app.router.dispatch(request)
        assert response.body == {"id": "123"}

    @pytest.mark.asyncio
    async def test_controller_without_request_mapping(self):
        """RequestMapping 없는 Controller (비동기)"""

        @Controller
        class SimpleController:
            @Get("/health")
            def health(self, **kwargs) -> str:
                return "ok"

        app = Application("test_simple_controller").ready()

        request = HttpRequest(method="GET", path="/health")
        response = await app.router.dispatch(request)
        assert response.body == "ok"


class TestASGI:
    """ASGI 애플리케이션 테스트"""

    @pytest.mark.asyncio
    async def test_asgi_basic_request(self):
        """기본 ASGI 요청 처리"""

        @Component
        class PingController:
            @Get("/ping")
            def ping(self, **kwargs) -> str:
                return "pong"

        app = Application("test_asgi")
        app.ready()

        router = app.router

        asgi_app = ASGIApplication(router)

        # Mock ASGI scope, receive, send
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/ping",
            "query_string": b"",
            "headers": [],
        }

        received_messages: list[dict] = []

        async def receive():
            return {"body": b"", "more_body": False}

        async def send(message: dict):
            received_messages.append(message)

        await asgi_app(scope, receive, send)

        # 응답 확인
        assert len(received_messages) == 2
        assert received_messages[0]["type"] == "http.response.start"
        assert received_messages[0]["status"] == 200
        assert received_messages[1]["type"] == "http.response.body"
        assert b"pong" in received_messages[1]["body"]

    @pytest.mark.asyncio
    async def test_asgi_post_with_body(self):
        """POST 요청 바디 처리"""

        @Component
        class EchoController:
            @Post("/echo")
            def echo(self, request: HttpRequest, **kwargs) -> dict:
                return {"received": request.json}

        app = Application("test_asgi_post")
        app.ready()

        router = app.router

        asgi_app = ASGIApplication(router)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/echo",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
        }

        body_content = b'{"message": "hello"}'
        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {"body": body_content, "more_body": False}
            return {"body": b"", "more_body": False}

        received_messages: list[dict] = []

        async def send(message: dict):
            received_messages.append(message)

        await asgi_app(scope, receive, send)

        assert received_messages[0]["status"] == 200
        import json

        response_body = json.loads(received_messages[1]["body"])
        assert response_body["received"] == {"message": "hello"}

    @pytest.mark.asyncio
    async def test_asgi_with_query_params(self):
        """쿼리 파라미터 처리"""

        @Component
        class SearchController:
            @Get("/search")
            def search(self, request: HttpRequest, **kwargs) -> dict:
                return {"query": request.query_params.get("q", "")}

        app = Application("test_asgi_query")
        app.ready()

        router = app.router

        asgi_app = ASGIApplication(router)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/search",
            "query_string": b"q=hello&limit=10",
            "headers": [],
        }

        async def receive():
            return {"body": b"", "more_body": False}

        received_messages: list[dict] = []

        async def send(message: dict):
            received_messages.append(message)

        await asgi_app(scope, receive, send)

        import json

        response_body = json.loads(received_messages[1]["body"])
        assert response_body["query"] == "hello"

    @pytest.mark.asyncio
    async def test_asgi_async_handler(self):
        """비동기 핸들러 ASGI 테스트"""

        @Component
        class AsyncController:
            @Get("/async-data")
            async def get_data(self, **kwargs) -> dict:
                return {"async": True, "data": "async result"}

        app = Application("test_asgi_async")
        app.ready()

        router = app.router

        asgi_app = ASGIApplication(router)

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/async-data",
            "query_string": b"",
            "headers": [],
        }

        async def receive():
            return {"body": b"", "more_body": False}

        received_messages: list[dict] = []

        async def send(message: dict):
            received_messages.append(message)

        await asgi_app(scope, receive, send)

        import json

        response_body = json.loads(received_messages[1]["body"])
        assert response_body["async"] is True
        assert response_body["data"] == "async result"

    @pytest.mark.asyncio
    async def test_create_asgi_app_factory(self):
        """create_asgi_app 팩토리 함수"""

        @Component
        class FactoryController:
            @Get("/factory")
            def factory_test(self, **kwargs) -> str:
                return "factory works"

        app = Application("test_factory")
        app.ready()

        # 팩토리로 생성
        asgi_app = create_asgi_app()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/factory",
            "query_string": b"",
            "headers": [],
        }

        async def receive():
            return {"body": b"", "more_body": False}

        received_messages: list[dict] = []

        async def send(message: dict):
            received_messages.append(message)

        await asgi_app(scope, receive, send)

        assert received_messages[0]["status"] == 200


class TestResponseTypeConversion:
    """response 파라미터를 통한 반환값 타입 변환 테스트"""

    @pytest.mark.asyncio
    async def test_response_with_pydantic(self):
        """pydantic BaseModel로 response 변환"""
        from pydantic import BaseModel

        class UserOutput(BaseModel):
            id: int
            name: str

        @Component
        class UserController:
            @Get("/user", response=UserOutput)
            def get_user(self) -> dict:
                return {"id": 1, "name": "홍길동"}

        app = Application("test_pydantic_response").ready()
        request = HttpRequest(method="GET", path="/user")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert isinstance(response.body, UserOutput)
        assert response.body.id == 1
        assert response.body.name == "홍길동"

    @pytest.mark.asyncio
    async def test_response_with_dataclass(self):
        """dataclass로 response 변환"""
        from dataclasses import dataclass

        @dataclass
        class ProductOutput:
            id: int
            name: str
            price: float

        @Component
        class ProductController:
            @Post("/product", response=ProductOutput)
            def create_product(self) -> dict:
                return {"id": 1, "name": "상품", "price": 1000.0}

        app = Application("test_dataclass_response").ready()
        request = HttpRequest(method="POST", path="/product", body=b"{}")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert isinstance(response.body, ProductOutput)
        assert response.body.id == 1
        assert response.body.name == "상품"
        assert response.body.price == 1000.0

    @pytest.mark.asyncio
    async def test_response_already_correct_type(self):
        """이미 올바른 타입이면 그대로 반환"""
        from pydantic import BaseModel

        class ItemOutput(BaseModel):
            id: int

        @Component
        class ItemController:
            @Get("/item", response=ItemOutput)
            def get_item(self) -> ItemOutput:
                return ItemOutput(id=42)

        app = Application("test_already_correct_type").ready()
        request = HttpRequest(method="GET", path="/item")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert isinstance(response.body, ItemOutput)
        assert response.body.id == 42

    @pytest.mark.asyncio
    async def test_response_without_conversion(self):
        """response 없으면 변환 안 함"""

        @Component
        class RawController:
            @Get("/raw")
            def get_raw(self) -> dict:
                return {"data": "raw"}

        app = Application("test_no_response").ready()
        request = HttpRequest(method="GET", path="/raw")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body == {"data": "raw"}

    def test_handler_repr_with_response_type(self):
        """response_type이 있으면 __repr__에 포함"""
        from pydantic import BaseModel

        class Output(BaseModel):
            value: str

        @Component
        class TestController:
            @Get("/test", response=Output)
            def test_method(self) -> dict:
                return {"value": "test"}

        handler = TestController.test_method.__container__
        assert "Output" in repr(handler.get_metadata("response_type"))

    def test_handler_repr_without_response_type(self):
        """response_type 없으면 __repr__에 미포함"""

        @Component
        class TestController:
            @Get("/test")
            def test_method(self) -> str:
                return "test"

        handler = TestController.test_method.__container__
        assert handler.get_metadata("response_type", raise_exception=False) is None


class TestStreamingResponse:
    """StreamingResponse 테스트"""

    @pytest.mark.asyncio
    async def test_basic_streaming(self):
        """기본 스트리밍 응답"""

        async def generate():
            for i in range(3):
                yield f"chunk{i}"

        response = StreamingResponse(generate())
        assert response.status_code == 200
        assert response.content_type == "text/plain"

        chunks = []
        async for chunk in response:
            chunks.append(chunk)

        assert chunks == [b"chunk0", b"chunk1", b"chunk2"]

    @pytest.mark.asyncio
    async def test_streaming_with_bytes(self):
        """bytes 청크 스트리밍"""

        async def generate():
            yield b"binary"
            yield b"data"

        response = StreamingResponse(generate())
        chunks = [chunk async for chunk in response]
        assert chunks == [b"binary", b"data"]

    @pytest.mark.asyncio
    async def test_sse_streaming(self):
        """SSE 스트리밍 응답"""

        async def events():
            yield "data: event1\n\n"
            yield "data: event2\n\n"

        response = StreamingResponse.sse(events())
        assert response.content_type == "text/event-stream"
        assert response.headers.get("Cache-Control") == "no-cache"
        assert response.headers.get("Connection") == "keep-alive"

        chunks = [chunk async for chunk in response]
        assert chunks == [b"data: event1\n\n", b"data: event2\n\n"]

    @pytest.mark.asyncio
    async def test_file_streaming(self):
        """파일 다운로드 스트리밍"""

        async def file_content():
            yield b"file content part 1"
            yield b"file content part 2"

        response = StreamingResponse.file(
            file_content(),
            filename="test.txt",
            content_type="text/plain",
        )
        assert response.content_type == "text/plain"
        assert 'filename="test.txt"' in response.headers.get("Content-Disposition", "")

        # 실제 컨텐츠 검증
        chunks = [chunk async for chunk in response]
        assert chunks == [b"file content part 1", b"file content part 2"]

    @pytest.mark.asyncio
    async def test_file_streaming_binary(self):
        """바이너리 파일 스트리밍"""

        async def binary_content():
            # 간단한 바이너리 데이터 시뮬레이션
            yield b"\x89PNG\r\n\x1a\n"  # PNG 헤더
            yield b"\x00\x00\x00\rIHDR"  # IHDR 청크

        response = StreamingResponse.file(
            binary_content(),
            filename="image.png",
            content_type="image/png",
        )
        assert response.content_type == "image/png"
        assert (
            response.headers["Content-Disposition"]
            == 'attachment; filename="image.png"'
        )

        chunks = [chunk async for chunk in response]
        assert len(chunks) == 2
        assert chunks[0].startswith(b"\x89PNG")

    @pytest.mark.asyncio
    async def test_file_streaming_with_custom_headers(self):
        """커스텀 헤더가 포함된 파일 스트리밍"""

        async def content():
            yield b"data"

        response = StreamingResponse.file(
            content(),
            filename="report.csv",
            content_type="text/csv",
            headers={"X-File-Id": "12345"},
        )
        assert response.headers["X-File-Id"] == "12345"
        assert "attachment" in response.headers["Content-Disposition"]

    @pytest.mark.asyncio
    async def test_streaming_with_custom_headers(self):
        """커스텀 헤더가 있는 스트리밍"""

        async def generate():
            yield "data"

        response = StreamingResponse(
            generate(),
            status_code=201,
            headers={"X-Custom": "value"},
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response.headers["X-Custom"] == "value"
        assert response.content_type == "application/json"


class TestASGIStreaming:
    """ASGI 스트리밍 통합 테스트"""

    @pytest.mark.asyncio
    async def test_asgi_streaming_response(self, reset_container_manager):
        """ASGI에서 스트리밍 응답 처리"""

        @Controller
        class StreamController:
            @Get("/stream")
            async def stream(self) -> StreamingResponse:
                async def generate():
                    for i in range(3):
                        yield f"data: {i}\n"

                return StreamingResponse(generate())

        app = Application("test").scan(StreamController).ready()

        # ASGI 시뮬레이션
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/stream",
            "headers": [],
            "query_string": b"",
        }

        received_messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            received_messages.append(message)

        await app.asgi(scope, receive, send)

        # 응답 시작 메시지 확인
        start_message = received_messages[0]
        assert start_message["type"] == "http.response.start"
        assert start_message["status"] == 200

        # 청크 메시지들 확인 (more_body=True)
        body_chunks = [
            msg
            for msg in received_messages
            if msg["type"] == "http.response.body" and msg.get("body")
        ]
        assert len(body_chunks) >= 1

        # 마지막 메시지는 more_body=False
        last_message = received_messages[-1]
        assert last_message["type"] == "http.response.body"
        assert last_message.get("more_body") == False

    @pytest.mark.asyncio
    async def test_asgi_sse_response(self, reset_container_manager):
        """ASGI에서 SSE 응답 처리"""

        @Controller
        class SSEController:
            @Get("/events")
            async def events(self) -> StreamingResponse:
                async def generate():
                    yield "event: message\ndata: hello\n\n"
                    yield "event: message\ndata: world\n\n"

                return StreamingResponse.sse(generate())

        app = Application("test").scan(SSEController).ready()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/events",
            "headers": [],
            "query_string": b"",
        }

        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await app.asgi(scope, receive, send)

        # content-type 확인
        start = messages[0]
        headers_dict = {k.decode(): v.decode() for k, v in start["headers"]}
        assert headers_dict.get("content-type") == "text/event-stream"

    @pytest.mark.asyncio
    async def test_asgi_file_download(self, reset_container_manager):
        """ASGI에서 파일 다운로드 응답 처리"""

        @Controller
        class FileController:
            @Get("/download")
            async def download(self) -> StreamingResponse:
                async def generate_csv():
                    yield "id,name,value\n"
                    yield "1,item1,100\n"
                    yield "2,item2,200\n"

                return StreamingResponse.file(
                    generate_csv(),
                    filename="data.csv",
                    content_type="text/csv",
                )

        app = Application("test").scan(FileController).ready()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/download",
            "headers": [],
            "query_string": b"",
        }

        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await app.asgi(scope, receive, send)

        # 헤더 검증
        start = messages[0]
        headers_dict = {k.decode(): v.decode() for k, v in start["headers"]}
        assert headers_dict.get("content-type") == "text/csv"
        # Content-Disposition 헤더 확인 (대소문자 유연하게)
        content_disposition = headers_dict.get(
            "Content-Disposition", headers_dict.get("content-disposition", "")
        )
        assert 'filename="data.csv"' in content_disposition

        # 바디 청크들 수집
        body_chunks = [
            msg["body"]
            for msg in messages
            if msg["type"] == "http.response.body" and msg.get("body")
        ]
        full_body = b"".join(body_chunks)
        assert b"id,name,value" in full_body
        assert b"1,item1,100" in full_body
        assert b"2,item2,200" in full_body

    @pytest.mark.asyncio
    async def test_asgi_large_file_streaming(self, reset_container_manager):
        """대용량 파일 청크 스트리밍 테스트"""

        @Controller
        class LargeFileController:
            @Get("/large")
            async def large_file(self) -> StreamingResponse:
                async def generate_large():
                    # 10개의 1KB 청크 생성
                    for i in range(10):
                        yield b"X" * 1024

                return StreamingResponse.file(
                    generate_large(),
                    filename="large.bin",
                )

        app = Application("test").scan(LargeFileController).ready()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/large",
            "headers": [],
            "query_string": b"",
        }

        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await app.asgi(scope, receive, send)

        # 청크 개수 확인 (more_body=True인 메시지들)
        streaming_chunks = [
            msg
            for msg in messages
            if msg["type"] == "http.response.body" and msg.get("more_body") == True
        ]
        assert len(streaming_chunks) == 10

        # 총 바이트 수 확인
        total_bytes = sum(
            len(msg["body"])
            for msg in messages
            if msg["type"] == "http.response.body" and msg.get("body")
        )
        assert total_bytes == 10 * 1024


class TestFileResponse:
    """FileResponse 테스트"""

    @pytest.mark.asyncio
    async def test_file_response_from_bytesio(self):
        """BytesIO에서 FileResponse 생성"""
        buffer = BytesIO(b"Hello, World!")
        response = FileResponse(buffer, filename="hello.txt")

        assert response.content_type == "text/plain"
        assert 'filename="hello.txt"' in response.headers.get("Content-Disposition", "")

        chunks = [chunk async for chunk in response]
        assert b"".join(chunks) == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_file_response_from_bytesio_binary(self):
        """바이너리 BytesIO에서 FileResponse 생성"""
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        buffer = BytesIO(data)
        response = FileResponse(buffer, filename="image.png")

        assert response.content_type == "image/png"
        chunks = [chunk async for chunk in response]
        assert b"".join(chunks) == data

    @pytest.mark.asyncio
    async def test_file_response_from_path(self):
        """파일 경로에서 FileResponse 생성"""
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".txt", delete=False
        ) as f:
            f.write(b"File content from path")
            temp_path = f.name

        try:
            response = FileResponse(temp_path)
            
            # 파일명 자동 추출
            assert Path(temp_path).name in response.headers.get("Content-Disposition", "")
            assert response.content_type == "text/plain"

            chunks = [chunk async for chunk in response]
            assert b"".join(chunks) == b"File content from path"
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_file_response_from_pathlib(self):
        """Path 객체에서 FileResponse 생성"""
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".json", delete=False
        ) as f:
            f.write(b'{"key": "value"}')
            temp_path = Path(f.name)

        try:
            response = FileResponse(temp_path)
            
            assert response.content_type == "application/json"
            chunks = [chunk async for chunk in response]
            assert b"".join(chunks) == b'{"key": "value"}'
        finally:
            temp_path.unlink()

    @pytest.mark.asyncio
    async def test_file_response_custom_content_type(self):
        """커스텀 MIME 타입 지정"""
        buffer = BytesIO(b"custom data")
        response = FileResponse(
            buffer,
            filename="data.bin",
            content_type="application/x-custom",
        )

        assert response.content_type == "application/x-custom"

    @pytest.mark.asyncio
    async def test_file_response_inline(self):
        """인라인 표시 (다운로드 대신 브라우저에서 표시)"""
        buffer = BytesIO(b"<html></html>")
        response = FileResponse(
            buffer,
            filename="page.html",
            attachment=False,
        )

        disposition = response.headers.get("Content-Disposition", "")
        assert "inline" in disposition
        assert "attachment" not in disposition

    @pytest.mark.asyncio
    async def test_file_response_custom_chunk_size(self):
        """커스텀 청크 크기"""
        # 1KB 데이터를 100바이트 청크로 분할
        data = b"X" * 1024
        buffer = BytesIO(data)
        response = FileResponse(buffer, filename="data.bin", chunk_size=100)

        chunks = [chunk async for chunk in response]
        # 1024 / 100 = 10.24 -> 11개 청크
        assert len(chunks) == 11
        assert b"".join(chunks) == data

    @pytest.mark.asyncio
    async def test_file_response_custom_headers(self):
        """커스텀 헤더 추가"""
        buffer = BytesIO(b"data")
        response = FileResponse(
            buffer,
            filename="file.txt",
            headers={"X-Custom-Header": "custom-value"},
        )

        assert response.headers.get("X-Custom-Header") == "custom-value"
        assert "Content-Disposition" in response.headers

    @pytest.mark.asyncio
    async def test_file_response_auto_filename_from_file_object(self):
        """파일 객체에서 파일명 자동 추출"""
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".csv", delete=False
        ) as f:
            f.write(b"a,b,c")
            temp_path = f.name

        try:
            with open(temp_path, "rb") as file_obj:
                response = FileResponse(file_obj)
                # 파일명이 자동으로 추출됨
                assert Path(temp_path).name in response.headers.get(
                    "Content-Disposition", ""
                )
        finally:
            Path(temp_path).unlink()


class TestFileResponseASGI:
    """FileResponse ASGI 통합 테스트"""

    @pytest.mark.asyncio
    async def test_asgi_file_response_bytesio(self, reset_container_manager):
        """ASGI에서 BytesIO FileResponse 처리"""

        @Controller
        class DownloadController:
            @Get("/export")
            async def export(self) -> FileResponse:
                buffer = BytesIO(b"id,name\n1,Alice\n2,Bob")
                return FileResponse(buffer, filename="users.csv")

        app = Application("test").scan(DownloadController).ready()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/export",
            "headers": [],
            "query_string": b"",
        }

        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        await app.asgi(scope, receive, send)

        # 헤더 검증
        start = messages[0]
        headers_dict = {k.decode(): v.decode() for k, v in start["headers"]}
        assert headers_dict.get("content-type") == "text/csv"
        
        content_disposition = headers_dict.get(
            "Content-Disposition", headers_dict.get("content-disposition", "")
        )
        assert 'filename="users.csv"' in content_disposition

        # 바디 검증
        body_chunks = [
            msg["body"]
            for msg in messages
            if msg["type"] == "http.response.body" and msg.get("body")
        ]
        full_body = b"".join(body_chunks)
        assert b"id,name" in full_body
        assert b"Alice" in full_body

    @pytest.mark.asyncio
    async def test_asgi_file_response_from_path(self, reset_container_manager):
        """ASGI에서 파일 경로 FileResponse 처리"""
        # 임시 파일 생성
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".txt", delete=False
        ) as f:
            f.write(b"Content from temp file")
            temp_path = f.name

        try:
            @Controller
            class FileController:
                @Get("/file")
                async def get_file(self) -> FileResponse:
                    return FileResponse(temp_path, filename="readme.txt")

            app = Application("test").scan(FileController).ready()

            scope = {
                "type": "http",
                "method": "GET",
                "path": "/file",
                "headers": [],
                "query_string": b"",
            }

            messages = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            await app.asgi(scope, receive, send)

            # 바디 검증
            body_chunks = [
                msg["body"]
                for msg in messages
                if msg["type"] == "http.response.body" and msg.get("body")
            ]
            full_body = b"".join(body_chunks)
            assert full_body == b"Content from temp file"
        finally:
            Path(temp_path).unlink()
