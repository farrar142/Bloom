from httpx import AsyncClient
from bloom import Application
import pytest

from .conftest import MyComponent


class TestASGIApplication:
    """ASGI 애플리케이션 테스트"""

    @pytest.mark.asyncio
    async def test_get_request(self, application: Application):
        """GET 요청 테스트"""
        await application.ready()
        instance = application.container_manager.get_instance(MyComponent)
        assert isinstance(instance, MyComponent)
        pass
