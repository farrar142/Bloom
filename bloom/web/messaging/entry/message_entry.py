"""메시지 핸들러 Entry"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bloom.core.container import HandlerContainer


@dataclass
class MessageHandlerEntry:
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


__all__ = ["MessageHandlerEntry"]
