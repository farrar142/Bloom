"""WebSocket 매니저

WebSocket 관련 컴포넌트들을 한 곳에서 관리하는 매니저 클래스입니다.
@EnableWebSocket 데코레이터가 붙은 컴포넌트가 있으면 WebSocket이 활성화됩니다.

사용 예시:
    from bloom import Component
    from bloom.web.messaging import EnableWebSocket, StompEndpointRegistry, MessageBrokerRegistry
    from bloom.core.decorators import Factory

    @Component
    @EnableWebSocket
    class WebSocketConfig:
        @Factory
        def stomp_endpoint_registry(self) -> StompEndpointRegistry:
            registry = StompEndpointRegistry()
            registry.add_endpoint("/ws").set_allowed_origins("*")
            return registry

        @Factory
        def message_broker_registry(self) -> MessageBrokerRegistry:
            registry = MessageBrokerRegistry()
            registry.enable_simple_broker("/topic", "/queue")
            registry.set_application_destination_prefixes("/app")
            return registry
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bloom.core.container import ComponentContainer
from bloom.core.container.element import Element

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager
    from .handler import StompProtocolHandler
    from .configurer import (
        StompEndpointRegistry,
        MessageBrokerRegistry,
        StompEndpoint,
    )


# ============================================================================
# @EnableWebSocket 데코레이터 및 Element
# ============================================================================


class EnableWebSocketElement(Element):
    """@EnableWebSocket 메타데이터를 담는 Element"""

    key = "enable_websocket"

    def __init__(self):
        super().__init__()
        self.metadata["enabled"] = True


def EnableWebSocket(cls: type) -> type:
    """
    WebSocket 기능을 활성화하는 데코레이터

    이 데코레이터가 붙은 @Component가 있으면 WebSocket 기능이 활성화됩니다.
    StompEndpointRegistry와 MessageBrokerRegistry를 @Factory로 정의하여
    WebSocket 설정을 구성할 수 있습니다.

    사용 예시:
        @Component
        @EnableWebSocket
        class WebSocketConfig:
            @Factory
            def stomp_endpoint_registry(self) -> StompEndpointRegistry:
                registry = StompEndpointRegistry()
                registry.add_endpoint("/ws")
                return registry

            @Factory
            def message_broker_registry(self) -> MessageBrokerRegistry:
                registry = MessageBrokerRegistry()
                registry.enable_simple_broker("/topic")
                return registry
    """
    container = ComponentContainer.get_or_create(cls)
    container.add_elements(EnableWebSocketElement())
    return cls


def is_websocket_enabled(cls: type) -> bool:
    """클래스에 @EnableWebSocket이 붙어있는지 확인"""
    container = ComponentContainer.get_container(cls)
    if container is None:
        return False
    return container.has_element(EnableWebSocketElement)


# ============================================================================
# WebSocketManager
# ============================================================================


class WebSocketManager:
    """
    WebSocket 관련 컴포넌트들을 관리하는 매니저

    Application에서 이 매니저를 통해 WebSocket 설정을 처리합니다.

    주요 역할:
    1. @EnableWebSocket 컴포넌트 감지
    2. StompEndpointRegistry / MessageBrokerRegistry 수집
    3. StompProtocolHandler 설정 적용
    4. 엔드포인트 경로 관리
    """

    def __init__(self, container_manager: "ContainerManager"):
        self._container_manager = container_manager
        self._enabled = False
        self._stomp_handler: "StompProtocolHandler | None" = None
        self._endpoint_registry: "StompEndpointRegistry | None" = None
        self._broker_registry: "MessageBrokerRegistry | None" = None
        self._endpoints: list["StompEndpoint"] = []

    @property
    def enabled(self) -> bool:
        """WebSocket이 활성화되어 있는지 여부"""
        return self._enabled

    @property
    def stomp_handler(self) -> "StompProtocolHandler | None":
        """StompProtocolHandler 인스턴스"""
        return self._stomp_handler

    @property
    def endpoints(self) -> list["StompEndpoint"]:
        """등록된 STOMP 엔드포인트 목록"""
        return self._endpoints.copy()

    def get_endpoint_paths(self) -> list[str]:
        """등록된 엔드포인트 경로 목록"""
        return [ep.path for ep in self._endpoints]

    def is_websocket_path(self, path: str) -> bool:
        """주어진 경로가 WebSocket 엔드포인트인지 확인"""
        for endpoint in self._endpoints:
            if path == endpoint.path or path.startswith(endpoint.path + "/"):
                return True
        return False

    def get_endpoint_for_path(self, path: str) -> "StompEndpoint | None":
        """경로에 해당하는 엔드포인트 반환"""
        for endpoint in self._endpoints:
            if path == endpoint.path or path.startswith(endpoint.path + "/"):
                return endpoint
        return None

    def initialize(self) -> None:
        """
        WebSocket 설정 초기화

        1. @EnableWebSocket 컴포넌트 확인
        2. StompEndpointRegistry / MessageBrokerRegistry 수집
        3. StompProtocolHandler 설정
        """
        # 1. @EnableWebSocket 컴포넌트 확인
        if not self._check_websocket_enabled():
            return

        self._enabled = True

        # 2. 레지스트리 수집
        self._collect_registries()

        # 3. StompProtocolHandler 설정
        self._configure_stomp_handler()

    def _check_websocket_enabled(self) -> bool:
        """@EnableWebSocket이 붙은 컴포넌트가 있는지 확인"""
        all_containers = self._container_manager.get_all_containers()

        for qual_containers in all_containers.values():
            for container in qual_containers.values():
                if isinstance(container, ComponentContainer):
                    if container.has_element(EnableWebSocketElement):
                        return True
        return False

    def _collect_registries(self) -> None:
        """StompEndpointRegistry와 MessageBrokerRegistry 수집"""
        from .configurer import StompEndpointRegistry, MessageBrokerRegistry

        # @Factory로 생성된 레지스트리 인스턴스 조회
        self._endpoint_registry = self._container_manager.get_instance(
            StompEndpointRegistry, raise_exception=False
        )
        self._broker_registry = self._container_manager.get_instance(
            MessageBrokerRegistry, raise_exception=False
        )

        # 엔드포인트 수집
        if self._endpoint_registry:
            self._endpoints = self._endpoint_registry.endpoints

    def _configure_stomp_handler(self) -> None:
        """StompProtocolHandler 설정 적용"""
        from .handler import StompProtocolHandler

        # StompProtocolHandler 인스턴스 조회
        self._stomp_handler = self._container_manager.get_instance(
            StompProtocolHandler, raise_exception=False
        )

        if self._stomp_handler is None:
            return

        # MessageBrokerRegistry 설정 적용
        if self._broker_registry:
            config = self._broker_registry.config
            self._stomp_handler.apply_config(config, self._endpoints)


__all__ = [
    "EnableWebSocket",
    "EnableWebSocketElement",
    "is_websocket_enabled",
    "WebSocketManager",
]
