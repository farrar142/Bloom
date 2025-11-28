"""STOMP 엔드포인트 Entry"""

from dataclasses import dataclass, field

from bloom.core.abstract import Entry


@dataclass
class StompEndpointEntry(Entry):
    """
    STOMP 엔드포인트 Entry

    WebSocket 엔드포인트 설정 정보를 담는 불변 데이터 클래스입니다.

    Attributes:
        path: 엔드포인트 경로 (예: "/ws", "/ws-sockjs")
        allowed_origins: 허용된 origin 목록
        allowed_origin_patterns: 허용된 origin 패턴 목록 (정규식)
        sockjs_enabled: SockJS 폴백 활성화 여부
        heartbeat_send: 서버→클라이언트 하트비트 간격 (ms)
        heartbeat_receive: 클라이언트→서버 하트비트 간격 (ms)
    """

    path: str
    allowed_origins: list[str] = field(default_factory=lambda: ["*"])
    allowed_origin_patterns: list[str] = field(default_factory=list)
    sockjs_enabled: bool = False
    heartbeat_send: int = 10000
    heartbeat_receive: int = 10000

    def is_path_match(self, request_path: str) -> bool:
        """요청 경로가 이 엔드포인트에 해당하는지 확인"""
        return request_path == self.path or request_path.startswith(self.path + "/")

    def is_origin_allowed(self, origin: str | None) -> bool:
        """origin이 허용되는지 확인"""
        if origin is None:
            return True
        if "*" in self.allowed_origins:
            return True
        if origin in self.allowed_origins:
            return True
        # 패턴 매칭
        import re

        for pattern in self.allowed_origin_patterns:
            if re.match(pattern, origin):
                return True
        return False

    def __repr__(self) -> str:
        return (
            f"StompEndpointEntry(path={self.path!r}, " f"sockjs={self.sockjs_enabled})"
        )


__all__ = ["StompEndpointEntry"]
