"""HandlerContainer 클래스"""

from typing import Callable, Self, get_type_hints, TYPE_CHECKING

if TYPE_CHECKING:
    from ..manager import ContainerManager

from .callable import CallableContainer


class HandlerContainer[**P, R](CallableContainer[P, R]):
    """
    메서드를 핸들러로 등록하는 컨테이너

    @Component
    class MyController:
        @Get("/users")
        def get_users(self) -> list[User]:
            return []

        @ExceptionHandler(ValueError)
        def handle_value_error(self, error: ValueError) -> Response:
            return Response(400, str(error))

    에서 get_users, handle_value_error 메서드에 대한 컨테이너 역할을 한다

    초기화 시: HandlerContainer 자체가 인스턴스로 저장됨
    호출 시: container(...) 또는 container.invoke(...) 로 실제 메서드 실행
    """

    _default_priority: int = 30

    def __init__(self, handler_method: Callable[P, R]):
        self._resolved_hints: dict | None = None
        self.manager: "ContainerManager | None" = None  # scan 시점에 주입됨
        super().__init__(handler_method)

    @property
    def handler_method(self) -> Callable[P, R]:
        """callable_target의 별칭 (하위 호환성)"""
        return self.callable_target

    def get_type_hints(self) -> dict:
        """타입 힌트를 resolve하여 캐시 (Annotated 포함)"""
        if self._resolved_hints is None:
            try:
                globalns = getattr(self.callable_target, "__globals__", {})
                self._resolved_hints = get_type_hints(
                    self.callable_target, globalns=globalns, include_extras=True
                )
            except Exception:
                self._resolved_hints = getattr(
                    self.callable_target, "__annotations__", {}
                )
        return self._resolved_hints  # type: ignore

    def get_dependencies(self) -> list[type]:
        """이 핸들러 컨테이너가 의존하는 타입들을 반환"""
        owner_type = self._get_owner_type()
        return [owner_type] if owner_type else []

    @classmethod
    def get_or_create(cls, handler_method: Callable[P, R]) -> Self:
        """핸들러 메서드에 대한 컨테이너 생성"""
        return cls._apply_override_rules(handler_method, lambda: cls(handler_method))
