"""구독 핸들러 Registry"""

from typing import TYPE_CHECKING

from bloom.core.abstract import AbstractRegistry

from ..entry import SubscribeHandlerEntry

if TYPE_CHECKING:
    from bloom.core.container import HandlerContainer


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


__all__ = [
    "SubscribeHandlerRegistry",
]
