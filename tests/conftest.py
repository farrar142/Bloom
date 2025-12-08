"""Test utilities for ASGI applications"""

from __future__ import annotations
from typing import Literal
import pytest
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport
from bloom.web.asgi import ASGIApplication
from bloom.web import GetMapping, Controller
from bloom import Application
from bloom.core import Component, Service, Handler
from bloom.web.decorators import PostMapping
from bloom.web.params import Cookie, Header, KeyValue


@Service
class MyService:
    @Handler
    async def greet(self, name: str) -> str:
        return f"Hello, {name}!"

    async def auto_converted_handler(self, name: str) -> str:
        await self.greet(name)  # This will be auto-converted to async
        return f"Hi, {name}!"


@Service
class SyncAsyncService:
    async def async_handler(self, value: int) -> int:
        return value * 2

    @Handler
    def sync_handler(self, value: int) -> int:
        return value + 2


@Component
class MyComponent:
    service: MyService
    synca_async_service: SyncAsyncService


@Controller
class MyController:
    component: MyComponent

    @GetMapping(path="/greet/{name}")
    async def greet_handler(self, name: str) -> dict:
        print(f"greet_handler called with name={name}")
        return {"message": await self.component.service.greet(name)}

    @PostMapping(path="/post/{post}")
    async def post_handler(self, field: int, post: int) -> dict:
        return {"field": field, "post": post}

    @PostMapping(path="/post/static")
    async def static_post_handler(
        self,
        authorization: Cookie[Literal["X-AUTHORIZATION"]],
        user_agent: Header,
    ) -> dict:
        print(authorization.value)
        return {"authorization": authorization.value, "user_agent": user_agent.value}


@pytest.fixture(scope="session", autouse=True)
def application() -> Application:
    """애플리케이션 초기화 및 종료를 위한 fixture"""
    return Application()
    # 애플리케이션 종료 로직이 필요하면 여기에 추가


@pytest.fixture(scope="session", autouse=True)
def asgi(application) -> ASGIApplication:
    """ASGI 애플리케이션 초기화 fixture"""
    asgi_app = ASGIApplication(application, debug=True)

    return asgi_app


@pytest.fixture
def asgi_client(asgi) -> AsyncClient:
    """ASGI 앱을 테스트하기 위한 httpx 클라이언트 fixture"""
    # httpx 클라이언트 생성 (ASGI transport 사용)

    transport = ASGITransport(app=asgi)
    client = AsyncClient(transport=transport, base_url="http://testserver")
    return client
