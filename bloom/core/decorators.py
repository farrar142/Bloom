"""Component 데코레이터"""

from typing import Any, Callable, overload

from bloom.core.container import (
    ComponentContainer,
    Element,
    FactoryContainer,
    HandlerContainer,
)
from bloom.core.manager import try_get_current_manager


class ComponentElement[T](Element[T]):
    pass


def _scan_child_containers(cls: type) -> None:
    """클래스의 메서드에서 Factory/Handler 컨테이너를 찾아 owner_cls 설정"""
    manager = try_get_current_manager()
    
    for attr_name in dir(cls):
        try:
            attr = getattr(cls, attr_name, None)
        except Exception:
            continue
            
        if attr and hasattr(attr, "__container__"):
            child_container = getattr(attr, "__container__")
            # Factory 또는 Handler 컨테이너인 경우
            if isinstance(child_container, (FactoryContainer, HandlerContainer)):
                child_container.owner_cls = cls
                # manager가 있으면 등록
                if manager:
                    manager.register_container(child_container, child_container.get_qual_name())


def Component[T](cls: type[T]) -> type[T]:
    container = ComponentContainer.get_or_create(cls)
    # 클래스의 메서드에서 Factory/Handler 컨테이너 스캔
    _scan_child_containers(cls)
    return cls


class QualifierElement[T](Element[T]):
    def __init__(self, name: str):
        super().__init__()
        self.metadata["qualifier"] = name


def Qualifier[T](name: str) -> Callable[[type[T]], type[T]]:
    def wrapper(cls: type[T]) -> type[T]:
        container = ComponentContainer.get_or_create(cls)
        container.add_element(QualifierElement(name))
        return cls

    return wrapper


def Factory[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """
    Factory 데코레이터: 메서드를 팩토리로 등록
    해당 메서드가 속한 클래스가 @Component로 등록되어 있어야 함
    """
    FactoryContainer.get_or_create(method)
    return method


def Handler[**P, R](key: Any) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Handler 데코레이터: 메서드를 핸들러로 등록
    해당 메서드가 속한 클래스가 @Component로 등록되어 있어야 함

    사용 예시:
        @Component
        class MyController:
            @Handler(("GET", "/users"))
            def get_users(self) -> list[User]:
                return []

            @Handler(ValueError)
            def handle_error(self, error: ValueError) -> Response:
                return Response(400, str(error))
    """

    def decorator(method: Callable[P, R]) -> Callable[P, R]:
        HandlerContainer.get_or_create(method, key)
        return method

    return decorator
