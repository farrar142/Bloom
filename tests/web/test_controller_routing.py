"""Controller 라우팅 및 파라미터 바인딩 테스트"""

import pytest
from typing import Any

from bloom import Application
from bloom.core import reset_container_manager
from bloom.web import (
    Controller,
    GetMapping,
    PostMapping,
    RequestMapping,
    JSONResponse,
    PathVariable,
    Query,
    RequestBody,
    Request,
)
from bloom.web.routing.resolver import ResolverRegistry, ParameterInfo
from bloom.web.routing.router import Route, RouteMatch


class TestResolverRegistry:
    """ResolverRegistry 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_container_manager()
        yield
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_resolve_no_params(self):
        """파라미터 없는 핸들러"""

        async def handler():
            return "ok"

        registry = ResolverRegistry()
        route = Route(path="/test", method="GET", handler=handler)
        match = RouteMatch(route=route, path_params={})

        # Mock request
        request = MockRequest(path="/test", method="GET")

        params = await registry.resolve_parameters(handler, request, match)
        assert params == {}

    @pytest.mark.asyncio
    async def test_resolve_request_param(self):
        """Request 파라미터"""

        async def handler(request: Request):
            return request.path

        registry = ResolverRegistry()
        route = Route(path="/test", method="GET", handler=handler)
        match = RouteMatch(route=route, path_params={})

        request = MockRequest(path="/test", method="GET")

        params = await registry.resolve_parameters(handler, request, match)
        assert "request" in params
        assert params["request"] is request

    @pytest.mark.asyncio
    async def test_resolve_path_variable(self):
        """PathVariable 파라미터"""

        async def handler(user_id: PathVariable[int]):
            return user_id

        registry = ResolverRegistry()
        route = Route(path="/users/{user_id}", method="GET", handler=handler)
        match = RouteMatch(route=route, path_params={"user_id": "123"})

        request = MockRequest(path="/users/123", method="GET")

        params = await registry.resolve_parameters(handler, request, match)
        assert "user_id" in params
        assert params["user_id"] == 123

    @pytest.mark.asyncio
    async def test_resolve_query_param(self):
        """Query 파라미터"""

        async def handler(page: Query[int], size: Query[int] = 10):
            return {"page": page, "size": size}

        registry = ResolverRegistry()
        route = Route(path="/items", method="GET", handler=handler)
        match = RouteMatch(route=route, path_params={})

        request = MockRequest(
            path="/items",
            method="GET",
            query_params={"page": "2", "size": "20"},
        )

        params = await registry.resolve_parameters(handler, request, match)
        assert params["page"] == 2
        assert params["size"] == 20

    @pytest.mark.asyncio
    async def test_resolve_query_param_default(self):
        """Query 파라미터 기본값"""

        async def handler(page: Query[int] = 1, size: Query[int] = 10):
            return {"page": page, "size": size}

        registry = ResolverRegistry()
        route = Route(path="/items", method="GET", handler=handler)
        match = RouteMatch(route=route, path_params={})

        request = MockRequest(
            path="/items",
            method="GET",
            query_params={},  # 빈 쿼리
        )

        params = await registry.resolve_parameters(handler, request, match)
        assert params["page"] == 1
        assert params["size"] == 10

    @pytest.mark.asyncio
    async def test_resolve_mixed_params(self):
        """혼합 파라미터 (PathVariable + Query + Request)"""

        async def handler(
            request: Request,
            user_id: PathVariable[int],
            include_profile: Query[bool] = False,
        ):
            return {
                "user_id": user_id,
                "include_profile": include_profile,
            }

        registry = ResolverRegistry()
        route = Route(path="/users/{user_id}", method="GET", handler=handler)
        match = RouteMatch(route=route, path_params={"user_id": "42"})

        request = MockRequest(
            path="/users/42",
            method="GET",
            query_params={"include_profile": "true"},
        )

        params = await registry.resolve_parameters(handler, request, match)
        assert params["request"] is request
        assert params["user_id"] == 42
        assert params["include_profile"] is True


class TestControllerRouting:
    """Controller 라우팅 통합 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        reset_container_manager()
        yield
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_controller_no_params(self):
        """파라미터 없는 Controller 메서드"""

        @Controller
        @RequestMapping("/api/test")
        class TestController:
            @GetMapping
            async def list_items(self) -> JSONResponse:
                return JSONResponse({"items": [1, 2, 3]})

        app = Application("test-app")
        app.scan(TestController)
        await app.ready_async()

        # httpx로 ASGI 테스트
        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi), base_url="http://test"
        ) as client:
            response = await client.get("/api/test")
            if response.status_code != 200:
                print("Response:", response.text)
            assert response.status_code == 200
            data = response.json()
            assert data["items"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_controller_path_variable(self):
        """PathVariable이 있는 Controller 메서드"""

        @Controller
        @RequestMapping("/api/users")
        class UserController:
            @GetMapping("/{user_id}")
            async def get_user(self, user_id: PathVariable[int]) -> JSONResponse:
                return JSONResponse({"id": user_id, "name": f"User {user_id}"})

        app = Application("test-app")
        app.scan(UserController)
        await app.ready_async()

        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi), base_url="http://test"
        ) as client:
            response = await client.get("/api/users/123")
            if response.status_code != 200:
                print("Response:", response.status_code, response.text)
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == 123
            assert data["name"] == "User 123"

    @pytest.mark.asyncio
    async def test_controller_query_params(self):
        """Query 파라미터가 있는 Controller 메서드"""

        @Controller
        @RequestMapping("/api/items")
        class ItemController:
            @GetMapping
            async def list_items(
                self,
                page: Query[int] = 1,
                size: Query[int] = 10,
            ) -> JSONResponse:
                return JSONResponse({"page": page, "size": size})

        app = Application("test-app")
        app.scan(ItemController)
        await app.ready_async()

        import httpx

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi), base_url="http://test"
        ) as client:
            # 기본값 테스트
            response = await client.get("/api/items")
            assert response.status_code == 200
            data = response.json()
            assert data["page"] == 1
            assert data["size"] == 10

            # 쿼리 파라미터 전달
            response = await client.get("/api/items?page=3&size=25")
            assert response.status_code == 200
            data = response.json()
            assert data["page"] == 3
            assert data["size"] == 25


# === Mock Classes ===


class MockRequest:
    """테스트용 Mock Request"""

    def __init__(
        self,
        path: str = "/",
        method: str = "GET",
        query_params: dict[str, str] | None = None,
        path_params: dict[str, str] | None = None,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ):
        self.path = path
        self.method = method
        self._query_params = query_params or {}
        self.path_params = path_params or {}
        self._body = body
        self._headers = headers or {}

    @property
    def query_params(self) -> dict[str, list[str]]:
        """query_params를 list 형태로 반환 (실제 Request와 동일)"""
        return {k: [v] for k, v in self._query_params.items()}

    def query_param(self, name: str, default: str | None = None) -> str | None:
        """단일 쿼리 파라미터 값 조회"""
        values = self.query_params.get(name)
        if values:
            return values[0]
        return default

    async def body(self) -> bytes:
        return self._body

    async def json(self) -> Any:
        import json

        return json.loads(self._body)

    @property
    def headers(self) -> dict[str, str]:
        return self._headers
