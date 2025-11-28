"""WebSocket/STOMP Entry 클래스들

Manager-Registry-Entry 패턴의 Entry 클래스들을 정의합니다.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from bloom.core.abstract import Entry

if TYPE_CHECKING:
    from bloom.core.container import HandlerContainer


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


@dataclass
class MessageHandlerEntry(Entry):
    """
    메시지 핸들러 Entry

    @MessageMapping으로 등록된 핸들러 정보를 담습니다.

    Attributes:
        destination_pattern: 목적지 패턴 (예: "/chat.send", "/chat.{roomId}")
        handler_container: 핸들러 컨테이너
        owner_cls: 핸들러를 소유한 컨트롤러 클래스
        send_to: @SendTo 목적지 (있는 경우)
        send_to_user: @SendToUser 목적지 (있는 경우)
    """

    destination_pattern: str
    handler_container: "HandlerContainer"
    owner_cls: type | None = None
    send_to: str | None = None
    send_to_user: str | None = None

    def matches(self, destination: str) -> dict[str, str] | None:
        """
        목적지가 이 핸들러 패턴과 일치하는지 확인

        Returns:
            일치하면 path variables 딕셔너리, 불일치하면 None
        """
        import re

        # /chat.{roomId} → /chat.(?P<roomId>[^/]+) 변환
        regex_pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", self.destination_pattern)
        regex_pattern = f"^{regex_pattern}$"

        match = re.match(regex_pattern, destination)
        if match:
            return match.groupdict()
        return None

    def __repr__(self) -> str:
        owner = self.owner_cls.__name__ if self.owner_cls else "Unknown"
        return (
            f"MessageHandlerEntry(pattern={self.destination_pattern!r}, "
            f"owner={owner})"
        )


@dataclass
class SubscribeHandlerEntry(Entry):
    """
    구독 핸들러 Entry

    @SubscribeMapping으로 등록된 핸들러 정보를 담습니다.

    Attributes:
        destination_pattern: 구독 목적지 패턴
        handler_container: 핸들러 컨테이너
        owner_cls: 핸들러를 소유한 컨트롤러 클래스
    """

    destination_pattern: str
    handler_container: "HandlerContainer"
    owner_cls: type | None = None

    def matches(self, destination: str) -> dict[str, str] | None:
        """목적지가 이 핸들러 패턴과 일치하는지 확인"""
        import re

        regex_pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", self.destination_pattern)
        regex_pattern = f"^{regex_pattern}$"

        match = re.match(regex_pattern, destination)
        if match:
            return match.groupdict()
        return None

    def __repr__(self) -> str:
        owner = self.owner_cls.__name__ if self.owner_cls else "Unknown"
        return (
            f"SubscribeHandlerEntry(pattern={self.destination_pattern!r}, "
            f"owner={owner})"
        )


@dataclass
class MessageExceptionHandlerEntry(Entry):
    """
    메시지 예외 핸들러 Entry

    @MessageExceptionHandler로 등록된 핸들러 정보를 담습니다.

    Attributes:
        exception_type: 처리할 예외 타입
        handler_container: 핸들러 컨테이너
        owner_cls: 핸들러를 소유한 컨트롤러 클래스
    """

    exception_type: type[Exception]
    handler_container: "HandlerContainer"
    owner_cls: type | None = None

    def can_handle(self, exception: Exception) -> bool:
        """이 핸들러가 주어진 예외를 처리할 수 있는지 확인"""
        return isinstance(exception, self.exception_type)

    def get_mro_distance(self, exception: Exception) -> int:
        """예외 타입과의 MRO 거리 반환"""
        exc_type = type(exception)
        if self.exception_type == exc_type:
            return 0
        try:
            return exc_type.__mro__.index(self.exception_type)
        except ValueError:
            return 9999

    def __repr__(self) -> str:
        owner = self.owner_cls.__name__ if self.owner_cls else "Unknown"
        return (
            f"MessageExceptionHandlerEntry("
            f"exception={self.exception_type.__name__}, owner={owner})"
        )


__all__ = [
    "StompEndpointEntry",
    "MessageHandlerEntry",
    "SubscribeHandlerEntry",
    "MessageExceptionHandlerEntry",
]
