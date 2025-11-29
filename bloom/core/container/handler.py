"""HandlerContainer 클래스"""

import asyncio
import inspect
from typing import Any, Callable, Self, get_type_hints, TYPE_CHECKING

if TYPE_CHECKING:
    from ..manager import ContainerManager

from ..manager import try_get_current_manager
from .base import Container


class HandlerContainer[**P, R](Container[Callable[P, R]]):
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

    def __init__(self, handler_method: Callable[P, R]):
        self.handler_method = handler_method
        self._bound_method: Callable[P, R] | None = None
        self._resolved_hints: dict | None = None
        self.owner_cls: type | None = None  # scan_components 후 주입됨
        self.manager: "ContainerManager | None" = None  # scan 시점에 주입됨
        self._is_coroutine: bool | None = None  # 캐싱된 코루틴 여부
        # target은 handler_method 자체
        super().__init__(handler_method)  # type: ignore

    def __repr__(self) -> str:
        return f"HandlerContainer(method={self.handler_method.__name__})"

    def get_type_hints(self) -> dict:
        """타입 힌트를 resolve하여 캐시 (Annotated 포함)"""
        if self._resolved_hints is None:
            try:
                globalns = getattr(self.handler_method, "__globals__", {})
                self._resolved_hints = get_type_hints(
                    self.handler_method, globalns=globalns, include_extras=True
                )
            except Exception:
                self._resolved_hints = getattr(
                    self.handler_method, "__annotations__", {}
                )
        return self._resolved_hints  # type: ignore

    def _get_owner_type(self) -> type | None:
        """owner 타입 반환 (scan_components에서 주입됨)"""
        return self.owner_cls

    def get_dependencies(self) -> list[type]:
        """이 핸들러 컨테이너가 의존하는 타입들을 반환"""
        owner_type = self._get_owner_type()
        return [owner_type] if owner_type else []

    def _bind_method(self) -> Callable[P, R]:
        """owner 인스턴스에 바인딩된 메서드 반환"""
        if self._bound_method is None:
            owner_type = self._get_owner_type()
            if owner_type is None:
                # owner가 없는 경우 (standalone 함수) 원래 함수 반환
                self._bound_method = self.handler_method
            else:
                owner_instance = self._get_manager().get_instance(owner_type)
                self._bound_method = self.handler_method.__get__(
                    owner_instance, owner_type
                )
        return self._bound_method  # type: ignore

    def initialize_instance(self) -> Self:
        """HandlerContainer 자체를 인스턴스로 반환"""
        return self

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """핸들러 메서드 호출 (비동기)

        핸들러가 동기 함수인 경우에도 async로 래핑하여 호출
        코루틴 여부를 캐싱하여 성능 최적화
        """
        bound_method = self._bind_method()

        # 코루틴 여부 캐싱 (최초 호출 시 한 번만 검사)
        if self._is_coroutine is None:
            self._is_coroutine = asyncio.iscoroutinefunction(bound_method)

        if self._is_coroutine:
            return await bound_method(*args, **kwargs)  # type: ignore
        else:
            # 동기 함수는 그대로 호출
            return bound_method(*args, **kwargs)

    async def invoke(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """핸들러 메서드 호출 (별칭)"""
        return await self(*args, **kwargs)

    @classmethod
    def get_or_create(
        cls,
        handler_method: Callable[P, R],
    ) -> Self:
        """핸들러 메서드에 대한 컨테이너 생성

        Container._apply_override_rules를 사용하여 오버라이드 규칙 적용
        """
        return cls._apply_override_rules(
            handler_method,
            lambda: cls(handler_method),
        )
