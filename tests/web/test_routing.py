"""라우팅 및 Controller 테스트"""

import pytest
from dataclasses import dataclass

from bloom.web.routing import (
    Router,
    Route,
    RouteMatch,
    Controller,
    RequestMapping,
    GetMapping,
    PostMapping,
    PutMapping,
    DeleteMapping,
    PathVariable,
    Query,
    RequestBody,
    Header,
    ResolverRegistry,
    get_controller_routes,
)
from bloom.web.routing.resolver import ParameterInfo
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


def make_request(
    method: str = "GET",
    path: str = "/",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
    }
    return Request(scope, MockReceive(body))


# === Router Tests ===


class TestRouter:
    """Router 테스트"""

    def test_simple_route(self):
        """간단한 라우트 등록 및 매칭"""
        router = Router()

        @router.get("/users")
        async def list_users():
            return []

        match = router.match("/users", "GET")
        assert match is not None
        assert match.handler is list_users

    def test_path_parameter(self):
        """Path Parameter 매칭"""
        router = Router()

        @router.get("/users/{id}")
        async def get_user(id: int):
            return {"id": id}

        match = router.match("/users/123", "GET")
        assert match is not None
        assert match.path_params == {"id": "123"}

    def test_path_parameter_typed(self):
        """타입 지정된 Path Parameter"""
        router = Router()

        @router.get("/users/{id:int}")
        async def get_user(id: int):
            return {"id": id}

        # 숫자만 매칭
        match = router.match("/users/123", "GET")
        assert match is not None
        assert match.path_params == {"id": "123"}

        # 문자는 매칭 안됨
        match = router.match("/users/abc", "GET")
        assert match is None

    def test_multiple_path_parameters(self):
        """여러 Path Parameter"""
        router = Router()

        @router.get("/users/{user_id}/posts/{post_id}")
        async def get_post(user_id: int, post_id: int):
            return {}

        match = router.match("/users/1/posts/42", "GET")
        assert match is not None
        assert match.path_params == {"user_id": "1", "post_id": "42"}

    def test_method_routing(self):
        """HTTP 메서드별 라우팅"""
        router = Router()

        @router.get("/resource")
        async def get_resource():
            return "GET"

        @router.post("/resource")
        async def create_resource():
            return "POST"

        assert router.match("/resource", "GET") is not None
        assert router.match("/resource", "POST") is not None
        assert router.match("/resource", "DELETE") is None

    def test_prefix(self):
        """라우터 prefix"""
        router = Router(prefix="/api/v1")

        @router.get("/users")
        async def list_users():
            return []

        match = router.match("/api/v1/users", "GET")
        assert match is not None

    def test_sub_router(self):
        """서브 라우터"""
        main_router = Router()
        api_router = Router()

        @api_router.get("/users")
        async def list_users():
            return []

        main_router.include_router(api_router, prefix="/api")

        match = main_router.match("/api/users", "GET")
        assert match is not None


# === Controller Tests ===


class TestController:
    """Controller 데코레이터 테스트"""

    def test_controller_decorator(self):
        """@Controller 데코레이터"""

        @Controller
        class UserController:
            @GetMapping("/users")
            async def list_users(self):
                return []

        assert hasattr(UserController, "__bloom_controller__")
        assert hasattr(UserController, "__bloom_component__")

    def test_request_mapping(self):
        """@RequestMapping prefix"""

        @Controller
        @RequestMapping("/api/v1")
        class ApiController:
            @GetMapping("/status")
            async def status(self):
                return {"ok": True}

        routes = get_controller_routes(ApiController)
        assert len(routes) == 1
        assert routes[0]["path"] == "/api/v1/status"
        assert routes[0]["methods"] == ["GET"]

    def test_http_methods(self):
        """HTTP 메서드별 데코레이터"""

        @Controller
        class ResourceController:
            @GetMapping("/resource")
            async def get_resource(self):
                return "GET"

            @PostMapping("/resource")
            async def create_resource(self):
                return "POST"

            @PutMapping("/resource/{id}")
            async def update_resource(self, id: int):
                return "PUT"

            @DeleteMapping("/resource/{id}")
            async def delete_resource(self, id: int):
                return "DELETE"

        routes = get_controller_routes(ResourceController)
        assert len(routes) == 4

        methods = {r["name"]: r["methods"] for r in routes}
        assert methods["get_resource"] == ["GET"]
        assert methods["create_resource"] == ["POST"]
        assert methods["update_resource"] == ["PUT"]
        assert methods["delete_resource"] == ["DELETE"]


# === Parameter Resolver Tests ===


