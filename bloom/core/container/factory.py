"""
Factory Container 모듈 - Spring @Factory 스타일 구현

@Configuration 클래스 내의 @Factory 메서드들이 반환하는 인스턴스를
컨테이너에 등록합니다.

사용 예:
    @Configuration
    class AppConfig:
        db_service: DatabaseService  # 다른 서비스 의존성 주입

        @Factory
        def user_repository(self) -> UserRepository:
            '''UserRepository 빈 생성'''
            return UserRepository(self.db_service)

        @Factory
        async def user_service(self, user_repository: UserRepository) -> UserService:
            '''UserService 빈 생성 - 다른 빈을 파라미터로 주입받음'''
            service = UserService(user_repository)
            await service.initialize()
            return service

        @Factory(scope=Scope.CALL)
        def session(self, db: Database) -> Session:
            '''요청마다 새로운 세션 생성'''
            return db.session()
"""

from typing import Any, Callable, Self
from uuid import uuid4


from .base import Container
from .manager import get_container_registry, get_container_manager
from .scope import Scope


# =============================================================================
# Factory Container - @Factory 메서드를 위한 컨테이너
# =============================================================================


class FactoryContainer[**P, T, R](Container[Callable[P, R]]):
    """Factory 컨테이너 클래스

    @Factory로 데코레이팅된 메서드를 관리합니다.
    HandlerContainer와 유사한 구조로, 메서드에 component_id를 부여하고
    containers에 등록합니다.
    """

    return_type: type[R]
    param_dependencies: dict[str, type]  # Factory 메서드의 파라미터 의존성
    is_async: bool
    _cached_instance: R | None

    def __init__(
        self,
        func: Callable[P, R],
        component_id: str,
        return_type: type[R],
        param_dependencies: dict[str, type],
        is_async: bool,
    ) -> None:
        super().__init__(func, component_id)  # type: ignore
        self.func = func
        self.return_type = return_type
        self.param_dependencies = param_dependencies
        self.is_async = is_async
        self._cached_instance = None

    @property
    def scope(self) -> Scope:
        """element에서 scope 조회 (없으면 SINGLETON 기본값)"""
        try:
            return self.get_element("scope", Scope.SINGLETON)
        except KeyError:
            return Scope.SINGLETON

    async def initialize(self) -> Callable[P, R]:
        """Factory 메서드 초기화 - 원본 함수 반환"""
        return self.func

    @classmethod
    def register(
        cls,
        func: Callable[P, R],
        return_type: type[R],
        dependencies: dict[str, type],
        is_async: bool,
    ) -> "FactoryContainer[P, T, R]":
        """Factory 메서드를 FactoryContainer로 등록

        기존 Container가 있으면 elements를 흡수합니다.
        """
        from .base import Container

        if not hasattr(func, "__component_id__"):
            func.__component_id__ = str(uuid4())

        new_container = cls(
            func,
            func.__component_id__,
            return_type,
            dependencies,
            is_async,
        )
        return Container.transfer_or_absorb(func, new_container)  # type: ignore

    async def create_instance(self, config_instance: Any) -> R:
        """Factory 인스턴스 생성

        SINGLETON 스코프일 경우 캐시된 인스턴스를 반환합니다.
        """
        if self.scope == Scope.SINGLETON and self._cached_instance is not None:
            return self._cached_instance

        from .manager import get_container_manager

        manager = get_container_manager()

        # 의존성 해결
        kwargs: dict[str, Any] = {}
        for param_name, param_type in self.param_dependencies.items():
            # 다른 Factory에서 의존성 찾기
            dep_instance = await manager.registry.factory(param_type, required=False)
            if dep_instance is None:
                # 일반 컨테이너에서 찾기
                dep_instance = manager.registry.instance(
                    type=param_type, required=False
                )
            if dep_instance is None:
                raise RuntimeError(
                    f"Cannot resolve dependency '{param_name}: {param_type.__name__}' "
                    f"for @Factory method '{self.func.__name__}'"
                )
            kwargs[param_name] = dep_instance

        # Factory 메서드 호출
        method = getattr(config_instance, self.func.__name__)
        result = method(**kwargs)

        if self.is_async:
            result = await result

        # SINGLETON만 캐시에 저장
        if self.scope == Scope.SINGLETON:
            self._cached_instance = result

        return result

    def create_instance_sync(self, config_instance: Any) -> R:
        """Factory 인스턴스 생성 (sync)

        async가 아닌 Factory만 지원합니다.
        """
        if self.is_async:
            raise RuntimeError(
                f"Cannot call sync create for async Factory '{self.func.__name__}'"
            )

        if self.scope == Scope.SINGLETON and self._cached_instance is not None:
            return self._cached_instance

        from .manager import get_container_manager

        manager = get_container_manager()

        # 의존성 해결 (sync)
        kwargs: dict[str, Any] = {}
        for param_name, param_type in self.param_dependencies.items():
            # 캐시된 Factory에서 의존성 찾기
            dep_instance = None
            for config in manager.registry._configurations():
                dep_instance = config.get_cached_factory(param_type)
                if dep_instance is not None:
                    break

            if dep_instance is None:
                # 일반 컨테이너에서 찾기
                dep_instance = manager.registry.instance(
                    type=param_type, required=False
                )

            if dep_instance is None:
                raise RuntimeError(
                    f"Cannot resolve dependency '{param_name}: {param_type.__name__}' "
                    f"for @Factory method '{self.func.__name__}' in sync context"
                )
            kwargs[param_name] = dep_instance

        # Factory 메서드 호출
        method = getattr(config_instance, self.func.__name__)
        result = method(**kwargs)

        # SINGLETON만 캐시에 저장
        if self.scope == Scope.SINGLETON:
            self._cached_instance = result

        return result

    def get_cached_instance(self) -> R | None:
        """캐시된 인스턴스 반환"""
        return self._cached_instance

    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._cached_instance = None

    def __repr__(self) -> str:
        deps = ", ".join(
            f"{k}: {v.__name__}" for k, v in self.param_dependencies.items()
        )
        return f"FactoryContainer({self.func.__name__} -> {self.return_type.__name__}, deps=[{deps}], async={self.is_async})"


