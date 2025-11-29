"""구독 핸들러 Entry"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bloom.core.container import HandlerContainer


@dataclass
class SubscribeHandlerEntry:
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


__all__ = ["SubscribeHandlerEntry"]
