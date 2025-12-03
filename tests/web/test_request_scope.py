"""REQUEST 스코프 및 ASGI 미들웨어 테스트"""

import pytest
import uuid
from typing import Any

from bloom.core import (
    Component,
    Scope,
    PostConstruct,
    PreDestroy,
    get_container_manager,
)
from bloom.web import (
    ASGIApplication,
    Request,
    Response,
    JSONResponse,
)


# === Test Utilities ===


class MockReceive:
    """테스트용 ASGI receive"""
    
    def __init__(self, body: bytes = b""):
        self.body = body
        self._sent = False
    
    async def __call__(self) -> dict[str, Any]:
        if not self._sent:
            self._sent = True
            return {"type": "http.request", "body": self.body, "more_body": False}
        return {"type": "http.disconnect"}


class MockSend:
    """테스트용 ASGI send"""
    
    def __init__(self):
        self.messages: list[dict[str, Any]] = []
    
    async def __call__(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
    
    @property
    def status_code(self) -> int | None:
        for msg in self.messages:
            if msg["type"] == "http.response.start":
                return msg.get("status")
        return None
    
    @property
    def body(self) -> bytes:
        body_parts = []
        for msg in self.messages:
            if msg["type"] == "http.response.body":
                body_parts.append(msg.get("body", b""))
        return b"".join(body_parts)
    
    @property
    def headers(self) -> dict[str, str]:
        for msg in self.messages:
            if msg["type"] == "http.response.start":
                raw_headers = msg.get("headers", [])
                return {
                    k.decode(): v.decode() for k, v in raw_headers
                }
        return {}


def make_scope(
    method: str = "GET",
    path: str = "/",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict[str, Any]:
    """테스트용 ASGI scope 생성"""
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "query_string": query_string,
        "root_path": "",
        "headers": headers or [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 12345),
    }


# === Tests ===


class TestRequestObject:
    """Request 객체 테스트"""

    @pytest.mark.asyncio
    async def test_request_basic_properties(self):
        """기본 속성 테스트"""
        scope = make_scope(method="POST", path="/users")
        receive = MockReceive()
        
        request = Request(scope, receive)
        
        assert request.method == "POST"
        assert request.path == "/users"
        assert request.scheme == "http"
        assert request.client_host == "127.0.0.1"

    @pytest.mark.asyncio
    async def test_request_query_params(self):
        """쿼리 파라미터 테스트"""
        scope = make_scope(path="/search", query_string=b"q=hello&page=1")
        receive = MockReceive()
        
        request = Request(scope, receive)
        
        assert request.query_params == {"q": ["hello"], "page": ["1"]}
        assert request.query_param("q") == "hello"
        assert request.query_param("page") == "1"
        assert request.query_param("missing", "default") == "default"

    @pytest.mark.asyncio
    async def test_request_headers(self):
        """헤더 테스트"""
        scope = make_scope(headers=[
            (b"content-type", b"application/json"),
            (b"authorization", b"Bearer token123"),
        ])
        receive = MockReceive()
        
        request = Request(scope, receive)
        
        assert request.content_type == "application/json"
        assert request.header("Authorization") == "Bearer token123"
        assert request.header("X-Missing") is None

    @pytest.mark.asyncio
    async def test_request_body(self):
        """본문 테스트"""
        scope = make_scope(method="POST")
        receive = MockReceive(body=b'{"name": "test"}')
        
        request = Request(scope, receive)
        
        body = await request.body()
        assert body == b'{"name": "test"}'
        
        text = await request.text()
        assert text == '{"name": "test"}'
        
        json_data = await request.json()
        assert json_data == {"name": "test"}


class TestResponseObject:
    """Response 객체 테스트"""

    @pytest.mark.asyncio
    async def test_response_basic(self):
        """기본 응답 테스트"""
        response = Response(content="Hello", status_code=200)
        
        scope = make_scope()
        receive = MockReceive()
        send = MockSend()
        
        await response(scope, receive, send)
        
        assert send.status_code == 200
        assert send.body == b"Hello"

    @pytest.mark.asyncio
    async def test_json_response(self):
        """JSON 응답 테스트"""
        response = JSONResponse({"message": "Hello"}, status_code=201)
        
        scope = make_scope()
        receive = MockReceive()
        send = MockSend()
        
        await response(scope, receive, send)
        
        assert send.status_code == 201
        assert b'"message"' in send.body
        assert send.headers.get("content-type") == "application/json"


class TestASGIApplication:
    """ASGIApplication 테스트"""

    @pytest.mark.asyncio
    async def test_simple_route(self):
        """간단한 라우트 테스트"""
        app = ASGIApplication()
        
        @app.get("/")
        async def index(request: Request) -> Response:
            return JSONResponse({"message": "Hello"})
        
        scope = make_scope(path="/")
        receive = MockReceive()
        send = MockSend()
        
        await app(scope, receive, send)
        
        assert send.status_code == 200
        assert b"Hello" in send.body

    @pytest.mark.asyncio
    async def test_404_not_found(self):
        """404 응답 테스트"""
        app = ASGIApplication()
        
        scope = make_scope(path="/nonexistent")
        receive = MockReceive()
        send = MockSend()
        
        await app(scope, receive, send)
        
        assert send.status_code == 404

    @pytest.mark.asyncio
    async def test_method_routing(self):
        """HTTP 메서드별 라우팅 테스트"""
        app = ASGIApplication()
        
        @app.get("/resource")
        async def get_resource(request: Request):
            return {"method": "GET"}
        
        @app.post("/resource")
        async def create_resource(request: Request):
            return {"method": "POST"}
        
        # GET
        scope = make_scope(method="GET", path="/resource")
        send = MockSend()
        await app(scope, MockReceive(), send)
        assert b"GET" in send.body
        
        # POST
        scope = make_scope(method="POST", path="/resource")
        send = MockSend()
        await app(scope, MockReceive(), send)
        assert b"POST" in send.body


class TestRequestScopeMiddleware:
    """REQUEST 스코프 미들웨어 테스트"""

    @pytest.mark.asyncio
    async def test_request_scope_lifecycle(self):
        """REQUEST 스코프 라이프사이클 테스트"""
        events = []
        instance_ids = []

        @Component(scope=Scope.REQUEST)
        class RequestContext:
            def __init__(self):
                self.id = str(uuid.uuid4())
                instance_ids.append(self.id)
                events.append(f"create:{self.id}")

            @PreDestroy
            async def cleanup(self):
                events.append(f"destroy:{self.id}")

        app = ASGIApplication()
        manager = get_container_manager()
        await manager.initialize()

        @app.get("/test")
        async def test_handler(request: Request):
            # REQUEST 스코프 인스턴스 획득
            ctx = await manager.get_instance_async(RequestContext)
            events.append(f"use:{ctx.id}")
            return {"request_id": ctx.id}

        # 첫 번째 요청
        scope = make_scope(path="/test")
        send = MockSend()
        await app(scope, MockReceive(), send)
        
        assert send.status_code == 200
        
        # 두 번째 요청
        scope = make_scope(path="/test")
        send = MockSend()
        await app(scope, MockReceive(), send)
        
        # 2개의 다른 인스턴스가 생성됨
        assert len(instance_ids) == 2
        assert instance_ids[0] != instance_ids[1]
        
        # 각 요청마다 create → use → destroy 순서
        assert events.count("create:" + instance_ids[0]) == 1
        assert events.count("use:" + instance_ids[0]) == 1
        assert events.count("destroy:" + instance_ids[0]) == 1

    @pytest.mark.asyncio
    async def test_request_scope_same_instance_in_request(self):
        """같은 요청 내에서는 같은 인스턴스"""
        
        @Component(scope=Scope.REQUEST)
        class RequestState:
            def __init__(self):
                self.id = str(uuid.uuid4())
                self.counter = 0
            
            def increment(self):
                self.counter += 1
                return self.counter

        app = ASGIApplication()
        manager = get_container_manager()
        await manager.initialize()

        @app.get("/test")
        async def test_handler(request: Request):
            # 같은 요청에서 여러 번 획득
            state1 = await manager.get_instance_async(RequestState)
            state1.increment()
            
            state2 = await manager.get_instance_async(RequestState)
            state2.increment()
            
            state3 = await manager.get_instance_async(RequestState)
            count = state3.increment()
            
            return {
                "same_instance": state1.id == state2.id == state3.id,
                "counter": count,
            }

        scope = make_scope(path="/test")
        send = MockSend()
        await app(scope, MockReceive(), send)
        
        import json
        result = json.loads(send.body)
        
        assert result["same_instance"] is True
        assert result["counter"] == 3

    @pytest.mark.asyncio
    async def test_request_scope_isolation(self):
        """요청 간 스코프 격리 테스트"""
        
        @Component(scope=Scope.REQUEST)
        class IsolatedState:
            def __init__(self):
                self.value = "initial"

        app = ASGIApplication()
        manager = get_container_manager()
        await manager.initialize()

        @app.post("/set")
        async def set_value(request: Request):
            state = await manager.get_instance_async(IsolatedState)
            data = await request.json()
            state.value = data.get("value", "default")
            return {"set": state.value}

        @app.get("/get")
        async def get_value(request: Request):
            state = await manager.get_instance_async(IsolatedState)
            return {"value": state.value}

        # 첫 번째 요청: 값 설정
        scope = make_scope(method="POST", path="/set")
        receive = MockReceive(body=b'{"value": "modified"}')
        send = MockSend()
        await app(scope, receive, send)
        
        # 두 번째 요청: 값 조회 (새 인스턴스이므로 initial)
        scope = make_scope(path="/get")
        send = MockSend()
        await app(scope, MockReceive(), send)
        
        import json
        result = json.loads(send.body)
        
        # 새 요청이므로 새 인스턴스 = initial 값
        assert result["value"] == "initial"
