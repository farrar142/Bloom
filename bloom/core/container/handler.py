from typing import Callable, cast
from functools import reduce, wraps
from uuid import uuid4

from .manager import get_container_registry
from .scope import call_scope_manager, ScopeContext
from .base import Container
from .functions import (
    Method,
    AsyncMethod,
    SyncMethod,
    safe_decorator_factory,
)


def async_call_scope_wrapper[**P, T, R](
    func: AsyncMethod[P, T, R],
) -> AsyncMethod[P, T, R]:
    """CallScope를 적용하는 wrapper - async 버전

    call_scope_manager()를 사용하여 CallStackTracker와 ScopeContext를 모두 관리합니다.
    """

    async def wrapped(self: T, *args: P.args, **kwargs: P.kwargs) -> R:
        async with call_scope_manager() as scope_context:
            result = func(self, *args, **kwargs)
            return await result

    return wrapped


def sync_call_scope_wrapper[**P, T, R](
    func: SyncMethod[P, T, R],
) -> SyncMethod[P, T, R]:
    """CallScope를 적용하는 wrapper - sync 버전

    call_scope_manager()를 사용하여 CallStackTracker와 ScopeContext를 모두 관리합니다.
    """

    def wrapped(self: T, *args: P.args, **kwargs: P.kwargs) -> R:
        with call_scope_manager() as scope_context:
            result = func(self, *args, **kwargs)
            return cast(R, result)

    return wrapped


class HandlerContainer[**P, T, R](Container[Method[P, T, R]]):
    """핸들러 컨테이너 클래스"""

    _wrappers: list[Callable[[Method[P, T, R]], Method[P, T, R]]]

    def __init__(self, kls: Method[P, T, R], component_id: str) -> None:
        super().__init__(kls, component_id)
        self.func = kls
        self._wrappers = []

        self._wrappers.append(
            safe_decorator_factory(sync_call_scope_wrapper, async_call_scope_wrapper)
        )

    async def initialize(self) -> Method[P, T, R]:
        final_method = reduce(
            lambda next_func, wrapper_factory: wrapper_factory(next_func),
            reversed(self._wrappers),
            self.func,
        )
        return cast(Method[P, T, R], wraps(self.func)(final_method))

    @classmethod
    def register(cls, func: Method[P, T, R]) -> "Container":
        """Handler 메서드를 HandlerContainer로 등록

        기존 Container가 있으면 elements를 흡수합니다.
        """
        from .base import Container

        if not hasattr(func, "__component_id__"):
            func.__component_id__ = str(uuid4())

        new_container = cls(func, func.__component_id__)
        return cls.transfer_or_absorb(func, new_container)
