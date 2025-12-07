"""
코루틴 안전한 데코레이터 유틸리티 모듈
"""

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

P = ParamSpec("P")
T = TypeVar("T")
R = TypeVar("R")

# 메서드 타입 정의 (TypeAlias)
type SyncMethod[**P, T, R] = Callable[Concatenate[T, P], R]
type AsyncMethod[**P, T, R] = Callable[Concatenate[T, P], Coroutine[Any, Any, R]]
type Method[**P, T, R] = SyncMethod[P, T, R] | AsyncMethod[P, T, R]

# 데코레이터 타입 정의
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
    """
    async wrapper 하나로 동기/비동기 모두 지원하는 데코레이터로 변환.

    wrapper_factory가 async def wrapped를 반환하고, 내부에서
    is_coroutinefunction(func)로 분기 처리하는 패턴을 지원합니다.

    - 비동기 함수: async wrapper 그대로 적용
    - 동기 함수: wrapper 로직을 포함한 동기 버전 자동 생성

    Args:
        wrapper_factory: Method를 받아서 wrapped Method를 반환하는 팩토리
                        (내부에서 is_coroutinefunction으로 분기 처리 가능)

    Usage:
        def call_scope(func):
            async def wrapped(self, *args, **kwargs):
                with CallScope():
                    result = func(self, *args, **kwargs)
                    if is_coroutinefunction(func):
                        return await result
                    return result
            return wrapped

        safe_wrapper = auto_coroutine_decorator(call_scope)

        @safe_wrapper
        def sync_method(self, x: int) -> str: ...  # CallScope 적용 + 동기 실행

        @safe_wrapper
        async def async_method(self, x: int) -> str: ...  # CallScope 적용 + 비동기 실행
    """

    def decorator(func: Method[P, T, R]) -> AsyncMethod[P, T, R]:
        wrapped: Method[P, T, R] = wrapper_factory(func)

        async def async_wrapper(self: T, *args: P.args, **kwargs: P.kwargs) -> R:
            result: R | Coroutine[Any, Any, R] = wrapped(self, *args, **kwargs)
            if is_coroutine(result):
                return await result
            return cast(R, result)

        return async_wrapper

    return decorator
