"""메시지 브로커 Registry"""

from dataclasses import dataclass, field


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
    "MessageBrokerRegistry",
    "MessageBrokerConfig",
]
