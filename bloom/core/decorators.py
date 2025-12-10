import inspect
from typing import Any, Callable, Concatenate, cast, overload

from bloom.utils.analyze_function import analyze_function
from .container import (
    Container,
    HandlerContainer,
    ConfigurationContainer,
    FactoryContainer,
)
from .container.base import ContainerTransferError
from .container.scope import Scope, transactional_scope
from .container.functions import Method, AsyncMethod, is_coroutine


# =============================================================================
# Scoped 데코레이터 - 클래스 및 함수에 스코프 지정
# =============================================================================

# Element key for scope
SCOPE_ELEMENT_KEY = "scope"


def Scoped[T](scope: Scope) -> Callable[[T], T]:
    """스코프 데코레이터: 클래스 또는 함수에 스코프를 지정합니다.

    다른 컨테이너 데코레이터(@Factory, @Component 등)와 순서에 상관없이 사용 가능합니다.
    - 다른 컨테이너가 먼저 적용된 경우: 해당 컨테이너의 element에 scope 추가
    - 다른 컨테이너가 나중에 적용되는 경우: 기본 Container 등록 후, 나중에 흡수/전이됨

    Usage:
        @Scoped(Scope.CALL)
        @Factory
        def session(self) -> Session:
            return Session()

        @Factory  # 순서 바뀌어도 동작
        @Scoped(Scope.CALL)
        def session(self) -> Session:
            return Session()

        @Scoped(Scope.REQUEST)
        @Component
        class RequestContext:
            pass

    Args:
        scope: 인스턴스 스코프 (SINGLETON, CALL, REQUEST)

    Returns:
        원본 클래스/함수 (scope가 Container element로 저장됨)
    """
    from .container.manager import get_container_registry

    def decorator(target: T) -> T:
        registry = get_container_registry()
        component_id = getattr(target, "__component_id__", None)
        key: Any = target

        # 이미 컨테이너가 등록되어 있는 경우 -> element에 scope 추가
        if key in registry and component_id and component_id in registry[key]:
            existing = registry[key][component_id]
            existing.add_element(SCOPE_ELEMENT_KEY, scope)
            return target

        # 컨테이너가 없는 경우 -> 기본 Container 등록
        container = Container.register(target)  # type: ignore
        container.add_element(SCOPE_ELEMENT_KEY, scope)
        return target

    return decorator


def Component[T: type](kls: T) -> T:
    """컴포넌트 데코레이터: 클래스를 특정 컨테이너 타입에 등록합니다."""
    container = Container.register(kls)
    return kls


def Service[T: type](kls: T) -> T:
    """서비스 데코레이터: 클래스를 싱글톤 컨테이너에 등록합니다."""
    container = Container.register(kls)
    return kls


def Handler[**P, T, R](
    func: Callable[Concatenate[T, P], R],
) -> Callable[Concatenate[T, P], R]:
    """핸들러 데코레이터: 함수를 특정 핸들러 컨테이너에 등록합니다."""
    handler = HandlerContainer.register(func)
    return func


def Configuration[T: type](kls: T) -> T:
    """Configuration 데코레이터: @Factory 메서드를 포함한 설정 클래스를 등록합니다.

    Spring의 @Configuration과 유사하게, 이 클래스 내의 @Factory 메서드들이
    반환하는 인스턴스가 컨테이너에 싱글톤으로 등록됩니다.

    사용법:
        @Configuration
        class AppConfig:
            db_service: DatabaseService  # 의존성 주입

            @Factory
            def user_repository(self) -> UserRepository:
                '''UserRepository 빈 생성'''
                return UserRepository(self.db_service)

            @Factory
            async def user_service(self, user_repo: UserRepository) -> UserService:
                '''UserService 빈 생성 - 다른 빈을 파라미터로 주입받음'''
                service = UserService(user_repo)
                await service.initialize()
                return service
    """
    container = ConfigurationContainer.register(kls)
    return kls


def Factory[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Factory 데코레이터: 메서드를 FactoryContainer에 등록합니다.

    @Configuration 클래스 내에서 사용되며, 메서드의 반환값이
    컨테이너에 등록됩니다.

    스코프를 지정하려면 @Scoped 데코레이터와 함께 사용하세요.

    Returns:
        원본 메서드 (component_id가 부여됨)

    Example:
        @Configuration
        class AppConfig:
            @Factory
            def user_service(self) -> UserService:
                return UserService()

            @Scoped(Scope.CALL)
            @Factory
            def session(self, db: Database) -> Session:
                return db.session()

            @Scoped(Scope.REQUEST)
            @Factory
            async def request_context(self) -> RequestContext:
                return RequestContext()
    """
    deps = analyze_function(func)
    is_async = inspect.iscoroutinefunction(func)

    # FactoryContainer 등록 - scope는 Lazy resolution으로 나중에 읽음
    container = FactoryContainer.register(
        func, deps.return_type, deps.dependencies, is_async
    )

    return func


def Transactional[**P, T, R](func: Method[P, T, R]) -> AsyncMethod[P, T, R]:
    """Transactional 데코레이터: 트랜잭션 스코프를 생성합니다.

    이 데코레이터가 적용된 메서드 내에서는 같은 스코프의 Factory 인스턴스가
    공유됩니다. 메서드 종료 시 모든 AutoCloseable 인스턴스가 자동으로 close됩니다.

    @Handler와 호환되며, Handler 내부에서 사용할 수 있습니다.

    Usage:
        @Component
        class MyService:
            session: Session  # ScopedProxy로 주입됨

            @Transactional
            def my_method(self):
                self.session.query(...)  # 세션 생성
                self.other_method()  # 같은 세션 공유
                # 메서드 종료 시 세션 자동 close

            @Transactional
            async def async_method(self):
                session = await self.async_session.resolve()
                # 같은 트랜잭션 내에서 session 공유
    """

    async def wrapper(self: T, *args: P.args, **kwargs: P.kwargs) -> R:
        async with transactional_scope():
            result = func(self, *args, **kwargs)
            if is_coroutine(result):
                return await result
            return result  # type: ignore

    # 원본 함수 정보 유지
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    wrapper.__module__ = func.__module__
    wrapper.__qualname__ = getattr(func, "__qualname__", func.__name__)
    wrapper.__annotations__ = getattr(func, "__annotations__", {})

    return wrapper  # type: ignore
