"""Component 데코레이터"""

from typing import Any, Callable, overload

from bloom.core.container import (
    ComponentContainer,
    Element,
    FactoryContainer,
    HandlerContainer,
)
from bloom.core.container.element import OrderElement, ScopeElement, Scope as ScopeEnum
from bloom.core.lifecycle import (
    LifecycleHandlerContainer,
    LifecycleType,
    LifecycleTypeElement,
)
from bloom.core.manager import try_get_current_manager


class ComponentElement[T](Element[T]):
    pass


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
                    manager.register_container(child_container)


def Component[T](cls: type[T]) -> type[T]:
    container = ComponentContainer.get_or_create(cls)
    # 클래스의 메서드에서 Factory/Handler 컨테이너 스캔
    _scan_child_containers(cls)
    return cls


def Factory[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """
    Factory 데코레이터: 메서드를 팩토리로 등록
    해당 메서드가 속한 클래스가 @Component로 등록되어 있어야 함
    """
    FactoryContainer.get_or_create(method)
    return method


def Handler[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """
    Handler 데코레이터: 메서드를 핸들러로 등록
    해당 메서드가 속한 클래스가 @Component로 등록되어 있어야 함

    사용 예시:
        @Component
        class MyController:
            @Handler
            def get_users(self) -> list[User]:
                return []

            @Handler
            def handle_error(self, error: ValueError) -> Response:
                return Response(400, str(error))
    """
    HandlerContainer.get_or_create(method)
    return method


def PostConstruct[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """
    PostConstruct 데코레이터: 인스턴스 생성 후 호출될 메서드를 지정

    의존성 주입이 완료된 후 초기화 로직을 실행합니다.
    비동기 메서드도 지원합니다.
    LifecycleHandlerContainer 기반으로 구현됩니다.

    사용 예시:
        @Component
        class DatabaseConnection:
            config: Config

            @PostConstruct
            def connect(self):
                self.connection = create_connection(self.config.db_url)
                print("Database connected")
    """
    container = LifecycleHandlerContainer.get_or_create(method)
    container.add_element(LifecycleTypeElement(LifecycleType.POST_CONSTRUCT))
    return method


def PreDestroy[**P, R](method: Callable[P, R]) -> Callable[P, R]:
    """
    PreDestroy 데코레이터: 애플리케이션 종료 시 호출될 메서드를 지정

    리소스 정리, 연결 해제 등의 정리 작업을 수행합니다.
    비동기 메서드도 지원합니다.
    LifecycleHandlerContainer 기반으로 구현됩니다.

    사용 예시:
        @Component
        class DatabaseConnection:
            @PreDestroy
            def disconnect(self):
                self.connection.close()
                print("Database disconnected")
    """
    container = LifecycleHandlerContainer.get_or_create(method)
    container.add_element(LifecycleTypeElement(LifecycleType.PRE_DESTROY))
    return method


def Order(order: int):
    """
    Order 데코레이터: Factory/Handler의 실행 순서 지정

    동일 타입을 반환하는 여러 Factory가 있을 때 (Factory Chain/Builder Chain),
    실행 순서를 명시적으로 지정합니다. 숫자가 낮을수록 먼저 실행됩니다.

    Order가 지정되지 않은 Factory는 의존성 그래프로 순서가 자동 결정됩니다.

    사용 예시 (Factory Chain):
        @Component
        class Config:
            @Factory
            def create(self) -> MyType:  # Order 없음 = 의존성 없으므로 먼저
                return MyType()

            @Factory
            @Order(1)
            def modify1(self, val: MyType) -> MyType:
                val.x += 1
                return val

            @Factory
            @Order(2)
            def modify2(self, val: MyType) -> MyType:  # 마지막 (최종값 저장)
                val.x += 2
                return val

    사용 예시 (Builder Chain):
        @Component
        class MyType:
            val = 0

        @Component
        class Config:
            @Factory
            @Order(1)
            def enhance1(self, val: MyType) -> MyType:
                val.val += 1
                return val

            @Factory
            @Order(2)
            def enhance2(self, val: MyType) -> MyType:  # 마지막 (최종값 저장)
                val.val += 2
                return val
    """

    def decorator[**P, R](method: Callable[P, R]) -> Callable[P, R]:
        from .container.callable import CallableContainer

        container = CallableContainer.get_or_create(method)
        container.add_element(OrderElement(order))
        return method

    return decorator


def Scope(scope: ScopeEnum):
    """
    Scope 데코레이터: 컴포넌트의 인스턴스 생명주기 범위 지정

    - SINGLETON (기본값): 애플리케이션 전체에서 단일 인스턴스
    - PROTOTYPE: 주입될 때마다 새 인스턴스 생성
    - REQUEST: HTTP 요청마다 새 인스턴스 (웹 컨텍스트에서만)

    사용 예시:
        from bloom.core.decorators import Scope
        from bloom.core.container.element import Scope as ScopeEnum

        @Component
        @Scope(ScopeEnum.PROTOTYPE)
        class RequestHandler:
            # 매번 새 인스턴스 생성
            pass

        @Component
        @Scope(ScopeEnum.SINGLETON)  # 기본값
        class DatabasePool:
            # 단일 인스턴스
            pass
    """

    def decorator[T](cls: type[T]) -> type[T]:
        container = ComponentContainer.get_or_create(cls)
        container.add_element(ScopeElement(scope))
        return cls

    return decorator
