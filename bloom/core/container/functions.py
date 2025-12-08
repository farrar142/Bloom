"""
코루틴 안전한 데코레이터 유틸리티 모듈
"""

from functools import wraps
import inspect
from typing import (
    Any,
    Callable,
    Concatenate,
    Coroutine,
    ParamSpec,
    TypeGuard,
    TypeVar,
    cast,
)


# 메서드 타입 정의 (TypeAlias)
type SyncMethod[**P, T, R] = Callable[Concatenate[T, P], R]
type AsyncMethod[**P, T, R] = Callable[Concatenate[T, P], Coroutine[Any, Any, R]]
type Method[**P, T, R] = SyncMethod[P, T, R] | AsyncMethod[P, T, R]

# 데코레이터 타입 정의
type SyncDecorator[**P, T, R] = Callable[[SyncMethod[P, T, R]], SyncMethod[P, T, R]]
type AsyncDecorator[**P, T, R] = Callable[[AsyncMethod[P, T, R]], AsyncMethod[P, T, R]]
type MethodDecorator[**P, T, R] = Callable[[Method[P, T, R]], Method[P, T, R]]
type SafeDecorator[**P, T, R] = Callable[[Method[P, T, R]], AsyncMethod[P, T, R]]


def is_coroutinefunction[**P, T, R](
    func: Method[P, T, R],
) -> TypeGuard[AsyncMethod[P, T, R]]:
    """함수가 코루틴 함수인지 확인하는 TypeGuard"""
    return inspect.iscoroutinefunction(func)


def is_syncfunction[**P, T, R](
    func: Method[P, T, R],
) -> TypeGuard[SyncMethod[P, T, R]]:
    """함수가 동기 함수인지 확인하는 TypeGuard"""
    return not inspect.iscoroutinefunction(func)


def is_coroutine[R](
    result: R | Coroutine[Any, Any, R],
) -> TypeGuard[Coroutine[Any, Any, R]]:
    """결과가 코루틴 객체인지 확인하는 TypeGuard"""
    return inspect.iscoroutine(result)


def auto_coroutine_decorator[**P, T, R](
    wrapper_factory: MethodDecorator[P, T, R],
) -> SafeDecorator[P, T, R]:
    def decorator(func: Method[P, T, R]) -> AsyncMethod[P, T, R]:
        wrapped: Method[P, T, R] = wrapper_factory(func)

        async def async_wrapper(self: T, *args: P.args, **kwargs: P.kwargs) -> R:
            result: R | Coroutine[Any, Any, R] = wrapped(self, *args, **kwargs)
            if is_coroutine(result):
                return await result
            return cast(R, result)

        return async_wrapper

    return decorator


def safe_decorator_factory[**P, T, R](
    sync_decorator: SyncDecorator[P, T, R],
    async_decorator: AsyncDecorator[P, T, R],
) -> MethodDecorator[P, T, R]:
    """동기 및 비동기 데코레이터를 자동으로 선택하는 팩토리 함수"""

    def decorator(func: Method[P, T, R]) -> Method[P, T, R]:
        if is_syncfunction(func):
            return wraps(func)(sync_decorator)(cast(SyncMethod[P, T, R], func))
        else:
            return wraps(func)(async_decorator)(cast(AsyncMethod[P, T, R], func))

    return decorator
