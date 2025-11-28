"""WebSocket/STOMP 설정 레지스트리

Spring의 WebSocket 설정 패턴을 참고하여 구현.
MessageBrokerRegistry와 StompEndpointRegistry를 @Factory로 생성하여 설정합니다.

사용 예시:
    from bloom import Component
    from bloom.core.decorators import Factory
    from bloom.web.messaging import StompEndpointRegistry, MessageBrokerRegistry

    @Component
    class WebSocketConfig:
        @Factory
        def stomp_endpoint_registry(self) -> StompEndpointRegistry:
            registry = StompEndpointRegistry()
            registry.add_endpoint("/ws").set_allowed_origins("*")
            registry.add_endpoint("/ws-sockjs").with_sockjs()
            return registry

        @Factory
        def message_broker_registry(self) -> MessageBrokerRegistry:
            registry = MessageBrokerRegistry()
            registry.enable_simple_broker("/topic", "/queue")
            registry.set_application_destination_prefixes("/app")
            registry.set_user_destination_prefix("/user")
            return registry
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .broker import SimpleBroker


# ============================================================================
# STOMP 엔드포인트 설정
# ============================================================================


@dataclass
class StompEndpoint:
    """STOMP 엔드포인트 설정"""

    path: str
    allowed_origins: list[str] = field(default_factory=lambda: ["*"])
    allowed_origin_patterns: list[str] = field(default_factory=list)
    sockjs_enabled: bool = False
    heartbeat_send: int = 10000  # ms
    heartbeat_receive: int = 10000  # ms

    def set_allowed_origins(self, *origins: str) -> "StompEndpoint":
        """허용할 origin 설정"""
        self.allowed_origins = list(origins)
        return self

    def set_allowed_origin_patterns(self, *patterns: str) -> "StompEndpoint":
        """허용할 origin 패턴 설정 (정규식)"""
        self.allowed_origin_patterns = list(patterns)
        return self

    def with_sockjs(self) -> "StompEndpoint":
        """SockJS 폴백 활성화"""
        self.sockjs_enabled = True
        return self

    def set_heartbeat(
        self, send_interval: int, receive_interval: int
    ) -> "StompEndpoint":
        """하트비트 간격 설정 (밀리초)"""
        self.heartbeat_send = send_interval
        self.heartbeat_receive = receive_interval
        return self


class StompEndpointRegistry:
    """
    STOMP 엔드포인트 레지스트리

    @Factory로 생성하여 DI 컨테이너에 등록하면 자동으로 적용됩니다.

    사용 예시:
        @Component
        class WebSocketConfig:
            @Factory
            def stomp_endpoint_registry(self) -> StompEndpointRegistry:
                registry = StompEndpointRegistry()
                registry.add_endpoint("/ws").set_allowed_origins("*")
                return registry
    """

    def __init__(self):
        self._endpoints: list[StompEndpoint] = []

    def add_endpoint(self, path: str) -> StompEndpoint:
        """STOMP 엔드포인트 추가"""
        endpoint = StompEndpoint(path=path)
        self._endpoints.append(endpoint)
        return endpoint

    @property
    def endpoints(self) -> list[StompEndpoint]:
        """등록된 엔드포인트 목록"""
        return self._endpoints.copy()


# ============================================================================
# 메시지 브로커 설정
# ============================================================================


@dataclass
class MessageBrokerConfig:
    """메시지 브로커 설정 데이터"""

    # Simple Broker 설정
    simple_broker_destinations: list[str] = field(default_factory=list)

    # 애플리케이션 목적지 프리픽스 (/app으로 시작하는 메시지는 @MessageMapping으로 라우팅)
    application_destination_prefixes: list[str] = field(
        default_factory=lambda: ["/app"]
    )

    # 사용자 목적지 프리픽스 (@SendToUser 사용 시)
    user_destination_prefix: str = "/user"

    # 브로커 채널 설정
    cache_limit: int = 1024  # 캐시할 메시지 수
    preserve_publish_order: bool = True  # 발행 순서 유지


class MessageBrokerRegistry:
    """
    메시지 브로커 레지스트리

    @Factory로 생성하여 DI 컨테이너에 등록하면 자동으로 적용됩니다.

    사용 예시:
        @Component
        class WebSocketConfig:
            @Factory
            def message_broker_registry(self) -> MessageBrokerRegistry:
                registry = MessageBrokerRegistry()
                registry.enable_simple_broker("/topic", "/queue")
                registry.set_application_destination_prefixes("/app")
                return registry
    """

    def __init__(self):
        self._config = MessageBrokerConfig()

    def enable_simple_broker(
        self, *destination_prefixes: str
    ) -> "MessageBrokerRegistry":
        """
        Simple Broker 활성화

        지정된 프리픽스로 시작하는 목적지에 대해 인메모리 브로커 사용.

        예시:
            registry.enable_simple_broker("/topic", "/queue")
        """
        self._config.simple_broker_destinations = list(destination_prefixes)
        return self

    def set_application_destination_prefixes(
        self, *prefixes: str
    ) -> "MessageBrokerRegistry":
        """
        애플리케이션 목적지 프리픽스 설정

        이 프리픽스로 시작하는 메시지는 @MessageMapping 핸들러로 라우팅됨.

        예시:
            registry.set_application_destination_prefixes("/app", "/api")
        """
        self._config.application_destination_prefixes = list(prefixes)
        return self

    def set_user_destination_prefix(self, prefix: str) -> "MessageBrokerRegistry":
        """
        사용자 목적지 프리픽스 설정

        @SendToUser 사용 시 이 프리픽스가 붙음.

        예시:
            registry.set_user_destination_prefix("/user")
        """
        self._config.user_destination_prefix = prefix
        return self

    def set_cache_limit(self, limit: int) -> "MessageBrokerRegistry":
        """브로커 캐시 제한 설정"""
        self._config.cache_limit = limit
        return self

    def set_preserve_publish_order(self, preserve: bool) -> "MessageBrokerRegistry":
        """발행 순서 유지 여부 설정"""
        self._config.preserve_publish_order = preserve
        return self

    @property
    def config(self) -> MessageBrokerConfig:
        """설정 객체 반환"""
        return self._config


__all__ = [
    # 엔드포인트
    "StompEndpointRegistry",
    "StompEndpoint",
    # 브로커
    "MessageBrokerRegistry",
    "MessageBrokerConfig",
]
