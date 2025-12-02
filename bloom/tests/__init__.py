"""Bloom 테스팅 유틸리티 패키지

pytest 기반 클래스형 테스트 (권장):
    from bloom.tests import BloomTestCase

    class TestMyService(BloomTestCase):
        components = [MyService]

        async def test_get_instance(self):
            service = self.get_instance(MyService)
            assert service is not None

        async def test_http(self):
            response = await self.get("/api/users")
            response.assert_ok().assert_json([{"id": 1}])

pytest 기반 함수형 테스트:
    from bloom.tests import BloomTestClient, AssertableResponse

    async def test_api(app):
        async with BloomTestClient(app) as client:
            (await client.get("/api/users"))
                .assert_ok()
                .assert_json([{"id": 1}])
"""

from .client import TestClient, TestResponse
from .websocket import WebSocketTestClient, StompTestClient
from .mock import MockContainer, override_dependency, isolated_container
from .testcase import BloomTestCase
from .utils import (
    create_test_app,
    AsyncTestHelper,
    assert_instance_of,
    assert_injected,
    assert_has_container,
    get_container_info,
    print_container_tree,
    SpyComponent,
    CallRecord,
)
from .pytest_plugin import (
    BloomTestClient,
    AssertableResponse,
    assert_instance,
    assert_injected_field,
    assert_container_exists,
    assert_raises_http,
)

__all__ = [
    # pytest 기반 클래스형 (권장)
    "BloomTestCase",
    # pytest 기반 함수형
    "BloomTestClient",
    "AssertableResponse",
    "assert_instance",
    "assert_injected_field",
    "assert_container_exists",
    "assert_raises_http",
    # HTTP 테스트
    "TestClient",
    "TestResponse",
    # WebSocket 테스트
    "WebSocketTestClient",
    "StompTestClient",
    # Mock
    "MockContainer",
    "override_dependency",
    "isolated_container",
    # 유틸리티
    "create_test_app",
    "AsyncTestHelper",
    # Assertion 헬퍼 (레거시)
    "assert_instance_of",
    "assert_injected",
    "assert_has_container",
    # 디버깅
    "get_container_info",
    "print_container_tree",
    # Spy
    "SpyComponent",
    "CallRecord",
]
