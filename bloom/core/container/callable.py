"""CallableContainer 클래스 - Callable을 대상으로 하는 컨테이너의 베이스"""

from typing import Callable, Self

from ..manager import try_get_current_manager
from .base import Container


class CallableContainer[**P, R](Container[Callable[P, R]]):
    """
    Callable(함수/메서드)을 대상으로 하는 컨테이너의 베이스 클래스

    HandlerContainer, FactoryContainer 등의 상위 클래스로 사용됩니다.
    @Order 등 Callable에 적용되는 데코레이터가 기본으로 사용합니다.
    """

    def __init__(self, callable_target: Callable[P, R]):
        self.callable_target = callable_target
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
