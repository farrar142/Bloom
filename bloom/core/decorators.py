"""Component 데코레이터"""

from typing import Any, Callable, overload

from bloom.core.container import (
    ComponentContainer,
    Element,
    FactoryContainer,
    HandlerContainer,
)


class ComponentElement[T](Element[T]):
    pass


def Component[T](cls: type[T]) -> type[T]:
    ComponentContainer.get_or_create(cls)
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
