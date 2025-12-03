"""bloom.core.decorators - 데코레이터 정의"""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Callable, TypeVar, overload, TYPE_CHECKING

from .scope import Scope
from .container import Container, analyze_factory_method
from .manager import get_container_manager

if TYPE_CHECKING:
    from .manager import ContainerManager


T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


# === @Component ===


@overload
def Component[T: type](cls: T) -> T:
    """@Component - 기본 SINGLETON"""
    ...


@overload
def Component[T: type](
    *,
    scope: Scope = Scope.SINGLETON,
    name: str | None = None,
    primary: bool = False,
    lazy: bool = True,
) -> Callable[[T], T]:
    """@Component(...) - 옵션 지정"""
    ...


def Component[T: type](
    cls: T | None = None,
    *,
    scope: Scope = Scope.SINGLETON,
    name: str | None = None,
    primary: bool = False,
    lazy: bool = True,
) -> T | Callable[[T], T]:
    """
    클래스를 DI 컨테이너에 등록하는 데코레이터.

    사용 예:
        @Component
        class UserService:
            pass

        @Component(scope=Scope.REQUEST)
        class RequestContext:
            pass

    Args:
        scope: 인스턴스 스코프 (SINGLETON, REQUEST, CALL)
        name: 빈 이름 (동일 타입 여러 빈 구분용)
        primary: 동일 타입 중 기본 빈 여부
        lazy: 지연 초기화 여부 (기본 True)
    """

    def decorator(cls: T) -> T:
        # 메타데이터 저장
        cls.__bloom_component__ = True  # type: ignore
        cls.__bloom_scope__ = scope  # type: ignore
        cls.__bloom_name__ = name  # type: ignore
        cls.__bloom_primary__ = primary  # type: ignore
        cls.__bloom_lazy__ = lazy  # type: ignore

        # Container 생성 및 등록
        container: Container[T] = Container(
            target=cls,
            scope=scope,
            name=name,
            primary=primary,
            lazy=lazy,
        )

        manager = get_container_manager()
        manager.register(container)

        return cls

    # @Component vs @Component()
    if cls is not None:
        return decorator(cls)
    return decorator


# === Alias Decorators ===


def Service[T: type](cls: T) -> T:
    """@Service = @Component (비즈니스 로직용)"""
    return Component(cls)


def Repository[T: type](cls: T) -> T:
    """@Repository = @Component (데이터 접근용)"""
    return Component(cls)


def Configuration[T: type](cls: T) -> T:
    """
    @Configuration - @Factory 메서드를 포함하는 설정 클래스.
    자동으로 @Component로 등록됨.
    """
    cls.__bloom_configuration__ = True  # type: ignore
    return Component(cls)


# === @Factory ===


def Factory[F: Callable[..., Any]](method: F) -> F:
    """
    팩토리 메서드 데코레이터.
    @Configuration 클래스 내부에서 사용.

    사용 예:
        @Configuration
        class AppConfig:
            @Factory
            def database_client(self) -> DatabaseClient:
                return DatabaseClient()
    """
    method.__bloom_factory__ = True  # type: ignore
    return method


def register_factories_from_configuration[T](
    config_cls: type[T],
    manager: "ContainerManager | None" = None,
) -> None:
    """
    @Configuration 클래스에서 @Factory 메서드들을 찾아 등록.
    Application.scan()에서 호출됨.
    """
    if manager is None:
        manager = get_container_manager()

    for name in dir(config_cls):
        if name.startswith("_"):
            continue

        method = getattr(config_cls, name, None)
        if method is None or not callable(method):
            continue

        if not getattr(method, "__bloom_factory__", False):
            continue

        # Factory 메서드 분석
        factory_info = analyze_factory_method(method, config_cls)

        # Container 생성
        container: Container[Any] = Container(
            target=factory_info.return_type,
            scope=Scope.SINGLETON,  # Factory는 기본 SINGLETON
            factory=factory_info,
        )

        manager.register(container)


