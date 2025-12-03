"""
MethodInterceptor 및 InterceptorChain 구현

Chain of Responsibility 패턴을 사용하여 인터셉터들을 순차적으로 실행.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Self
from collections.abc import Awaitable
import asyncio
import inspect


@dataclass
class MethodInvocation:
    """메서드 호출 정보를 담는 컨텍스트"""

    target: Any  # 실제 인스턴스
    method_name: str  # 메서드 이름
    args: tuple[Any, ...]  # 위치 인자
    kwargs: dict[str, Any]  # 키워드 인자
    method: Callable[..., Any]  # 실제 메서드

    # 메타데이터 (인터셉터들이 데이터를 공유할 때 사용)
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def signature(self) -> str:
        """메서드 시그니처 문자열"""
        return f"{type(self.target).__name__}.{self.method_name}"


@dataclass
class ProceedingJoinPoint:
    """
    Around 어드바이스에서 사용하는 proceed 포인트.
    proceed()를 호출하면 체인의 다음 인터셉터로 진행.
    """

    invocation: MethodInvocation
    _chain: "InterceptorChain"
    _index: int

    async def proceed(self) -> Any:
        """체인의 다음 인터셉터로 진행하거나, 실제 메서드 실행"""
        return await self._chain._proceed_from(self._index + 1, self.invocation)

    def get_args(self) -> tuple[Any, ...]:
        """호출 인자들 반환"""
        return self.invocation.args

    def get_kwargs(self) -> dict[str, Any]:
        """호출 키워드 인자들 반환"""
        return self.invocation.kwargs

    def set_args(self, args: tuple[Any, ...]) -> None:
        """호출 인자 수정 (파라미터 변환에 사용)"""
        self.invocation.args = args

    def set_kwargs(self, kwargs: dict[str, Any]) -> None:
        """호출 키워드 인자 수정"""
        self.invocation.kwargs = kwargs


class MethodInterceptor(ABC):
    """
    메서드 인터셉터 인터페이스.

    모든 인터셉터는 이 클래스를 상속하여 구현.
    order 속성으로 실행 순서를 제어.
    """

    order: int = 0  # 낮을수록 먼저 실행 (외부에서 감쌈)

    @abstractmethod
    async def intercept(
        self,
        invocation: MethodInvocation,
        proceed: Callable[[], Awaitable[Any]],
    ) -> Any:
        """
        메서드 호출을 인터셉트.

        Args:
            invocation: 메서드 호출 정보
            proceed: 다음 인터셉터 또는 실제 메서드를 호출하는 함수

        Returns:
            메서드 실행 결과 (또는 변환된 결과)
        """
        pass


class InterceptorChain:
    """
    인터셉터 체인 관리자.

    여러 인터셉터를 order 순으로 정렬하여 체인 실행.
    """

    def __init__(self, interceptors: list[MethodInterceptor] | None = None):
        self._interceptors: list[MethodInterceptor] = []
        if interceptors:
            for interceptor in interceptors:
                self.add(interceptor)

    def add(self, interceptor: MethodInterceptor) -> Self:
        """인터셉터 추가 (order 순으로 정렬 유지)"""
        self._interceptors.append(interceptor)
        self._interceptors.sort(key=lambda i: i.order)
        return self

    def remove(self, interceptor: MethodInterceptor) -> Self:
        """인터셉터 제거"""
        self._interceptors.remove(interceptor)
        return self

    def clear(self) -> Self:
        """모든 인터셉터 제거"""
        self._interceptors.clear()
        return self

    @property
    def interceptors(self) -> list[MethodInterceptor]:
        """등록된 인터셉터 목록 (복사본)"""
        return list(self._interceptors)

    async def invoke(self, invocation: MethodInvocation) -> Any:
        """체인 실행"""
        return await self._proceed_from(0, invocation)

    async def _proceed_from(self, index: int, invocation: MethodInvocation) -> Any:
        """특정 인덱스부터 체인 실행"""
        if index >= len(self._interceptors):
            # 모든 인터셉터를 통과했으면 실제 메서드 실행
            return await self._invoke_target(invocation)

        interceptor = self._interceptors[index]

        async def proceed() -> Any:
            return await self._proceed_from(index + 1, invocation)

        return await interceptor.intercept(invocation, proceed)

    async def _invoke_target(self, invocation: MethodInvocation) -> Any:
        """실제 타겟 메서드 실행"""
        method = invocation.method
        args = invocation.args

        # InjectableDecoratorFactory로 감싸진 메서드는 __bloom_original_method__를 가짐
        # 이 경우 원본 메서드를 호출해야 인터셉터에서 주입된 의존성이 제대로 동작함
        original = getattr(method, "__bloom_original_method__", None)
        if original is not None:
            # 원본 함수는 바운드 메서드가 아니므로 self를 첫 인자로 전달해야 함
            method = original
            # target(self)을 첫 번째 인자로 추가
            args = (invocation.target,) + args

        result = method(*args, **invocation.kwargs)

        # 코루틴이면 await
        if inspect.iscoroutine(result):
            result = await result

        return result


# ============================================================
# 기본 인터셉터 구현체들
# ============================================================


class BeforeInterceptor(MethodInterceptor):
    """메서드 실행 전에 동작하는 인터셉터"""

    def __init__(
        self,
        callback: Callable[[MethodInvocation], Awaitable[None] | None],
        order: int = 0,
    ):
        self._callback = callback
        self.order = order

    async def intercept(
        self,
        invocation: MethodInvocation,
        proceed: Callable[[], Awaitable[Any]],
    ) -> Any:
        result = self._callback(invocation)
        if inspect.iscoroutine(result):
            await result
        return await proceed()


class AfterInterceptor(MethodInterceptor):
    """메서드 실행 후에 동작하는 인터셉터 (예외 여부와 관계없이)"""

    def __init__(
        self,
        callback: Callable[
            [MethodInvocation, Any, Exception | None], Awaitable[None] | None
        ],
        order: int = 0,
    ):
        self._callback = callback
        self.order = order

    async def intercept(
        self,
        invocation: MethodInvocation,
        proceed: Callable[[], Awaitable[Any]],
    ) -> Any:
        exception: Exception | None = None
        result: Any = None

        try:
            result = await proceed()
            return result
        except Exception as e:
            exception = e
            raise
        finally:
            cb_result = self._callback(invocation, result, exception)
            if inspect.iscoroutine(cb_result):
                await cb_result


class AfterReturningInterceptor(MethodInterceptor):
    """메서드가 정상 반환될 때만 동작하는 인터셉터"""

    def __init__(
        self,
        callback: Callable[[MethodInvocation, Any], Awaitable[Any] | Any],
        order: int = 0,
    ):
        self._callback = callback
        self.order = order

    async def intercept(
        self,
        invocation: MethodInvocation,
        proceed: Callable[[], Awaitable[Any]],
    ) -> Any:
        result = await proceed()
        cb_result = self._callback(invocation, result)
        if inspect.iscoroutine(cb_result):
            return await cb_result
        return cb_result if cb_result is not None else result


class AfterThrowingInterceptor(MethodInterceptor):
    """메서드가 예외를 던질 때 동작하는 인터셉터"""

    def __init__(
        self,
        callback: Callable[[MethodInvocation, Exception], Awaitable[None] | None],
        exception_type: type[Exception] = Exception,
        order: int = 0,
    ):
        self._callback = callback
        self._exception_type = exception_type
        self.order = order

    async def intercept(
        self,
        invocation: MethodInvocation,
        proceed: Callable[[], Awaitable[Any]],
    ) -> Any:
        try:
            return await proceed()
        except Exception as e:
            if isinstance(e, self._exception_type):
                cb_result = self._callback(invocation, e)
                if inspect.iscoroutine(cb_result):
                    await cb_result
            raise


class AroundInterceptor(MethodInterceptor):
    """메서드 실행 전후를 모두 제어하는 인터셉터"""

    def __init__(
        self,
        callback: Callable[[ProceedingJoinPoint], Awaitable[Any]],
        order: int = 0,
    ):
        self._callback = callback
        self.order = order

    async def intercept(
        self,
        invocation: MethodInvocation,
        proceed: Callable[[], Awaitable[Any]],
    ) -> Any:
        # ProceedingJoinPoint를 만들어서 콜백에 전달
        # 여기서는 proceed 함수를 직접 감싸서 전달
        class SimpleProceedingJoinPoint(ProceedingJoinPoint):
            def __init__(
                self, inv: MethodInvocation, proceed_fn: Callable[[], Awaitable[Any]]
            ):
                self.invocation = inv
                self._proceed = proceed_fn

            async def proceed(self) -> Any:
                return await self._proceed()

            def get_args(self) -> tuple[Any, ...]:
                return self.invocation.args

            def get_kwargs(self) -> dict[str, Any]:
                return self.invocation.kwargs

            def set_args(self, args: tuple[Any, ...]) -> None:
                self.invocation.args = args

            def set_kwargs(self, kwargs: dict[str, Any]) -> None:
                self.invocation.kwargs = kwargs

        join_point = SimpleProceedingJoinPoint(invocation, proceed)
        return await self._callback(join_point)
