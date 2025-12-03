"""
AOP 데코레이터들

메서드에 적용되어 인터셉터 정보를 등록하는 데코레이터들.
"""

from typing import Any, Callable, TypeVar, ParamSpec, overload
from functools import wraps
import inspect

from .descriptor import (
    MethodDescriptor,
    InterceptorInfo,
    ensure_method_descriptor,
)


P = ParamSpec("P")
R = TypeVar("R")


def Order(value: int) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드 실행 순서를 지정하는 데코레이터.

    낮은 값이 먼저 실행됨 (인터셉터 체인에서 외부에 위치).

    Usage:
        @Order(1)
        async def first_method(self): ...

        @Order(2)
        async def second_method(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.order = value
        return func

    return decorator


def Before(
    callback: Callable[..., Any] | None = None,
    *,
    order: int = 0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드 실행 전에 콜백을 실행하는 데코레이터.

    Usage:
        @Before(lambda inv: print(f"Calling {inv.method_name}"))
        async def my_method(self): ...

        # 또는 콜백 없이 마킹만
        @Before()
        async def my_method(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="before",
                callback=callback,
                order=order,
            )
        )
        return func

    return decorator


def After(
    callback: Callable[..., Any] | None = None,
    *,
    order: int = 0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드 실행 후에 콜백을 실행하는 데코레이터 (예외 여부와 관계없이).

    Usage:
        @After(lambda inv, result, exc: print("Done"))
        async def my_method(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="after",
                callback=callback,
                order=order,
            )
        )
        return func

    return decorator


def Around(
    callback: Callable[..., Any] | None = None,
    *,
    order: int = 0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드 실행 전후를 모두 제어하는 데코레이터.

    Usage:
        async def timing_advice(join_point):
            start = time.time()
            result = await join_point.proceed()
            print(f"Took {time.time() - start}s")
            return result

        @Around(timing_advice)
        async def my_method(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="around",
                callback=callback,
                order=order,
            )
        )
        return func

    return decorator


def AfterReturning(
    callback: Callable[..., Any] | None = None,
    *,
    order: int = 0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드가 정상적으로 반환될 때만 콜백을 실행하는 데코레이터.

    콜백이 값을 반환하면 그 값이 메서드의 반환값이 됨.

    Usage:
        @AfterReturning(lambda inv, result: result.upper())
        async def get_name(self) -> str: ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="after_returning",
                callback=callback,
                order=order,
            )
        )
        return func

    return decorator


def AfterThrowing(
    callback: Callable[..., Any] | None = None,
    *,
    exception_type: type[Exception] = Exception,
    order: int = 0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드가 예외를 던질 때 콜백을 실행하는 데코레이터.

    Usage:
        @AfterThrowing(
            lambda inv, exc: log.error(f"Error: {exc}"),
            exception_type=ValueError
        )
        async def risky_method(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="after_throwing",
                callback=callback,
                order=order,
                metadata={"exception_type": exception_type},
            )
        )
        return func

    return decorator


# ============================================================
# 도메인 특화 데코레이터들 (메타데이터만 추가)
# ============================================================


def Transactional(
    *,
    propagation: str = "REQUIRED",
    isolation: str = "DEFAULT",
    read_only: bool = False,
    rollback_for: tuple[type[Exception], ...] = (Exception,),
    order: int = -100,  # 트랜잭션은 가장 먼저 시작해야 함
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    트랜잭션을 관리하는 데코레이터.

    실제 트랜잭션 로직은 TransactionalInterceptor가 처리.

    Usage:
        @Transactional()
        async def create_user(self, name: str): ...

        @Transactional(read_only=True)
        async def get_users(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="transactional",
                order=order,
                metadata={
                    "propagation": propagation,
                    "isolation": isolation,
                    "read_only": read_only,
                    "rollback_for": rollback_for,
                },
            )
        )
        return func

    return decorator


