"""Controller 컨테이너 및 RequestMapping"""

from typing import Callable, TypeVar

from bloom.core.container import ComponentContainer, Element

T = TypeVar("T")


class RequestMappingElement[T](Element[T]):
    """RequestMapping 정보를 담는 Element"""

    def __init__(self, path: str = ""):
        super().__init__()
        self.metadata["request_mapping"] = path

    @property
    def path(self) -> str:
        return self.metadata.get("request_mapping", "")


class ControllerContainer[T](ComponentContainer[T]):
    """
    Controller 컴포넌트 컨테이너

    @Controller
    @RequestMapping("/api/users")
    class UserController:
        @Get("/{id}")
        def get_user(self, id: str) -> User:
            return User(id=id)

    RequestMapping의 prefix와 핸들러의 path가 결합됨
    """

    # Controller-specific helpers should use generic container metadata API.
    # RequestMapping values are stored as elements with metadata key "request_mapping".


def Controller[T](cls: type[T]) -> type[T]:
    """
    Controller 데코레이터

    @Component와 동일하지만 ControllerContainer를 사용

    사용법:
        @Controller
        class UserController:
            @Get("/users")
            def list_users(self) -> list[User]:
                return []
    """
    ControllerContainer.get_or_create(cls)
    return cls


def RequestMapping[T](path: str) -> Callable[[type[T]], type[T]]:
    """
    RequestMapping 데코레이터

    Controller의 기본 경로 prefix 설정

    사용법:
        @Controller
        @RequestMapping("/api/v1")
        class ApiController:
            @Get("/users")  # 실제 경로: /api/v1/users
            def list_users(self) -> list[User]:
                return []
    """

    def wrapper(cls: type[T]) -> type[T]:
        container = ControllerContainer.get_or_create(cls)
        container.add_element(RequestMappingElement(path))
        return cls

    return wrapper