# =============================================================================
# Factory 데코레이터
# =============================================================================


# =============================================================================
# Configuration Container
# =============================================================================


class ConfigurationContainer[T](Container[T]):
    """Configuration 컨테이너 클래스

    @Configuration 클래스를 등록하고, 내부의 @Factory 메서드들을 관리합니다.
    """

    # 이 Configuration에 속한 FactoryContainer들
    _factory_containers: list[FactoryContainer]

    def __init__(self, kls: type[T], component_id: str) -> None:
        super().__init__(kls, component_id)
        self._factory_containers = []
        self._collect_factory_containers()

    def _collect_factory_containers(self) -> None:
        """Configuration 클래스의 @Factory 메서드들에 대한 FactoryContainer 수집"""
        registry = get_container_registry()
        manager = get_container_manager()

        for name in dir(self.kls):
            if name.startswith("_"):
                continue

            attr = getattr(self.kls, name, None)
            if attr is None or not callable(attr):
                continue

            # @Factory로 등록된 메서드인지 확인
            if not hasattr(attr, "__component_id__"):
                continue

            # FactoryContainer 찾기
            if attr in registry:
                component_id = attr.__component_id__
                factory_container = manager.registry.container(
                    container_type=FactoryContainer, id=component_id
                )
                self._factory_containers.append(factory_container)

    @classmethod
    def register[U: type](cls, kls: U) -> "ConfigurationContainer[U]":
        """Configuration 클래스를 ConfigurationContainer로 등록"""
        if not hasattr(kls, "__component_id__"):
            kls.__component_id__ = str(uuid4())

        registry = get_container_registry()

        if kls not in registry:
            registry[kls] = {}

        if kls.__component_id__ not in registry[kls]:
            registry[kls][kls.__component_id__] = ConfigurationContainer(
                kls, kls.__component_id__
            )
        container = registry[kls][kls.__component_id__]
        return container  # type: ignore

    async def initialize(self) -> T:
        """Configuration 인스턴스 초기화"""
        instance = self.kls()
        return instance

    def get_factory_containers(self) -> list[FactoryContainer]:
        """이 Configuration에 속한 모든 FactoryContainer 반환"""
        return self._factory_containers.copy()

    def get_factory_types(self) -> list[type]:
        """이 Configuration이 생성하는 모든 Factory 반환 타입"""
        return [fc.return_type for fc in self._factory_containers]

    def has_factory(self, factory_type: type) -> bool:
        """특정 타입의 Factory를 생성할 수 있는지 확인"""
        return any(fc.return_type == factory_type for fc in self._factory_containers)

    def get_factory_container_for_type(
        self, factory_type: type
    ) -> FactoryContainer | None:
        """특정 반환 타입에 대한 FactoryContainer 반환"""
        for fc in self._factory_containers:
            if fc.return_type == factory_type:
                return fc
        return None

    def get_factory_definition(self, factory_type: type) -> FactoryContainer | None:
        """특정 타입의 Factory 정의(FactoryContainer) 반환 - 하위 호환성"""
        return self.get_factory_container_for_type(factory_type)

    async def create_factory[R](self, factory_type: type[R]) -> R:
        """Factory 인스턴스 생성"""
        factory_container = self.get_factory_container_for_type(factory_type)
        if factory_container is None:
            raise ValueError(
                f"No @Factory method found for type '{factory_type.__name__}' "
                f"in {self.kls.__name__}"
            )

        from .manager import get_container_manager

        manager = get_container_manager()
        config_instance = manager.registry.instance(type=self.kls, required=False)

        if config_instance is None:
            raise RuntimeError(
                f"Configuration '{self.kls.__name__}' is not initialized"
            )

        return await factory_container.create_instance(config_instance)

    def get_cached_factory[R](self, factory_type: type[R]) -> R | None:
        """캐시된 인스턴스 반환"""
        factory_container = self.get_factory_container_for_type(factory_type)
        if factory_container is None:
            return None
        return factory_container.get_cached_instance()

    def clear_factories(self) -> None:
        """모든 캐시된 인스턴스 초기화"""
        for fc in self._factory_containers:
            fc.clear_cache()
