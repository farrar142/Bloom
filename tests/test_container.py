from httpx import AsyncClient
from bloom import Application
from bloom.core.call_scope import call_stack
import pytest

from .conftest import MyComponent


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
        stack.add_event_listener(call_handlers)
        assert await instance.service.greet("World") == "Hello, World!"
        assert len(frames) == 1
        assert await instance.service.auto_converted_handler("World") == "Hi, World!"
        assert len(frames) == 3
        print(frames)
