"""웹 기능 테스트"""

import pytest
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
