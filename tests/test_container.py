from httpx import AsyncClient
from bloom import Application
from bloom.core import get_container_manager
from bloom.core.container.call_scope import call_stack
import pytest

from bloom.web.decorators import RouteContainer

from .conftest import MyComponent, MyController


class TestASGIApplication:
    """ASGI 애플리케이션 테스트"""

    @pytest.mark.asyncio
    async def test_initialize(self, application: Application):
        """GET 요청 테스트"""
        await application.ready()
        instance = application.container_manager.get_instance(MyComponent)
        assert isinstance(instance, MyComponent)
        pass

    @pytest.mark.asyncio
    async def test_injection(self, application: Application):
        """GET 요청 테스트"""
        await application.ready()
        instance = application.container_manager.get_instance(MyComponent)
        assert instance.service is not None
        print("before call handler method")
        frames = []

        async def call_handlers(frame):
            frames.append(frame)
            return

        stack = call_stack()
        stack.aadd_event_listener(call_handlers)
        assert await instance.service.greet("World") == "Hello, World!"
        assert len(frames) == 1
        assert await instance.service.auto_converted_handler("World") == "Hi, World!"
        assert len(frames) == 3
        print(frames)

    @pytest.mark.asyncio
    async def test_sync_async_handlers(self, application: Application):
        """동기 및 비동기 핸들러 테스트"""
        await application.ready()
        instance = application.container_manager.get_instance(MyComponent)
        assert instance.synca_async_service is not None
        # 비동기 핸들러 테스트
        result_async = await instance.synca_async_service.async_handler(5)
        assert result_async == 10

        # 동기 핸들러 테스트
        result_sync = instance.synca_async_service.sync_handler(5)
        assert result_sync == 7

    @pytest.mark.asyncio
    async def test_route_handler(self, application: Application):
        await application.ready()
        manager = get_container_manager()
        all_instances = manager.instances
        for key, value in all_instances.items():
            print(f"Instance Key: {key}, Value: {value}")
        for key, value in manager.containers.items():
            print(f"Container Key: {key}, Value: {value}")
        controller = manager.get_instance(MyController)
        route_containers = manager.get_containers_by_container_type(RouteContainer)
        routes = [manager.get_instance(r.component_id) for r in route_containers]
        print([await route("hello") for route in routes if route is not None])
