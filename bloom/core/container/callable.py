"""CallableContainer 클래스 - Callable을 대상으로 하는 컨테이너의 베이스"""

from typing import Callable, Self, TYPE_CHECKING

if TYPE_CHECKING:
    from .component import ComponentContainer

from ..manager import try_get_current_manager
from .base import Container
from .element import Scope, ScopeElement, SingletonOnlyElement


class CallableContainer[**P, R](Container[Callable[P, R]]):
    """
    Callable(함수/메서드)을 대상으로 하는 컨테이너의 베이스 클래스

    HandlerContainer, FactoryContainer 등의 상위 클래스로 사용됩니다.
    @Order 등 Callable에 적용되는 데코레이터가 기본으로 사용합니다.

    SINGLETON 스코프에서만 사용 가능한 핸들러는 SingletonOnlyElement를 추가합니다.
    """

    def __init__(self, callable_target: Callable[P, R]):
        self.callable_target = callable_target
        self.owner_cls: type | None = None  # scan 시 주입됨
        super().__init__(callable_target)  # type: ignore

    def __repr__(self) -> str:
        name = getattr(self.callable_target, "__name__", str(self.callable_target))
        return f"CallableContainer(target={name})"

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

    def get_prototype_mode(self) -> "PrototypeMode":
        """컨테이너의 프로토타입 모드 반환 (기본값: DEFAULT)"""
        from .element import PrototypeMode

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
