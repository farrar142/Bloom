import pytest
from httpx import AsyncClient
from bloom.application import Application
from bloom.web import ASGIApplication


class TestASGIApplication:
    """ASGI 애플리케이션 테스트"""

    @pytest.mark.asyncio
    async def test_get_request(self, asgi: ASGIApplication, asgi_client: AsyncClient):
        """GetMapping 요청 테스트"""
        await asgi.ready()
        response = await asgi_client.get("/greet/Tester")
        assert response.status_code == 200
        assert response.json() == {"message": "Hello, Tester!"}
