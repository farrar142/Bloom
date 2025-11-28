"""STOMP 엔드포인트 Registry"""

from bloom.core.abstract import AbstractRegistry

from ..entry import StompEndpointEntry


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


__all__ = [
    "StompEndpointRegistry",
    "StompEndpointBuilder",
]
