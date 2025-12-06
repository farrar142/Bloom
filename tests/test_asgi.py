"""ASGI Application 테스트 예시"""

import pytest
from httpx import AsyncClient


class TestASGIApplication:
    """ASGI 애플리케이션 테스트"""

    @pytest.mark.asyncio
    async def test_get_request(self, asgi_client: AsyncClient):
        """GET 요청 테스트"""
        response = await asgi_client.get("/test")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_matched_request(self, asgi_client: AsyncClient):
        """GET 요청 테스트"""
        response = await asgi_client.get("/response")

        assert response.status_code == 200
        assert response.json() == {"message": "Hello, ASGI!"}

    @pytest.mark.asyncio
    async def test_get_matched_method_request(self, asgi_client: AsyncClient):
        """GET 요청 테스트"""
        response = await asgi_client.post("/response")

        assert response.status_code == 200
        assert response.json() == {"message": "Hello, POST!"}
