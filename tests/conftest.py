"""Test utilities for ASGI applications"""

import pytest
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport
from bloom.web.asgi import ASGIApplication
from bloom import Application
from bloom.core import Component, Service, Handler


@Service
class MyService:
    @Handler
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"


@Component
class MyComponent:
    service: MyService


@pytest.fixture(scope="session", autouse=True)
def application() -> Application:
    """애플리케이션 초기화 및 종료를 위한 fixture"""
    return Application()
    # 애플리케이션 종료 로직이 필요하면 여기에 추가


@pytest.fixture
def asgi_client(application) -> AsyncClient:
    """ASGI 앱을 테스트하기 위한 httpx 클라이언트 fixture"""
    # httpx 클라이언트 생성 (ASGI transport 사용)

    transport = ASGITransport(app=ASGIApplication(application, debug=True))
    client = AsyncClient(transport=transport, base_url="http://testserver")
    return client
