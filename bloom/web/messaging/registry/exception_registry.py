"""메시지 예외 핸들러 Registry"""

from typing import TYPE_CHECKING

from bloom.core.abstract import AbstractRegistry

from ..entry import MessageExceptionHandlerEntry

if TYPE_CHECKING:
    from bloom.core.container import HandlerContainer


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


__all__ = [
    "MessageExceptionHandlerRegistry",
]