class TestParameterResolver:
    """ParameterResolver 테스트"""

    @pytest.mark.asyncio
    async def test_path_variable_resolver(self):
        """PathVariable 리졸버"""
        registry = ResolverRegistry()

        async def handler(user_id: PathVariable[int]):
            return user_id

        route = Route("/users/{user_id}", "GET", handler)
        match = RouteMatch(route, {"user_id": "123"})
        request = make_request(path="/users/123")

        resolved = await registry.resolve_parameters(handler, request, match)
        assert resolved["user_id"] == 123

    @pytest.mark.asyncio
    async def test_query_resolver(self):
        """Query 리졸버"""
        registry = ResolverRegistry()

        async def handler(page: Query[int], size: Query[int] = Query(default=10)):
            return {"page": page, "size": size}

        route = Route("/users", "GET", handler)
        match = RouteMatch(route, {})
        request = make_request(path="/users", query_string=b"page=2")

        resolved = await registry.resolve_parameters(handler, request, match)
        assert resolved["page"] == 2
        assert resolved["size"] == 10  # default

    @pytest.mark.asyncio
    async def test_request_body_resolver(self):
        """RequestBody 리졸버"""
        registry = ResolverRegistry()

        @dataclass
        class CreateUser:
            name: str
            email: str

        async def handler(body: RequestBody[CreateUser]):
            return body

        route = Route("/users", "POST", handler)
        match = RouteMatch(route, {})
        request = make_request(
            method="POST",
            path="/users",
            body=b'{"name": "Alice", "email": "alice@example.com"}',
            headers=[(b"content-type", b"application/json")],
        )

        resolved = await registry.resolve_parameters(handler, request, match)
        assert resolved["body"].name == "Alice"
        assert resolved["body"].email == "alice@example.com"

    @pytest.mark.asyncio
    async def test_header_resolver(self):
        """Header 리졸버"""
        registry = ResolverRegistry()

        async def handler(authorization: Header[str]):
            return authorization

        route = Route("/profile", "GET", handler)
        match = RouteMatch(route, {})
        request = make_request(
            path="/profile",
            headers=[(b"authorization", b"Bearer token123")],
        )

        resolved = await registry.resolve_parameters(handler, request, match)
        assert resolved["authorization"] == "Bearer token123"

    @pytest.mark.asyncio
    async def test_implicit_path_variable(self):
        """암시적 PathVariable (마커 없이 이름만)"""
        registry = ResolverRegistry()

        async def handler(id: int):
            return id

        route = Route("/users/{id}", "GET", handler)
        match = RouteMatch(route, {"id": "42"})
        request = make_request(path="/users/42")

        resolved = await registry.resolve_parameters(handler, request, match)
        assert resolved["id"] == 42

    @pytest.mark.asyncio
    async def test_request_injection(self):
        """Request 객체 주입"""
        registry = ResolverRegistry()

        async def handler(request: Request):
            return request.path

        route = Route("/test", "GET", handler)
        match = RouteMatch(route, {})
        request = make_request(path="/test")

        resolved = await registry.resolve_parameters(handler, request, match)
        assert resolved["request"] is request

    @pytest.mark.asyncio
    async def test_mixed_parameters(self):
        """혼합 파라미터"""
        registry = ResolverRegistry()

        async def handler(
            request: Request,
            user_id: PathVariable[int],
            include_posts: Query[bool] = Query(default=False),
        ):
            return {
                "path": request.path,
                "user_id": user_id,
                "include_posts": include_posts,
            }

        route = Route("/users/{user_id}", "GET", handler)
        match = RouteMatch(route, {"user_id": "123"})
        request = make_request(
            path="/users/123",
            query_string=b"include_posts=true",
        )

        resolved = await registry.resolve_parameters(handler, request, match)
        assert resolved["request"] is request
        assert resolved["user_id"] == 123
        assert resolved["include_posts"] is True


# === Request Cookie Tests ===


class TestRequestCookie:
    """Request cookie 메서드 테스트"""

    def test_cookies_parsing(self):
        """쿠키 파싱"""
        request = make_request(
            headers=[(b"cookie", b"session_id=abc123; user_id=42")]
        )

        assert request.cookies == {"session_id": "abc123", "user_id": "42"}

    def test_single_cookie(self):
        """단일 쿠키 조회"""
        request = make_request(
            headers=[(b"cookie", b"session_id=abc123")]
        )

        assert request.cookie("session_id") == "abc123"
        assert request.cookie("unknown") is None
        assert request.cookie("unknown", "default") == "default"

    def test_empty_cookies(self):
        """쿠키 없음"""
        request = make_request()

        assert request.cookies == {}
        assert request.cookie("session_id") is None
