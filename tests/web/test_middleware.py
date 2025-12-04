"""Middleware 시스템 테스트"""

import pytest
from typing import Any


class TestMiddlewareComponent:
    """@MiddlewareComponent 데코레이터 테스트"""

    def test_middleware_component_decorator(self):
        """@MiddlewareComponent로 미들웨어 등록"""
        from bloom.web.middleware import (
            MiddlewareComponent,
            is_middleware_component,
            get_middleware_metadata,
        )

        @MiddlewareComponent(order=50)
        class TestMiddleware:
            async def __call__(self, request, call_next):
                return await call_next(request)

        assert is_middleware_component(TestMiddleware)
        metadata = get_middleware_metadata(TestMiddleware)
        assert metadata is not None
        assert metadata.order == 50
        assert metadata.path_pattern is None

    def test_middleware_component_with_path(self):
        """@MiddlewareComponent에 path 패턴 지정"""
        from bloom.web.middleware import MiddlewareComponent, get_middleware_metadata

        @MiddlewareComponent(order=10, path="/api/*")
        class ApiMiddleware:
            async def __call__(self, request, call_next):
                return await call_next(request)

        metadata = get_middleware_metadata(ApiMiddleware)
        assert metadata is not None
        assert metadata.order == 10
        assert metadata.path_pattern == "/api/*"


class TestMiddlewareStack:
    """MiddlewareStack 테스트"""

    def test_middleware_ordering(self):
        """미들웨어가 order대로 정렬되는지 테스트"""
        from bloom.web.middleware.base import MiddlewareStack, Middleware

        call_order = []

        class Middleware1(Middleware):
            async def __call__(self, scope, receive, send):
                call_order.append(1)
                await self.app(scope, receive, send)

        class Middleware2(Middleware):
            async def __call__(self, scope, receive, send):
                call_order.append(2)
                await self.app(scope, receive, send)

        class Middleware3(Middleware):
            async def __call__(self, scope, receive, send):
                call_order.append(3)
                await self.app(scope, receive, send)

        async def final_app(scope, receive, send):
            call_order.append("final")

        stack = MiddlewareStack(final_app)
        # 순서를 섞어서 추가
        stack.add(Middleware2, order=20)
        stack.add(Middleware1, order=10)
        stack.add(Middleware3, order=30)

        app = stack.build()

        import asyncio

        asyncio.run(app({}, None, None))

        # order 순서대로 실행되어야 함 (10 -> 20 -> 30 -> final)
        assert call_order == [1, 2, 3, "final"]


class TestApplicationMiddleware:
    """Application.add_middleware() 테스트"""

    @pytest.mark.asyncio
    async def test_add_asgi_middleware(self):
        """ASGI 레벨 미들웨어 추가"""
        from bloom import Application
        from bloom.web.middleware import Middleware, CORSMiddleware
        from bloom.core import reset_container_manager

        # 컨테이너 초기화
        reset_container_manager()

        app = Application("test-app")

        # CORS 미들웨어 추가
        app.add_middleware(CORSMiddleware, order=0, allow_origins=["*"])

        assert len(app._middleware_entries) == 1
        entry = app._middleware_entries[0]
        assert entry.order == 0
        assert entry.middleware_cls == CORSMiddleware

    @pytest.mark.asyncio
    async def test_add_di_middleware(self):
        """DI 연동 미들웨어 추가"""
        from bloom import Application
        from bloom.web.middleware import MiddlewareComponent
        from bloom.core import Service, reset_container_manager

        # 컨테이너 초기화
        reset_container_manager()

        # DI 서비스
        @Service
        class AuthService:
            def verify(self, token: str) -> dict:
                return {"user_id": 123}

        # DI 미들웨어 (필드 주입)
        @MiddlewareComponent(order=50)
        class AuthMiddleware:
            auth_service: AuthService  # 필드 주입

            async def __call__(self, request, call_next):
                token = request.headers.get("Authorization")
                if token:
                    request.state["user"] = self.auth_service.verify(token)
                return await call_next(request)

        app = Application("test-app")
        app.add_middleware(AuthMiddleware, order=50)

        assert len(app._middleware_entries) == 1
        entry = app._middleware_entries[0]
        assert entry.order == 50
        assert entry.di_middleware_cls == AuthMiddleware

    @pytest.mark.asyncio
    async def test_function_middleware(self):
        """함수 미들웨어 데코레이터"""
        from bloom import Application
        from bloom.core import reset_container_manager

        # 컨테이너 초기화
        reset_container_manager()

        app = Application("test-app")

        @app.middleware(order=10)
        async def logging_middleware(request, call_next):
            print(f"Request: {request.path}")
            response = await call_next(request)
            print(f"Response sent")
            return response

        assert len(app._middleware_entries) == 1
        entry = app._middleware_entries[0]
        assert entry.order == 10
        assert entry.func_middleware == logging_middleware

    @pytest.mark.asyncio
    async def test_exception_handler_decorator(self):
        """@app.exception_handler() 데코레이터"""
        from bloom import Application
        from bloom.web import JSONResponse
        from bloom.core import reset_container_manager

        # 컨테이너 초기화
        reset_container_manager()

        app = Application("test-app")

        class CustomError(Exception):
            pass

        @app.exception_handler(CustomError)
        async def custom_error_handler(request, exc):
            return JSONResponse({"error": str(exc)}, status_code=400)

        assert CustomError in app._exception_handlers
        assert app._exception_handlers[CustomError] == custom_error_handler


