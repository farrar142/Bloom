from typing import Callable, Self, cast
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
        return wraps(self.func)(final_method)  # type:ignore

    @classmethod
    def register(cls, func: Method[P, T, R]):
        if not hasattr(func, "__component_id__"):
            func.__component_id__ = str(uuid4())

        registry = get_container_registry()

        if func not in registry:
            registry[func] = {}

        if func.__component_id__ not in registry[func]:

            registry[func][func.__component_id__] = cls(func, func.__component_id__)
        container: Self = registry[func][func.__component_id__]  # type:ignore

        return container
