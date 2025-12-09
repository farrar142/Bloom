"""
Container Manager 모듈

컨테이너와 인스턴스를 관리하는 중앙 관리자입니다.
"""

from contextvars import ContextVar
import inspect
import types
from typing import TYPE_CHECKING, Any, Callable, TypeGuard, overload

if TYPE_CHECKING:
    from . import Container
    from .factory import ConfigurationContainer, FactoryContainer

type COMPONENT_ID = str

# 전역 컨테이너 레지스트리
# { 등록된_타입(클래스/함수): { component_id: Container } }
containers = dict[type | Callable, dict[COMPONENT_ID, "Container"]]()


def is_container_registered[T](container_type: type[T]) -> TypeGuard[type[T]]:
    """타입이 컨테이너로 등록되어 있는지 확인"""
    return container_type in containers


def get_container_registry() -> dict[type | Callable, dict[COMPONENT_ID, "Container"]]:
    """전역 컨테이너 레지스트리 조회"""
    return containers


class ContainerManager:
    """컨테이너 매니저

    모든 컨테이너와 인스턴스를 관리합니다.

    조회 메서드 요약:
    - container(): 컨테이너 조회 (타입, ID, 컨테이너클래스 기반)
    - instance(): 인스턴스 조회 (타입, ID 기반)
    - factory(): Factory 인스턴스 조회
    """

    def __init__(self) -> None:
        self._instances = dict[COMPONENT_ID, object]()
        self._factory_types_cache: set[type] | None = None

    @property
    def instances(self) -> dict[COMPONENT_ID, object]:
        """인스턴스 저장소"""
        return self._instances

    # =========================================================================
    # 초기화/종료
    # =========================================================================

    async def initialize(self) -> None:
        """모든 컨테이너 초기화"""
        # 1. 모든 컨테이너 초기화 및 일반 의존성 주입
        # 스냅샷 생성 (반복 중 dict 변경 방지)
        initial_containers = [(rt, dict(cd)) for rt, cd in containers.items()]
        for registered_type, container_dict in initial_containers:
            for container in container_dict.values():
                instance = await container.initialize()
                self._add_instance(container.component_id, instance)
                self._inject_dependencies(container, instance)

        # 2. Factory 인스턴스 미리 생성
        await self._initialize_factories()

        # 3. Factory 의존성 주입 (스냅샷 갱신)
        current_containers = [(rt, dict(cd)) for rt, cd in containers.items()]
        for registered_type, container_dict in current_containers:
            for container in container_dict.values():
                instance = self.instance(id=container.component_id, required=False)
                if instance is not None:
                    await self._inject_factory_dependencies(container, instance)

        # 4. Handler 메서드 바인딩 (스냅샷 사용)
        for registered_type, container_dict in current_containers:
            if inspect.isclass(registered_type):
                for container in container_dict.values():
                    await self._bind_handler_methods(container)

    async def shutdown(self) -> None:
        """모든 컨테이너 종료"""
        current_containers = [(rt, dict(cd)) for rt, cd in containers.items()]
        for registered_type, container_dict in current_containers:
            for container in container_dict.values():
                await container.shutdown()

    # =========================================================================
    # 컨테이너 조회 (통합 API)
    # =========================================================================

    @overload
    def container[T](
        self,
        *,
        type: type[T],
        id: COMPONENT_ID | None = None,
    ) -> "Container[T]":
        """등록된 타입으로 컨테이너 조회"""
        ...

    @overload
    def container[T: "Container"](
        self,
        *,
        container_type: type[T],
        id: COMPONENT_ID | None = None,
    ) -> T:
        """컨테이너 클래스 타입으로 조회"""
        ...

    @overload
    def container(
        self,
        *,
        id: COMPONENT_ID,
    ) -> "Container":
        """컴포넌트 ID로 컨테이너 조회"""
        ...

    def container[T](
        self,
        *,
        type: type[T] | None = None,
        container_type: "type[Container] | None" = None,
        id: COMPONENT_ID | None = None,
    ) -> "Container":
        """컨테이너 조회

        Args:
            type: 등록된 클래스/함수 타입
            container_type: Container 서브클래스 타입 (ConfigurationContainer 등)
            id: 컴포넌트 ID

        Returns:
            조회된 컨테이너

        Examples:
            # 등록된 타입으로 조회
            container = manager.container(type=MyService)

            # 컨테이너 클래스로 조회
            config = manager.container(container_type=ConfigurationContainer, id=some_id)

            # ID로만 조회
            container = manager.container(id=component_id)
        """
        # ID로만 조회
        if id is not None and type is None and container_type is None:
            for container_dict in containers.values():
                if id in container_dict:
                    return container_dict[id]
            raise ValueError(f"No container found for id: {id}")

        # 컨테이너 클래스 타입으로 조회
        if container_type is not None:
            matched = [
                c
                for container_dict in containers.values()
                for c in container_dict.values()
                if isinstance(c, container_type)
            ]
            if id is not None:
                for c in matched:
                    if c.component_id == id:
                        return c
                raise ValueError(f"No {container_type.__name__} found with id: {id}")
            if not matched:
                raise ValueError(f"No {container_type.__name__} found")
            return matched[0]

        # 등록된 타입으로 조회
        if type is not None:
            if type not in containers:
                raise ValueError(f"No container registered for type: {type}")
            container_dict = containers[type]
            if id is not None:
                if id not in container_dict:
                    raise ValueError(f"No container for {type} with id: {id}")
                return container_dict[id]
            if not container_dict:
                raise ValueError(f"No container found for type: {type}")
            return next(iter(container_dict.values()))

        raise ValueError("Must provide 'type', 'container_type', or 'id'")

    def containers[T: "Container"](
        self,
        container_type: type[T],
    ) -> list[T]:
        """특정 컨테이너 클래스의 모든 컨테이너 조회

        Args:
            container_type: Container 서브클래스 (ConfigurationContainer 등)

        Returns:
            해당 타입의 모든 컨테이너 리스트
        """
        return [
            c
            for container_dict in containers.values()
            for c in container_dict.values()
            if isinstance(c, container_type)
        ]

    # =========================================================================
    # 인스턴스 조회 (통합 API)
    # =========================================================================

    @overload
    def instance[T](self, *, type: type[T]) -> T:
        """타입으로 인스턴스 조회 (required)"""
        ...

    @overload
    def instance[T](self, *, type: type[T], required: bool) -> T | None:
        """타입으로 인스턴스 조회"""
        ...

    @overload
    def instance[T](self, *, id: COMPONENT_ID) -> T:
        """ID로 인스턴스 조회 (required)"""
        ...

    @overload
    def instance[T](self, *, id: COMPONENT_ID, required: bool) -> T | None:
        """ID로 인스턴스 조회"""
        ...

    def instance[T](
        self,
        *,
        type: type[T] | None = None,
        id: COMPONENT_ID | None = None,
        required: bool = True,
    ) -> T | None:
        """인스턴스 조회

        Args:
            type: 인스턴스 타입
            id: 컴포넌트 ID
            required: True면 없을 시 예외 발생

        Returns:
            조회된 인스턴스

        Examples:
            # 타입으로 조회
            service = manager.instance(type=MyService)

            # ID로 조회
            instance = manager.instance(id=component_id)

            # 옵셔널 조회
            maybe = manager.instance(type=MyService, required=False)
        """
        # ID로 조회
        if id is not None:
            if id in self._instances:
                return self._instances[id]  # type: ignore
            if required:
                raise ValueError(f"No instance found for id: {id}")
            return None

        # 타입으로 조회
        if type is not None:
            for inst in self._instances.values():
                if isinstance(inst, type):
                    return inst  # type: ignore
            if required:
                raise ValueError(f"No instance found for type: {type}")
            return None

        raise ValueError("Must provide 'type' or 'id'")

    def instances_of[T](self, type: type[T]) -> list[T]:
        """특정 타입의 모든 인스턴스 조회"""
        return [
            inst for inst in self._instances.values() if isinstance(inst, type)
        ]  # type: ignore

    # =========================================================================
    # Factory 조회
    # =========================================================================
    @overload
    async def factory[T](self, type: type[T]) -> T: ...
    @overload
    async def factory[T](self, type: type[T], *, required: bool) -> T | None: ...
    async def factory[T](self, type: type[T], *, required: bool = True) -> T | None:
        """Factory 인스턴스 조회

        Args:
            type: Factory 반환 타입
            required: True면 없을 시 예외 발생

        Returns:
            Factory 인스턴스
        """
        # 캐시된 인스턴스 찾기
        for config in self._configurations():
            cached = config.get_cached_factory(type)
            if cached is not None:
                return cached

        # Factory 정의가 있는 Configuration 찾기
        config = self.configuration_for(type)
        if config is None:
            if required:
                raise ValueError(f"No Factory found for type '{type.__name__}'")
            return None

        # Factory 인스턴스 생성
        return await config.create_factory(type)

    def factory_types(self) -> list[type]:
        """모든 Factory 반환 타입 조회"""
        result: list[type] = []
        for config in self._configurations():
            result.extend(config.get_factory_types())
        return result

    def configuration_for[T](
        self, factory_type: type[T]
    ) -> "ConfigurationContainer | None":
        """특정 타입의 Factory를 가진 Configuration 찾기"""
        for config in self._configurations():
            if config.has_factory(factory_type):
                return config
        return None

    # =========================================================================
    # Private 메서드
    # =========================================================================

    def _add_instance(self, component_id: COMPONENT_ID, instance: object) -> None:
        """인스턴스 저장"""
        self._instances[component_id] = instance

    def _configurations(self) -> list["ConfigurationContainer"]:
        """모든 ConfigurationContainer 조회"""
        from .factory import ConfigurationContainer

        return self.containers(ConfigurationContainer)

    def _is_factory_type(self, field_type: type) -> bool:
        """타입이 Factory로 등록되어 있는지 확인"""
        # 캐시 사용
        if self._factory_types_cache is None:
            self._factory_types_cache = set(self.factory_types())
        return field_type in self._factory_types_cache

    def _inject_dependencies[T](self, container: "Container[T]", instance: T) -> None:
        """일반 의존성 주입 (LazyProxy 사용)"""
        from .proxy import LazyProxy

        for dep in container.dependencies:
            if getattr(instance, dep.field_name, None) is not None:
                continue

            # Factory 타입은 나중에 처리
            if self._is_factory_type(dep.field_type):
                continue

            try:
                dep_container = self.container(type=dep.field_type)
            except ValueError:
                if dep.is_optional:
                    continue
                raise RuntimeError(
                    f"Cannot resolve dependency '{dep.field_name}' "
                    f"for '{container.kls.__name__}'"
                )

            setattr(instance, dep.field_name, LazyProxy(dep_container, self))

    async def _initialize_factories(self) -> None:
        """SINGLETON 스코프 Factory 인스턴스만 미리 생성

        CALL, REQUEST 등의 스코프는 사용 시점에 생성됨
        """
        from .factory import FactoryContainer
        from .scope import Scope

        for config in self._configurations():
            for factory_container in config.get_factory_containers():
                # SINGLETON 스코프만 미리 초기화
                if factory_container.scope == Scope.SINGLETON:
                    await self.factory(factory_container.return_type, required=False)

    async def _inject_factory_dependencies[T](
        self, container: "Container[T]", instance: T
    ) -> None:
        """Factory 타입 필드에 인스턴스 주입"""
        from .factory import FactoryContainer

        if isinstance(container, FactoryContainer):
            return

        for dep in container.dependencies:
            if not self._is_factory_type(dep.field_type):
                continue

            if getattr(instance, dep.field_name, None) is not None:
                continue

            factory_instance = await self.factory(dep.field_type, required=False)
            if factory_instance is None:
                if dep.is_optional:
                    continue
                raise RuntimeError(
                    f"Cannot resolve Factory dependency '{dep.field_name}' "
                    f"for '{container.kls.__name__}'"
                )

            setattr(instance, dep.field_name, factory_instance)

    async def _bind_handler_methods[T](self, container: "Container[T]") -> None:
        """Handler 메서드를 인스턴스에 바인딩"""
        from . import HandlerContainer

        for name in dir(container.kls):
            if name.startswith("_"):
                continue

            attr = getattr(container.kls, name, None)
            if attr is None or inspect.isclass(attr):
                continue

            # Handler 등록
            component_id = getattr(attr, "__component_id__", None)
            if not component_id:
                handler_container = HandlerContainer.register(attr)
                self._add_instance(
                    handler_container.component_id,
                    await handler_container.initialize(),
                )
                component_id = handler_container.component_id

            handler_instance = self.instance(id=component_id, required=False)
            if not handler_instance:
                continue

            # 바인딩
            handler_container = self.container(type=attr, id=component_id)
            parent_instance = self.instance(id=container.component_id)

            handler_container.parent_instance = parent_instance
            handler_container.parent_container = container

            bound_handler = types.MethodType(handler_instance, parent_instance)
            self._add_instance(component_id, bound_handler)
            setattr(parent_instance, name, bound_handler)


# =============================================================================
# 전역 함수
# =============================================================================

container_manager_contexts: ContextVar[ContainerManager | None] = ContextVar(
    "container_manager", default=None
)


def get_container_manager() -> ContainerManager:
    """현재 컨테이너 매니저 조회"""
    manager = container_manager_contexts.get()
    if manager is None:
        manager = ContainerManager()
        container_manager_contexts.set(manager)
    return manager
