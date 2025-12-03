"""CallableContainer 클래스 - Callable을 대상으로 하는 컨테이너의 베이스"""

import asyncio
from typing import Callable, Self, TYPE_CHECKING

if TYPE_CHECKING:
    from .component import ComponentContainer

from ..manager import try_get_current_manager
from .base import Container
from .element import (
    Scope,
    ScopeElement,
    SingletonOnlyElement,
    PriorityElement,
    PrototypeMode,
)


class CallableContainer[**P, R](Container[Callable[P, R]]):
    """
    Callable(함수/메서드)을 대상으로 하는 컨테이너의 베이스 클래스

    HandlerContainer, FactoryContainer 등의 상위 클래스로 사용됩니다.
    @Order 등 Callable에 적용되는 데코레이터가 기본으로 사용합니다.

    SINGLETON 스코프에서만 사용 가능한 핸들러는 SingletonOnlyElement를 추가합니다.
    """

    # 서브클래스에서 오버라이드할 priority (기본값 10)
    _default_priority: int = 10

    def __init__(self, callable_target: Callable[P, R]):
        self.callable_target = callable_target
        self.owner_cls: type | None = None  # scan 시 주입됨
        self._bound_method: Callable[P, R] | None = None
        self._is_coroutine: bool | None = None  # 캐싱된 코루틴 여부
        super().__init__(callable_target)  # type: ignore
        # PriorityElement 설정
        self._set_priority(self._default_priority)

    def _set_priority(self, priority: int) -> None:
        """PriorityElement 설정 (기존 제거 후 새로 추가)"""
        self.elements = [e for e in self.elements if not isinstance(e, PriorityElement)]
        self.add_element(PriorityElement(priority))

    def __repr__(self) -> str:
        name = getattr(self.callable_target, "__name__", str(self.callable_target))
        return f"{self.__class__.__name__}(target={name})"

    def _get_owner_type(self) -> type | None:
        """owner 타입 반환 (scan에서 주입됨)"""
        return self.owner_cls

    def _create_bound_method(
        self,
        target: Callable[P, R],
        wrapper: Callable[[Callable[P, R]], Callable[P, R]] | None = None,
    ) -> Callable[P, R]:
        """
        owner 인스턴스에 바인딩된 메서드 생성

        Args:
            target: 바인딩할 원본 함수/메서드
            wrapper: 적용할 wrapper 함수 (optional)

        Returns:
            바인딩된 메서드 (wrapper가 있으면 적용됨)
        """
        owner_type = self._get_owner_type()

        if owner_type is None:
            # owner가 없는 경우 (standalone 함수)
            if wrapper:
                return wrapper(target)
            return target
        else:
            # owner가 있는 경우 - 바인딩
            owner_instance = self._get_manager().get_instance(owner_type)
            if wrapper:
                wrapped = wrapper(target)
                return wrapped.__get__(owner_instance, owner_type)
            return target.__get__(owner_instance, owner_type)

    def _bind_method(self) -> Callable[P, R]:
        """owner 인스턴스에 바인딩된 메서드 반환 (캐싱)"""
        if self._bound_method is not None:
            return self._bound_method

        self._bound_method = self._create_bound_method(self.callable_target)
        return self._bound_method

    def initialize_instance(self) -> Self:
        """컨테이너 자체를 인스턴스로 반환"""
        return self

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Callable 호출 (비동기)"""
        bound_method = self._bind_method()

        # 코루틴 여부 캐싱 (최초 호출 시 한 번만 검사)
        if self._is_coroutine is None:
            self._is_coroutine = asyncio.iscoroutinefunction(bound_method)

        if self._is_coroutine:
            return await bound_method(*args, **kwargs)  # type: ignore
        else:
            return bound_method(*args, **kwargs)

    async def invoke(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Callable 호출 (별칭)"""
        return await self(*args, **kwargs)

    @classmethod
    def get_or_create(cls, method: Callable[P, R]) -> Self:
        """
        Callable에 컨테이너 생성

        더 구체적인 컨테이너(@Factory, @Handler)가 나중에 적용되면
        Element들이 자동으로 이전됩니다.
        """
        return cls._apply_override_rules(method, lambda: cls(method))

    def get_scope(self) -> Scope:
        """컨테이너의 스코프 반환 (기본값: SINGLETON)"""
        for elem in self.elements:
            if isinstance(elem, ScopeElement):
                return elem.scope
        return Scope.SINGLETON

    def get_prototype_mode(self) -> PrototypeMode:
        """컨테이너의 프로토타입 모드 반환 (기본값: DEFAULT)"""
        for elem in self.elements:
            if isinstance(elem, ScopeElement):
                return elem.prototype_mode
        return PrototypeMode.DEFAULT

    def is_singleton_only(self) -> bool:
        """SINGLETON 스코프에서만 사용 가능한 핸들러인지 확인"""
        return self.has_element(SingletonOnlyElement)

    def get_handler_type_name(self) -> str:
        """핸들러 타입명 반환 (에러 메시지용)"""
        elements = [e for e in self.elements if isinstance(e, SingletonOnlyElement)]
        if elements:
            return elements[0].handler_type
        return "Handler"

    def get_callable_name(self) -> str:
        """Callable의 이름 반환 (서브클래스에서 오버라이드 가능)"""
        if hasattr(self, "callable_target"):
            return getattr(self.callable_target, "__name__", str(self.callable_target))
        return str(self.target)

    def validate_owner_scope(self) -> None:
        """
        owner 컴포넌트의 스코프를 검증

        SingletonOnlyElement가 있는 핸들러가 CALL 또는 REQUEST 스코프
        컴포넌트에 정의되어 있으면 InvalidScopeError를 발생시킵니다.

        Raises:
            InvalidScopeError: 잘못된 스코프에서 핸들러가 사용된 경우
        """
        if not self.is_singleton_only():
            return

        owner_type = self.owner_cls
        if owner_type is None:
            return

        # owner의 ComponentContainer 조회
        from .component import ComponentContainer

        owner_container = ComponentContainer.get_container(owner_type)
        if owner_container is None:
            return

        # ScopeElement 확인
        scope_elements = [
            e for e in owner_container.elements if isinstance(e, ScopeElement)
        ]
        if not scope_elements:
            return  # 기본값 SINGLETON이므로 OK

        scope_element = scope_elements[0]
        scope = scope_element.scope

        # CALL 또는 REQUEST면 에러
        if scope in (Scope.CALL, Scope.REQUEST):
            from ..exceptions import InvalidScopeError

            handler_name = self.get_callable_name()
            raise InvalidScopeError(
                component_type=owner_type,
                handler_name=handler_name,
                handler_type=self.get_handler_type_name(),
                scope=scope.value,
            )
