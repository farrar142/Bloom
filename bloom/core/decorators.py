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


class PostConstructElement[T](Element[T]):
    """@PostConstruct 메서드를 나타내는 Element"""

    def __init__(self):
        super().__init__()
        self.metadata["lifecycle"] = "post_construct"


class PreDestroyElement[T](Element[T]):
    """@PreDestroy 메서드를 나타내는 Element"""

    def __init__(self):
        super().__init__()
        self.metadata["lifecycle"] = "pre_destroy"


def _scan_child_containers(cls: type) -> None:
    """클래스의 메서드에서 Factory/Handler 컨테이너를 찾아 owner_cls 설정"""
    from .container.base import Container

    manager = try_get_current_manager()

    for attr_name in dir(cls):
        try:
            attr = getattr(cls, attr_name, None)
        except Exception:
            continue

        if child_container := Container.get_container(attr):
            # Factory 또는 Handler 컨테이너인 경우
            if isinstance(child_container, (FactoryContainer, HandlerContainer)):
                child_container.owner_cls = cls
                # manager가 있으면 등록
                if manager:
                    manager.register_container(
                        child_container, child_container.get_qual_name()
                    )


def Component[T](cls: type[T]) -> type[T]:
    container = ComponentContainer.get_or_create(cls)
    # 클래스의 메서드에서 Factory/Handler 컨테이너 스캔
    _scan_child_containers(cls)
    return cls


class QualifierElement[T](Element[T]):
    def __init__(self, name: str):
        super().__init__()
        self.metadata["qualifier"] = name


def Qualifier[T, **P, R](
    name: str,
) -> Callable[[type[T] | Callable[P, R]], type[T] | Callable[P, R]]:
    """
    Qualifier 데코레이터: 컴포넌트나 팩토리 메서드에 qualifier를 지정

    동일한 타입의 여러 인스턴스를 구분할 때 사용합니다.

    사용 예시 (클래스):
        @Component
        @Qualifier("mysql")
        class MySqlRepository(Repository):
            pass

    사용 예시 (Factory 메서드):
        @Component
        class StaticConfig:
            @Factory
            @Qualifier("public")
            def public_static(self) -> StaticFilesContainer:
                return StaticFilesContainer().add("/static", "public")

            @Factory
            @Qualifier("assets")
            def assets_static(self) -> StaticFilesContainer:
                return StaticFilesContainer().add("/assets", "assets")
    """

    def wrapper(target: type[T] | Callable[P, R]) -> type[T] | Callable[P, R]:
        if isinstance(target, type):
            # 클래스인 경우 - ComponentContainer 사용
            container = ComponentContainer.get_or_create(target)
            container.add_element(QualifierElement(name))
        else:
            # 메서드인 경우 - FactoryContainer 사용
            factory_container = FactoryContainer.get_or_create(target)
            factory_container.add_element(QualifierElement(name))
        return target

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


def PostConstruct[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """
    PostConstruct 데코레이터: 인스턴스 생성 후 호출될 메서드를 지정

    의존성 주입이 완료된 후 초기화 로직을 실행합니다.
    비동기 메서드도 지원합니다.
    HandlerContainer 기반으로 구현되어 __container__ 속성만 사용합니다.

    사용 예시:
        @Component
        class DatabaseConnection:
            config: Config

            @PostConstruct
            def connect(self):
                self.connection = create_connection(self.config.db_url)
                print("Database connected")
    """
    container = HandlerContainer.get_or_create(method, "__post_construct__")
    container.add_element(PostConstructElement())
    return method


def PreDestroy[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """
    PreDestroy 데코레이터: 애플리케이션 종료 시 호출될 메서드를 지정

    리소스 정리, 연결 해제 등의 정리 작업을 수행합니다.
    비동기 메서드도 지원합니다.
    HandlerContainer 기반으로 구현되어 __container__ 속성만 사용합니다.

    사용 예시:
        @Component
        class DatabaseConnection:
            @PreDestroy
            def disconnect(self):
                self.connection.close()
                print("Database disconnected")
    """
    container = HandlerContainer.get_or_create(method, "__pre_destroy__")
    container.add_element(PreDestroyElement())
    return method
