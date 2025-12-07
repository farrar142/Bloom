"""
코루틴 안전한 데코레이터 유틸리티 모듈
"""

import inspect
from typing import (
    Any,
    Awaitable,
    Callable,
    Concatenate,
    TypeGuard,
    cast,
)

type Method[**P, T, R] = Callable[Concatenate[T, P], R | Awaitable[R]]
type SyncMethod[**P, T, R] = Callable[Concatenate[T, P], R]
type AsyncMethod[**P, T, R] = Callable[Concatenate[T, P], Awaitable[R]]


def is_coroutinefunction[**P, T, R](
    func: Method[P, T, R],
) -> TypeGuard[AsyncMethod[P, T, R]]:
    """함수가 코루틴 함수인지 확인하는 TypeGuard"""
    return inspect.iscoroutinefunction(func)


def auto_coroutine_decorator[**P, T, R](
    wrapper_factory: Callable[[Method[P, T, R]], Method[P, T, R]],
) -> Callable[[Method[P, T, R]], Method[P, T, R]]:
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

    def decorator(func: Method[P, T, R]) -> Method[P, T, R]:
        if is_coroutinefunction(func):
            # 비동기 함수: async wrapper 그대로 적용
            return wrapper_factory(func)
        else:
            # 동기 함수: wrapper를 적용하고 결과를 동기로 실행
            async_wrapped = wrapper_factory(func)

            # async_wrapped를 호출하면 코루틴이 반환됨
            # 이 코루틴은 내부에서 func()를 호출하고 await 없이 반환하므로
            # send(None)으로 한 번 실행하면 결과를 얻을 수 있음
            def sync_wrapped(self: T, *args: P.args, **kwargs: P.kwargs) -> R:
                coro = async_wrapped(self, *args, **kwargs)
                try:
                    # 코루틴을 실행하여 결과 얻기
                    # 내부에서 await가 없으면 StopIteration으로 결과 반환
                    coro.send(None)
                except StopIteration as e:
                    return e.value  # type: ignore
                finally:
                    coro.close()
                # 여기에 도달하면 안 됨 (await가 있는 경우)
                raise RuntimeError("Wrapper contains await for sync function")

            return sync_wrapped  # type: ignore

    return decorator