class TestMiddlewareIntegration:
    """미들웨어 통합 테스트 (실제 HTTP 요청)"""

    @pytest.mark.asyncio
    async def test_middleware_chain_execution(self):
        """미들웨어 체인이 올바른 순서로 실행되는지 테스트"""
        import httpx
        from bloom import Application
        from bloom.web import Controller, GetMapping, JSONResponse, RequestMapping
        from bloom.core import reset_container_manager

        # 실행 순서 추적
        execution_order = []

        # 컨테이너 초기화
        reset_container_manager()

        app = Application("test-app")

        # 미들웨어 1 (order=10)
        @app.middleware(order=10)
        async def middleware1(request, call_next):
            execution_order.append("middleware1_before")
            response = await call_next(request)
            execution_order.append("middleware1_after")
            return response

        # 미들웨어 2 (order=20)
        @app.middleware(order=20)
        async def middleware2(request, call_next):
            execution_order.append("middleware2_before")
            response = await call_next(request)
            execution_order.append("middleware2_after")
            return response

        @Controller
        @RequestMapping("/api")
        class TestController:
            @GetMapping("/test")
            async def test_endpoint(self) -> JSONResponse:
                execution_order.append("handler")
                return JSONResponse({"message": "ok"})

        app.scan(TestController)
        await app.ready_async()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/test")
            assert response.status_code == 200

        # 실행 순서 확인
        # middleware1(order=10) -> middleware2(order=20) -> handler -> middleware2 -> middleware1
        assert execution_order == [
            "middleware1_before",
            "middleware2_before",
            "handler",
            "middleware2_after",
            "middleware1_after",
        ]

        await app.shutdown_async()

    @pytest.mark.asyncio
    async def test_di_middleware_injection(self):
        """DI 미들웨어에 의존성이 주입되는지 테스트"""
        import httpx
        from bloom import Application
        from bloom.web import (
            Controller,
            GetMapping,
            JSONResponse,
            MiddlewareComponent,
            RequestMapping,
        )
        from bloom.core import Service, reset_container_manager, get_container_manager

        # 컨테이너 초기화
        reset_container_manager()

        app = Application("test-app")
        # 새 컨테이너 매니저 사용하도록 캐시 무효화
        app._container_manager = None

        # 서비스
        @Service
        class CounterService:
            def __init__(self):
                self.count = 0

            def increment(self):
                self.count += 1
                return self.count

        # DI 미들웨어
        @MiddlewareComponent(order=10)
        class CounterMiddleware:
            counter: CounterService

            async def __call__(self, request, call_next):
                # request.state 대신 counter 직접 증가
                self.counter.increment()
                return await call_next(request)

        @Controller
        @RequestMapping("/api")
        class TestController:
            @GetMapping("/count")
            async def get_count(self) -> JSONResponse:
                return JSONResponse({"message": "ok"})

        app.scan(CounterService, CounterMiddleware, TestController)
        await app.ready_async()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi),
            base_url="http://test",
        ) as client:
            # 3번 요청
            r1 = await client.get("/api/count")
            r2 = await client.get("/api/count")
            r3 = await client.get("/api/count")
            print(f"Responses: {r1.status_code}, {r2.status_code}, {r3.status_code}")

        # CounterService 확인
        manager = get_container_manager()
        counter = await manager.get_instance_async(CounterService)
        print(f"counter.count: {counter.count}, id: {id(counter)}")
        print(f"middleware_entries: {len(app._middleware_entries)}")
        assert counter.count == 3

        await app.shutdown_async()

    @pytest.mark.asyncio
    async def test_path_pattern_middleware(self):
        """경로 패턴이 지정된 미들웨어 테스트"""
        import httpx
        from bloom import Application
        from bloom.web import Controller, GetMapping, JSONResponse
        from bloom.core import reset_container_manager

        # 컨테이너 초기화
        reset_container_manager()

        api_calls = []
        all_calls = []

        app = Application("test-app")

        # /api/* 경로에만 적용
        @app.middleware(order=10, path="/api/*")
        async def api_middleware(request, call_next):
            api_calls.append(request.path)
            return await call_next(request)

        # 모든 경로에 적용
        @app.middleware(order=20)
        async def global_middleware(request, call_next):
            all_calls.append(request.path)
            return await call_next(request)

        @Controller
        class TestController:
            @GetMapping("/api/users")
            async def api_users(self) -> JSONResponse:
                return JSONResponse({"users": []})

            @GetMapping("/health")
            async def health(self) -> JSONResponse:
                return JSONResponse({"status": "ok"})

        app.scan(TestController)
        await app.ready_async()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi),
            base_url="http://test",
        ) as client:
            await client.get("/api/users")
            await client.get("/health")

        # /api/* 미들웨어는 /api/users에만 적용
        assert api_calls == ["/api/users"]
        # 전역 미들웨어는 모두 적용
        assert all_calls == ["/api/users", "/health"]

        await app.shutdown_async()
