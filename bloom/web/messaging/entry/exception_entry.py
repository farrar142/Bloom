"""메시지 예외 핸들러 Entry"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from bloom.core.abstract import Entry

if TYPE_CHECKING:
    from bloom.core.container import HandlerContainer


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


__all__ = ["MessageExceptionHandlerEntry"]
