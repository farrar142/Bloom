"""메시지 핸들러 Registry"""

from typing import TYPE_CHECKING

from bloom.core.abstract import AbstractRegistry

from ..entry import MessageHandlerEntry

if TYPE_CHECKING:
    from bloom.core.container import HandlerContainer


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


__all__ = [
    "MessageHandlerRegistry",
]
