"""bloom.core.decorators - 데코레이터 정의"""

from __future__ import annotations

import asyncio
import inspect
from functools import wraps
from typing import Any, Callable, TypeVar, overload, TYPE_CHECKING

from .scope import ScopeEnum
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
    scope: ScopeEnum = ScopeEnum.SINGLETON,
    name: str | None = None,
    primary: bool = False,
    lazy: bool = True,
) -> Callable[[T], T]:
    """@Component(...) - 옵션 지정"""
    ...


def Component[T: type](
    cls: T | None = None,
    *,
    scope: ScopeEnum = ScopeEnum.SINGLETON,
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

        @Component(scope=ScopeEnum.REQUEST)
        class RequestContext:
            pass

        # @Scope 데코레이터와 함께 사용 (순서 무관)
        @Component
        @Scope(ScopeEnum.CALL)
        class CallScopedService:
            pass

    Args:
        scope: 인스턴스 스코프 (SINGLETON, REQUEST, CALL)
        name: 빈 이름 (동일 타입 여러 빈 구분용)
        primary: 동일 타입 중 기본 빈 여부
        lazy: 지연 초기화 여부 (기본 True)
    """

    def decorator(cls: T) -> T:
        # 생성자 파라미터 검사 (self 제외) - 클래스 자체에 정의된 __init__만 확인
        init_method = cls.__dict__.get("__init__", None)
        if init_method is not None:
            sig = inspect.signature(init_method)
            params = [p for p in sig.parameters.values() if p.name != "self"]
            if params:
                param_names = [p.name for p in params]
                raise TypeError(
                    f"@Component는 생성자 의존성 주입을 지원하지 않습니다. "
                    f"'{cls.__name__}'에서 생성자 파라미터 {param_names}를 제거하고 "
                    f"필드 주입을 사용하세요. 예: `service: SomeService`"
                )

        # __bloom_scope__가 이미 설정되어 있으면 우선 사용 (@Scope 데코레이터)
        # 이를 통해 @Scope를 먼저 적용하든 나중에 적용하든 동작
        actual_scope = getattr(cls, "__bloom_scope__", None) or scope

        # 메타데이터 저장
        cls.__bloom_component__ = True  # type: ignore
        cls.__bloom_scope__ = actual_scope  # type: ignore
        cls.__bloom_name__ = name  # type: ignore
        cls.__bloom_primary__ = primary  # type: ignore
        cls.__bloom_lazy__ = lazy  # type: ignore

        # Container 생성 및 등록
        container: Container[T] = Container(
            target=cls,
            scope=actual_scope,
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


@overload
def Factory[F: Callable[..., Any]](method: F) -> F:
    """@Factory - 기본 SINGLETON"""
    ...


@overload
def Factory[F: Callable[..., Any]](
    *,
    scope: ScopeEnum = ScopeEnum.SINGLETON,
) -> Callable[[F], F]:
    """@Factory(scope=...) - 스코프 지정"""
    ...


def Factory[F: Callable[..., Any]](
    method: F | None = None,
    *,
    scope: ScopeEnum = ScopeEnum.SINGLETON,
) -> F | Callable[[F], F]:
    """
    팩토리 메서드 데코레이터.
    @Configuration 클래스 내부에서 사용.

    사용 예:
        @Configuration
        class AppConfig:
            @Factory
            def database_client(self) -> DatabaseClient:
                return DatabaseClient()

            @Factory(scope=ScopeEnum.CALL)
            def session(self) -> Session:
                return Session()
    """

    def decorator(m: F) -> F:
        m.__bloom_factory__ = True  # type: ignore
        m.__bloom_factory_scope__ = scope  # type: ignore
        return m

    if method is not None:
        # @Factory 형태 (인자 없이)
        return decorator(method)
    else:
        # @Factory(scope=...) 형태
        return decorator


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

        # Factory에서 지정한 scope 또는 기본 SINGLETON
        factory_scope = getattr(method, "__bloom_factory_scope__", ScopeEnum.SINGLETON)

        # Container 생성
        container: Container[Any] = Container(
            target=factory_info.return_type,
            scope=factory_scope,
            factory=factory_info,
        )

        manager.register(container)


# === @Handler ===


@overload
def Handler[F: Callable[..., Any]](func: F) -> F: ...


@overload
def Handler[F: Callable[..., Any]](*, propagate: bool = False) -> Callable[[F], F]: ...


def Handler[F: Callable[..., Any]](
    func: F | None = None, *, propagate: bool = False
) -> F | Callable[[F], F]:
    """
    핸들러 메서드 데코레이터.
    CALL 스코프 라이프사이클 관리.

    Args:
        propagate: True면 기존 CALL 스코프가 있을 경우 그대로 재사용.
                  트랜잭션 전파처럼 중첩 Handler에서 같은 세션/트랜잭션을
                  공유하고 싶을 때 사용.
                  False(기본값)면 항상 새 CALL 스코프 생성.

    사용 예:
        @Component
        class UserService:
            tx: AsyncProxy[TransactionContext]  # CALL 스코프 async factory

            @Handler
            async def create_user(self, name: str):
                session = await self.tx.resolve()  # 여기서 생성됨
                await self.internal_logic()  # 새 스코프에서 다른 세션

            @Handler(propagate=True)
            async def internal_logic(self):
                session = await self.tx.resolve()  # 부모 Handler와 같은 세션
                pass
    """

    def decorator(fn: F) -> F:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            manager = get_container_manager()
            scope_manager = manager.scope_manager

            # Call 스코프 시작 (propagate 옵션 적용)
            frame_id, is_owner = scope_manager.start_call(propagate=propagate)

            try:
                # 원본 함수 호출
                # CALL 스코프 의존성은 접근 시점에 생성됨:
                # - AsyncProxy: await resolve() 시점
                # - LazyProxy: 필드 접근 시점 (동기 factory만)
                result = fn(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            finally:
                # Call 스코프 종료 (정리)
                # is_owner=False면 정리하지 않음 (부모에서 정리)
                await scope_manager.end_call(frame_id, is_owner=is_owner)

        # 메타데이터 보존
        wrapper.__bloom_handler__ = True  # type: ignore
        wrapper.__bloom_handler_propagate__ = propagate  # type: ignore

        return wrapper  # type: ignore

    # @Handler 또는 @Handler()
    if func is not None:
        return decorator(func)
    return decorator


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
def Scope(scope: ScopeEnum) -> Callable[[type[T]], type[T]]:
    """@Scope(ScopeEnum.XXX) 형태"""
    ...


@overload
def Scope[T: type](cls: T) -> T:
    """직접 적용 불가 - 항상 인자 필요"""
    ...


def Scope(
    scope_or_cls: ScopeEnum | type | None = None,
) -> Callable[[type], type] | type:
    """
    스코프 지정 데코레이터.
    @Component와 함께 사용.

    사용 예:
        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestContext:
            pass
    """
    if isinstance(scope_or_cls, ScopeEnum):
        scope = scope_or_cls

        def decorator[T: type](cls: T) -> T:
            cls.__bloom_scope__ = scope  # type: ignore
            return cls

        return decorator
    else:
        raise TypeError(
            "@Scope requires a ScopeEnum argument: @Scope(ScopeEnum.REQUEST)"
        )


# Alias (하위 호환)
scope_decorator = Scope
ScopeDecorator = Scope


# === 편의 데코레이터 ===


def RequestScope[T: type](cls: T) -> T:
    """@RequestScope = @Component(scope=ScopeEnum.REQUEST)"""
    return Component(cls, scope=ScopeEnum.REQUEST)


def CallScope[T: type](cls: T) -> T:
    """@CallScope = @Component(scope=ScopeEnum.CALL)"""
    return Component(cls, scope=ScopeEnum.CALL)


def Singleton[T: type](cls: T) -> T:
    """@Singleton = @Component(scope=ScopeEnum.SINGLETON)"""
    return Component(cls, scope=ScopeEnum.SINGLETON)


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
