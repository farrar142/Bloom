"""WebSocket/STOMP Registry 클래스들

Manager-Registry-Entry 패턴의 Registry 클래스들을 정의합니다.
기존 configurer.py의 Registry들을 AbstractRegistry 패턴으로 개선합니다.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bloom.core.abstract import AbstractRegistry

from .entry import (
    StompEndpointEntry,
    MessageHandlerEntry,
    SubscribeHandlerEntry,
    MessageExceptionHandlerEntry,
)

if TYPE_CHECKING:
    from bloom.core.container import HandlerContainer


# ============================================================================
# STOMP 엔드포인트 Registry
# ============================================================================


class StompEndpointRegistry(AbstractRegistry[StompEndpointEntry]):
    """
    STOMP 엔드포인트 Registry

    WebSocket/STOMP 엔드포인트를 관리합니다.
    @Factory로 생성하여 DI 컨테이너에 등록하면 자동으로 적용됩니다.

    사용 예시:
        @Component
        class WebSocketConfig:
            @Factory
            def stomp_endpoint_registry(self) -> StompEndpointRegistry:
                registry = StompEndpointRegistry()
                registry.add_endpoint("/ws").set_allowed_origins("*")
                registry.add_endpoint("/ws-sockjs").with_sockjs()
                return registry
    """

    def add_endpoint(self, path: str) -> "StompEndpointBuilder":
        """
        STOMP 엔드포인트 추가

        빌더 패턴으로 체이닝 설정 가능.

        Args:
            path: 엔드포인트 경로

        Returns:
            StompEndpointBuilder: 체이닝 설정용 빌더
        """
        entry = StompEndpointEntry(path=path)
        self._entries.append(entry)
        return StompEndpointBuilder(entry)

    def find_endpoint(self, path: str) -> StompEndpointEntry | None:
        """경로에 해당하는 엔드포인트 찾기"""
        for entry in self._entries:
            if entry.is_path_match(path):
                return entry
        return None

    def get_paths(self) -> list[str]:
        """등록된 엔드포인트 경로 목록"""
        return [entry.path for entry in self._entries]

    # 하위 호환성을 위한 property
    @property
    def endpoints(self) -> list[StompEndpointEntry]:
        """등록된 엔드포인트 목록 (하위 호환성)"""
        return list(self._entries)


class StompEndpointBuilder:
    """StompEndpointEntry 빌더 (체이닝 설정용)"""

    def __init__(self, entry: StompEndpointEntry):
        self._entry = entry

    def set_allowed_origins(self, *origins: str) -> "StompEndpointBuilder":
        """허용할 origin 설정"""
        # dataclass는 frozen이 아니므로 직접 수정
        object.__setattr__(self._entry, "allowed_origins", list(origins))
        return self

    def set_allowed_origin_patterns(self, *patterns: str) -> "StompEndpointBuilder":
        """허용할 origin 패턴 설정 (정규식)"""
        object.__setattr__(self._entry, "allowed_origin_patterns", list(patterns))
        return self

    def with_sockjs(self) -> "StompEndpointBuilder":
        """SockJS 폴백 활성화"""
        object.__setattr__(self._entry, "sockjs_enabled", True)
        return self

    def set_heartbeat(
        self, send_interval: int, receive_interval: int
    ) -> "StompEndpointBuilder":
        """하트비트 간격 설정 (밀리초)"""
        object.__setattr__(self._entry, "heartbeat_send", send_interval)
        object.__setattr__(self._entry, "heartbeat_receive", receive_interval)
        return self


# ============================================================================
# 메시지 핸들러 Registry
# ============================================================================


class MessageHandlerRegistry(AbstractRegistry[MessageHandlerEntry]):
    """
    메시지 핸들러 Registry

    @MessageMapping으로 등록된 핸들러들을 관리합니다.
    """

    def add(
        self,
        destination_pattern: str,
        handler_container: "HandlerContainer",
        owner_cls: type | None = None,
        send_to: str | None = None,
        send_to_user: str | None = None,
    ) -> MessageHandlerEntry:
        """메시지 핸들러 추가"""
        entry = MessageHandlerEntry(
            destination_pattern=destination_pattern,
            handler_container=handler_container,
            owner_cls=owner_cls,
            send_to=send_to,
            send_to_user=send_to_user,
        )
        self._entries.append(entry)
        return entry

    def find_handler(
        self, destination: str
    ) -> tuple[MessageHandlerEntry, dict[str, str]] | None:
        """
        목적지에 매칭되는 핸들러 찾기

        Returns:
            (핸들러 Entry, path variables) 또는 None
        """
        for entry in self._entries:
            path_vars = entry.matches(destination)
            if path_vars is not None:
                return (entry, path_vars)
        return None


class SubscribeHandlerRegistry(AbstractRegistry[SubscribeHandlerEntry]):
    """
    구독 핸들러 Registry

    @SubscribeMapping으로 등록된 핸들러들을 관리합니다.
    """

    def add(
        self,
        destination_pattern: str,
        handler_container: "HandlerContainer",
        owner_cls: type | None = None,
    ) -> SubscribeHandlerEntry:
        """구독 핸들러 추가"""
        entry = SubscribeHandlerEntry(
            destination_pattern=destination_pattern,
            handler_container=handler_container,
            owner_cls=owner_cls,
        )
        self._entries.append(entry)
        return entry

    def find_handler(
        self, destination: str
    ) -> tuple[SubscribeHandlerEntry, dict[str, str]] | None:
        """
        목적지에 매칭되는 핸들러 찾기

        Returns:
            (핸들러 Entry, path variables) 또는 None
        """
        for entry in self._entries:
            path_vars = entry.matches(destination)
            if path_vars is not None:
                return (entry, path_vars)
        return None


class MessageExceptionHandlerRegistry(AbstractRegistry[MessageExceptionHandlerEntry]):
    """
    메시지 예외 핸들러 Registry

    @MessageExceptionHandler로 등록된 핸들러들을 관리합니다.
    """

    def add(
        self,
        exception_type: type[Exception],
        handler_container: "HandlerContainer",
        owner_cls: type | None = None,
    ) -> MessageExceptionHandlerEntry:
        """예외 핸들러 추가"""
        entry = MessageExceptionHandlerEntry(
            exception_type=exception_type,
            handler_container=handler_container,
            owner_cls=owner_cls,
        )
        self._entries.append(entry)
        return entry

    def find_handler(self, exception: Exception) -> MessageExceptionHandlerEntry | None:
        """
        예외에 매칭되는 핸들러 찾기 (MRO 거리로 정렬)
        """
        candidates = [entry for entry in self._entries if entry.can_handle(exception)]
        if not candidates:
            return None
        # MRO 거리가 가장 작은 핸들러 반환
        candidates.sort(key=lambda e: e.get_mro_distance(exception))
        return candidates[0]


# ============================================================================
# 메시지 브로커 설정 (기존 유지)
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
    cache_limit: int = 1024
    preserve_publish_order: bool = True


class MessageBrokerRegistry:
    """
    메시지 브로커 Registry

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
        """Simple Broker 활성화"""
        self._config.simple_broker_destinations = list(destination_prefixes)
        return self

    def set_application_destination_prefixes(
        self, *prefixes: str
    ) -> "MessageBrokerRegistry":
        """애플리케이션 목적지 프리픽스 설정"""
        self._config.application_destination_prefixes = list(prefixes)
        return self

    def set_user_destination_prefix(self, prefix: str) -> "MessageBrokerRegistry":
        """사용자 목적지 프리픽스 설정"""
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
    "StompEndpointBuilder",
    # 핸들러
    "MessageHandlerRegistry",
    "SubscribeHandlerRegistry",
    "MessageExceptionHandlerRegistry",
    # 브로커
    "MessageBrokerRegistry",
    "MessageBrokerConfig",
]