def EventListener(
    event_type: str | type | None = None,
    *,
    condition: str | None = None,
    order: int = 0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    이벤트 리스너로 등록하는 데코레이터.

    Usage:
        @EventListener("user.created")
        async def on_user_created(self, event: UserCreatedEvent): ...

        @EventListener(UserCreatedEvent)
        async def on_user_created(self, event: UserCreatedEvent): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.set_metadata(
            "event_listener",
            {
                "event_type": event_type,
                "condition": condition,
            },
        )
        descriptor.order = order
        return func

    return decorator


def EventEmitter(
    event_type: str,
    *,
    condition: str | None = None,
    order: int = 100,  # 실행 후 이벤트 발행
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드 실행 후 이벤트를 발행하는 데코레이터.

    Usage:
        @EventEmitter("user.created")
        async def create_user(self, name: str) -> User: ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="event_emitter",
                order=order,
                metadata={
                    "event_type": event_type,
                    "condition": condition,
                },
            )
        )
        return func

    return decorator


def Cacheable(
    cache_name: str = "default",
    *,
    key: str | Callable[..., str] | None = None,
    ttl: int | None = None,
    condition: str | None = None,
    order: int = -50,  # 트랜잭션 다음으로 빨리
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    결과를 캐시하는 데코레이터.

    Usage:
        @Cacheable("users", key=lambda self, id: f"user:{id}", ttl=300)
        async def get_user(self, id: int) -> User: ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="cacheable",
                order=order,
                metadata={
                    "cache_name": cache_name,
                    "key": key,
                    "ttl": ttl,
                    "condition": condition,
                },
            )
        )
        return func

    return decorator


def CacheEvict(
    cache_name: str = "default",
    *,
    key: str | Callable[..., str] | None = None,
    all_entries: bool = False,
    before_invocation: bool = False,
    order: int = -50,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    캐시를 삭제하는 데코레이터.

    Usage:
        @CacheEvict("users", key=lambda self, id: f"user:{id}")
        async def delete_user(self, id: int): ...

        @CacheEvict("users", all_entries=True)
        async def clear_all_users(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="cache_evict",
                order=order,
                metadata={
                    "cache_name": cache_name,
                    "key": key,
                    "all_entries": all_entries,
                    "before_invocation": before_invocation,
                },
            )
        )
        return func

    return decorator


def Async(
    *,
    executor: str | None = None,
    order: int = 50,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드를 비동기로 실행하는 데코레이터.

    Usage:
        @Async()
        async def send_email(self, to: str, body: str): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="async",
                order=order,
                metadata={"executor": executor},
            )
        )
        return func

    return decorator


def Retry(
    max_attempts: int = 3,
    *,
    delay: float = 1.0,
    multiplier: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    order: int = -90,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    실패 시 재시도하는 데코레이터.

    Usage:
        @Retry(max_attempts=3, delay=1.0, exceptions=(ConnectionError,))
        async def call_external_api(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="retry",
                order=order,
                metadata={
                    "max_attempts": max_attempts,
                    "delay": delay,
                    "multiplier": multiplier,
                    "exceptions": exceptions,
                },
            )
        )
        return func

    return decorator


def RateLimited(
    limit: int,
    *,
    window: int = 60,  # seconds
    key: str | Callable[..., str] | None = None,
    order: int = -80,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    호출 횟수를 제한하는 데코레이터.

    Usage:
        @RateLimited(limit=100, window=60)  # 분당 100회
        async def api_endpoint(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="rate_limited",
                order=order,
                metadata={
                    "limit": limit,
                    "window": window,
                    "key": key,
                },
            )
        )
        return func

    return decorator


def Timed(
    *,
    metric_name: str | None = None,
    order: int = 200,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드 실행 시간을 측정하는 데코레이터.

    Usage:
        @Timed(metric_name="user_service.create_user")
        async def create_user(self): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="timed",
                order=order,
                metadata={"metric_name": metric_name},
            )
        )
        return func

    return decorator


def Logged(
    *,
    level: str = "INFO",
    include_args: bool = True,
    include_result: bool = False,
    order: int = 200,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    메서드 호출을 로깅하는 데코레이터.

    Usage:
        @Logged(level="DEBUG", include_args=True)
        async def process_data(self, data: dict): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        descriptor = ensure_method_descriptor(func)
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="logged",
                order=order,
                metadata={
                    "level": level,
                    "include_args": include_args,
                    "include_result": include_result,
                },
            )
        )
        return func

    return decorator
