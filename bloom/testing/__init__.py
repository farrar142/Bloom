"""Bloom 테스팅 유틸리티 패키지"""

from .client import TestClient, TestResponse
from .websocket import WebSocketTestClient, StompTestClient
from .mock import MockContainer, override_dependency, isolated_container
from .testcase import TestCase, AsyncTestCase
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

__all__ = [
    # TestCase (Django 스타일)
    "TestCase",
    "AsyncTestCase",
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
    # Assertion 헬퍼
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
