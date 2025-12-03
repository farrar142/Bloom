"""Decorator Container - 메서드를 데코레이션하는 컨테이너"""

import asyncio
from typing import (
    Any,
    Awaitable,
    Callable,
    ParamSpec,
    TypeVar,
    Self,
    overload,
    TYPE_CHECKING,
)
from functools import wraps

if TYPE_CHECKING:
    from ..manager import ContainerManager

from .callable import CallableContainer


P = ParamSpec("P")
R = TypeVar("R")


class DecoratorContainer[**P, R](CallableContainer[P, R]):
    """
    원본 컨테이너나 함수를 데코레이션하는 컨테이너.

    DecoratorContainer는 원본 메서드를 wrapper 함수로 감쌉니다.
    다른 컨테이너와 흡수/전이될 때 데코레이션이 유지됩니다.

    @Handler 없이도 독립적으로 동작 가능:
        @Component
        class MyService:
            @decorator(my_wrapper)
            async def my_method(self):
                pass

    @Handler와 함께 사용:
        @Component
        class MyService:
            @decorator(my_wrapper)
            @Handler
            async def my_handler(self):
                pass

    DecoratorContainer가 상위 컨테이너(예: HandlerContainer)에 의해 오버라이드되면,
    Element들이 이전되면서 데코레이션 체인도 함께 유지됩니다.
    """

    def __init__(
        self,
        callable_target: Callable[P, R],
        wrapper: Callable[[Callable[P, R]], Callable[P, R]],
    ):
        """
        DecoratorContainer 초기화

        Args:
            callable_target: 데코레이션할 원본 함수/메서드
            wrapper: 원본을 완전히 래핑하는 함수
        """
        self._original_target = callable_target
        self._wrapper = wrapper
        # wrapper로 감싼 함수를 callable_target으로 저장
        super().__init__(wrapper(callable_target))
        self._decoration_chain: list["DecoratorContainer"] = [self]
        self._is_coroutine: bool | None = None
        self.manager: "ContainerManager | None" = None

    def _get_owner_type(self) -> type | None:
        """owner 타입 반환 (scan에서 주입됨)"""
        return self.owner_cls

    def _bind_method(self) -> Callable[P, R]:
        """owner 인스턴스에 바인딩된 메서드 반환"""
        owner_type = self._get_owner_type()
        if owner_type is None:
            # owner가 없는 경우 (standalone 함수)
            return self.callable_target
        else:
            # owner 인스턴스를 가져와서 원본을 바인딩 후 wrapper 적용
            owner_instance = self._get_manager().get_instance(owner_type)
            bound_method = self._original_target.__get__(owner_instance, owner_type)
            return self._wrapper(bound_method)

    def initialize_instance(self) -> Self:
        """DecoratorContainer 자체를 인스턴스로 반환 (HandlerContainer처럼)"""
        return self

    def add_decorator(self, decorator: "DecoratorContainer") -> None:
        """데코레이션 체인에 추가"""
        self._decoration_chain.append(decorator)
        self._decorated = None  # 캐시 무효화

    def get_decoration_chain(self) -> list["DecoratorContainer"]:
        """전체 데코레이션 체인 반환"""
        return list(self._decoration_chain)

    def _transfer_elements_to(self, target_container: "CallableContainer") -> None:
        """
        Element 이전 시 데코레이션 체인도 함께 이전

        DecoratorContainer의 핵심 기능:
        상위 컨테이너(예: HandlerContainer)로 오버라이드될 때,
        데코레이션 정보를 target_container에 전달합니다.
        """
        # 부모의 Element 이전 로직 호출
        super()._transfer_elements_to(target_container)

        # target이 DecoratorContainer면 데코레이션 체인 이전
        if isinstance(target_container, DecoratorContainer):
            for decorator in self._decoration_chain:
                if decorator not in target_container._decoration_chain:
                    target_container._decoration_chain.append(decorator)
            target_container._decorated = None  # 캐시 무효화
        else:
            # target이 DecoratorContainer가 아니면 Element로 데코레이션 정보 저장
            from .element import Element

            decoration_element = Element()
            decoration_element.metadata["decoration_chain"] = self._decoration_chain
            decoration_element.metadata["wrapper"] = self._wrapper
            target_container.add_element(decoration_element)

    @classmethod
    def get_or_create(
        cls,
        method: Callable[P, R],
        wrapper: Callable[[Callable[P, R]], Callable[P, R]],
    ) -> Self:
        """
        DecoratorContainer 생성 또는 기존 반환

        Args:
            method: 데코레이션할 함수/메서드
            wrapper: 원본을 완전히 래핑하는 함수
        """
        return cls._apply_override_rules(method, lambda: cls(method, wrapper))

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """데코레이션된 함수 호출 (owner 인스턴스 자동 바인딩)"""
        bound_method = self._bind_method()

        # 코루틴 여부 캐싱 (최초 호출 시 한 번만 검사)
        if self._is_coroutine is None:
            self._is_coroutine = asyncio.iscoroutinefunction(bound_method)

        if self._is_coroutine:
            return await bound_method(*args, **kwargs)  # type: ignore
        else:
            return bound_method(*args, **kwargs)

    async def invoke(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """핸들러 메서드 호출 (별칭)"""
        return await self(*args, **kwargs)

    def invoke_sync(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """동기 호출 (테스트용, owner 바인딩 없음)"""
        return self.callable_target(*args, **kwargs)


type ACallable[**P, R] = Callable[P, Awaitable[R]]

type Decorator[**P, R] = Callable[[Callable[P, R]], Callable[P, R]]
type ADecorator[**P, R] = Callable[[ACallable[P, R]], ACallable[P, Awaitable[R]]]


@overload
def decorator[**P, R](wrapper: Decorator[P, R]) -> Decorator[P, R]: ...
@overload
def decorator[**P, R](wrapper: ADecorator[P, R]) -> ADecorator[P, R]: ...


def decorator[**P, R](
    wrapper: Decorator[P, R] | ADecorator[P, R],
) -> Decorator[P, R] | ADecorator[P, R]:
    """
    DecoratorContainer를 생성하는 데코레이터 팩토리

    사용 예:
        def my_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                print("before")
                result = await fn(*args, **kwargs)
                print("after")
                return result
            return wrapped

        @decorator(my_wrapper)
        def my_func():
            pass
    """

    @overload
    def decorator_factory(func: Callable[P, R]) -> Callable[P, R]: ...
    @overload
    def decorator_factory(
        func: ACallable[P, R],
    ) -> ACallable[P, R]: ...
    def decorator_factory(
        func: Callable[P, R] | ACallable[P, R],
    ) -> Callable[P, R] | ACallable[P, R]:
        DecoratorContainer.get_or_create(func, wrapper)
        # 원본 함수 시그니처 유지하면서 컨테이너 연결
        return func

    return decorator_factory
