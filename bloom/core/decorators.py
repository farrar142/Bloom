import inspect
from typing import Callable, Concatenate

from bloom.utils.analyze_function import analyze_function
from .container import (
    Container,
    HandlerContainer,
    ConfigurationContainer,
    FactoryContainer,
)


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
    컨테이너에 싱글톤으로 등록됩니다.

    Args:
        func: Factory를 생성하는 메서드

    Returns:
        원본 메서드 (component_id가 부여됨)

    Example:
        @Configuration
        class AppConfig:
            @Factory
            def user_service(self) -> UserService:
                return UserService()

            @Factory
            async def async_service(self) -> AsyncService:
                service = AsyncService()
                await service.initialize()
                return service
    """
    deps = analyze_function(func)

    is_async = inspect.iscoroutinefunction(func)

    # FactoryContainer 등록
    FactoryContainer.register(func, deps.return_type, deps.dependencies, is_async)

    return func