# === @Handler ===


def Handler[F: Callable[..., Any]](func: F) -> F:
    """
    핸들러 메서드 데코레이터.
    CALL 스코프 라이프사이클 관리 및 콜스택 추적.

    사용 예:
        @Component
        class UserService:
            tx: TransactionContext  # CALL 스코프

            @Handler
            async def create_user(self, name: str):
                # tx는 이 호출 내에서만 유효
                pass
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        manager = get_container_manager()
        scope_manager = manager.scope_manager

        # Call 스코프 시작
        frame_id = scope_manager.start_call()

        try:
            # 원본 함수 호출
            result = func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            return result
        finally:
            # Call 스코프 종료 (정리)
            await scope_manager.end_call(frame_id)

    # 메타데이터 보존
    wrapper.__bloom_handler__ = True  # type: ignore

    return wrapper  # type: ignore


# === @Value ===


class Value:
    """
    설정값 주입 마커.

    사용 예:
        @Component
        class UserService:
            @Value("app.name")
            app_name: str

            @Value("app.debug", default=False)
            debug: bool
    """

    def __init__(self, key: str, *, default: Any = None) -> None:
        self.key = key
        self.default = default

    def __repr__(self) -> str:
        return f"Value({self.key!r})"


# === @Scope ===


@overload
def scope_decorator(scope: Scope) -> Callable[[type[T]], type[T]]:
    """@Scope(Scope.XXX) 형태"""
    ...


@overload
def scope_decorator[T: type](cls: T) -> T:
    """직접 적용 불가 - 항상 인자 필요"""
    ...


def scope_decorator(
    scope_or_cls: Scope | type | None = None,
) -> Callable[[type], type] | type:
    """
    스코프 지정 데코레이터.
    @Component와 함께 사용.

    사용 예:
        @Component
        @Scope(Scope.REQUEST)
        class RequestContext:
            pass
    """
    if isinstance(scope_or_cls, Scope):
        scope = scope_or_cls

        def decorator[T: type](cls: T) -> T:
            cls.__bloom_scope__ = scope  # type: ignore
            return cls

        return decorator
    else:
        raise TypeError("@Scope requires a Scope argument: @Scope(Scope.REQUEST)")


# Alias
ScopeDecorator = scope_decorator


# === 편의 데코레이터 ===


def RequestScope[T: type](cls: T) -> T:
    """@RequestScope = @Component(scope=Scope.REQUEST)"""
    return Component(cls, scope=Scope.REQUEST)


def CallScope[T: type](cls: T) -> T:
    """@CallScope = @Component(scope=Scope.CALL)"""
    return Component(cls, scope=Scope.CALL)


def Singleton[T: type](cls: T) -> T:
    """@Singleton = @Component(scope=Scope.SINGLETON)"""
    return Component(cls, scope=Scope.SINGLETON)


# === @Primary ===


def Primary[T: type](cls: T) -> T:
    """
    동일 타입의 여러 빈 중 기본 빈으로 지정.

    사용 예:
        @Component
        @Primary
        class DefaultUserRepository(UserRepository):
            pass
    """
    cls.__bloom_primary__ = True  # type: ignore
    return cls


# === @Lazy ===


def Lazy[T: type](cls: T) -> T:
    """
    지연 초기화 명시적 지정.
    (기본적으로 모든 필드 주입은 Lazy)

    사용 예:
        @Component
        @Lazy
        class HeavyService:
            pass
    """
    cls.__bloom_lazy__ = True  # type: ignore
    return cls


# === @Order ===


def Order(value: int) -> Callable[[type[T]], type[T]]:
    """
    초기화 순서 지정 (낮을수록 먼저).

    사용 예:
        @Component
        @Order(1)
        class FirstService:
            pass

        @Component
        @Order(2)
        class SecondService:
            first: FirstService
    """

    def decorator[T: type](cls: T) -> T:
        cls.__bloom_order__ = value  # type: ignore
        return cls

    return decorator
