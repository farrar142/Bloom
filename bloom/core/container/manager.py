from contextvars import ContextVar
import inspect
import types
from typing import TYPE_CHECKING, Any, Callable, TypeGuard, overload

if TYPE_CHECKING:
    from . import Container
    from .factory import ConfigurationContainer

type COMPONENT_ID = str

containers = dict[type | Callable, dict[COMPONENT_ID, "Container"]]()


def is_container_registered[T](container_type: type[T]) -> TypeGuard[type[T]]:
    return container_type in containers


class ContainerManager:
    def __init__(self) -> None:
        self.instances = dict[COMPONENT_ID, object]()
        self.containers = containers

    async def initialize(self) -> None:
        """모든 컨테이너 초기화"""
        for container_type, container_list in containers.items():
            for container in container_list.values():
                instance = await container.initialize()
                self.add_instance(container_type, container.component_id, instance)
                self._inject_fields_sync(container, instance)
        target_containers = [
            container
            for container_type, container_list in self.containers.items()
            if inspect.isclass(container_type)
            for container in container_list.values()
        ]
        for container in target_containers:
            await self.replace_handler_methods(container)

    async def replace_handler_methods[T](self, container: "Container[T]"):
        for name in dir(container.kls):
            if name.startswith("_"):
                continue
            attr = getattr(container.kls, name, None)
            if attr is None:
                continue
            if not inspect.isfunction(attr):
                continue
            if not (component_id := getattr(attr, "__component_id__", None)):
                from . import HandlerContainer

                handler_container = HandlerContainer.register(attr)
                self.add_instance(
                    attr,
                    handler_container.component_id,
                    await handler_container.initialize(),
                )
                component_id = handler_container.component_id
            if not (handler_instance := self.get_instance(component_id)):
                continue
            handler_container = self.get_container(attr, component_id)
            parent_instance = self.get_instance(container.component_id)
            handler_container.parent_instance = parent_instance
            handler_container.parent_container = container
            bound_handler = types.MethodType(
                handler_instance,  # type:ignore
                parent_instance,
            )
            self.add_instance(
                attr, component_id, bound_handler
            )  # 바운드된 메서드로 교체
            setattr(parent_instance, name, bound_handler)

    async def shutdown(self) -> None:
        """모든 컨테이너 종료"""
        for container_type, container_list in containers.items():
            for container in container_list.values():

                await container.shutdown()

    def add_instance[T](
        self,
        container_type: type[T] | Callable,
        component_id: COMPONENT_ID,
        instance: T,
    ) -> None:
        """컨테이너 인스턴스 수동 추가"""
        self.instances[component_id] = instance

    def get_containers_by_container_type[T: Container](
        self, container_type: "type[T]"
    ) -> list[T]:
        """특정 컨테이너 타입의 컨테이너 조회"""
        return [
            container
            for _, container_dict in self.containers.items()
            for container in container_dict.values()
            if isinstance(container, container_type)
        ]

    def get_container_by_container_type_and_id[T: Container](
        self, container_type: "type[T]", component_id: COMPONENT_ID
    ) -> T:
        containers = self.get_containers_by_container_type(container_type)
        for container in containers:
            if container.component_id == component_id:
                return container
        raise ValueError(
            f"No container found for type: {container_type} with id: {component_id}"
        )

    def get_container_type_by_id[T](
        self, component_id: COMPONENT_ID
    ) -> type["Container[T]"]:
        for _, container_dict in self.containers.items():
            for container in container_dict.values():
                if container.component_id == component_id:
                    return container.__class__
        raise ValueError(f"No container found for id: {component_id}")

    def get_containers[T](self, container_type: type[T]) -> dict[str, "Container[T]"]:
        """특정 타입의 컨테이너 조회"""
        if container_type not in containers:
            raise ValueError(f"No containers registered for type: {container_type}")
        return containers.get(container_type, {})  # type:ignore

    def get_container[T](
        self,
        container_type: type[T] | Callable,
        component_id: COMPONENT_ID | None = None,
    ) -> "Container[T]":
        """특정 타입과 컴포넌트 ID의 컨테이너 조회"""
        if container_type not in self.containers:
            raise ValueError(f"No containers registered for type: {container_type}")
        container_dict = containers.get(container_type, {})  # type:ignore
        if component_id is None:
            # 기본(첫 번째) 컨테이너 반환
            if not container_dict:
                raise ValueError(f"No container found for type: {container_type}")
            return next(iter(container_dict.values()))  # type:ignore
        if component_id not in container_dict:
            raise ValueError(
                f"No container found for type: {container_type} with id: {component_id}"
            )
        return container_dict[component_id]  # type:ignore

    def get_instances[T](self, container_type: type[T]) -> list[T]:
        """특정 타입의 컨테이너 인스턴스 조회"""
        result = list[T]()
        for componen_id, instance in self.instances.items():
            if isinstance(instance, container_type):
                result.append(instance)  # type: ignore
        return result

    @overload
    def get_instance[T](self, instance_type: type[T]) -> T: ...

    @overload
    def get_instance[T](
        self, instance_type: type[T], required: bool = False
    ) -> T | None: ...
    @overload
    def get_instance[T](self, instance_type: COMPONENT_ID) -> T: ...
    @overload
    def get_instance[T](
        self, instance_type: COMPONENT_ID, required: bool = False
    ) -> T | None: ...
    def get_instance[T](
        self, instance_type: type[T] | str, required: bool = True
    ) -> T | None:
        if isinstance(instance_type, str):
            for componen_id, instance in self.instances.items():
                if componen_id == instance_type:
                    return instance  # type: ignore
            else:
                if required:
                    raise ValueError(
                        f"No container instance found for id: {instance_type}"
                    )
                return None
        """특정 타입의 컨테이너 인스턴스 단일 조회"""
        instance = self.get_instances(instance_type)
        if required and not instance:
            raise ValueError(f"No container instance found for type: {instance_type}")
        return instance[0] if instance else None

    def _inject_fields_sync[T](self, container: "Container[T]", instance: T) -> None:
        """동기적으로 필드에 LazyProxy 주입"""
        from .proxy import LazyProxy

        for dep in container.dependencies:
            current_value = getattr(instance, dep.field_name, None)
            if current_value is not None:
                continue

            dep_container = self.get_container(dep.field_type)
            if dep_container is None:
                if dep.is_optional:
                    continue
                raise RuntimeError(
                    f"Cannot resolve dependency '{dep.field_name}' for '{container.kls.__name__}'"
                )

            proxy_lp: LazyProxy[T] = LazyProxy(dep_container, self)
            setattr(instance, dep.field_name, proxy_lp)

    # =========================================================================
    # Configuration/Factory 관련 메서드
    # =========================================================================

    def get_configurations(self) -> list["ConfigurationContainer"]:
        """모든 Configuration 컨테이너 조회"""
        from .factory import ConfigurationContainer

        return self.get_containers_by_container_type(ConfigurationContainer)

    def get_all_factory_types(self) -> list[type]:
        """모든 Configuration에서 정의된 Factory 반환 타입들 조회"""
        factory_types: list[type] = []
        for config in self.get_configurations():
            factory_types.extend(config.get_factory_types())
        return factory_types

    def find_configuration_for_factory[T](
        self, factory_type: type[T]
    ) -> "ConfigurationContainer | None":
        """특정 반환 타입을 생성할 수 있는 Configuration 찾기"""
        for config in self.get_configurations():
            if config.has_factory(factory_type):
                return config
        return None

    async def get_or_create_factory_instance[T](
        self, factory_type: type[T]
    ) -> T | None:
        """Factory 인스턴스 조회 또는 생성

        먼저 캐시된 인스턴스를 찾고, 없으면 생성합니다.

        Args:
            factory_type: 반환 타입

        Returns:
            Factory 인스턴스 또는 None (해당 타입의 Factory가 없는 경우)
        """
        # 먼저 캐시된 인스턴스 찾기
        for config in self.get_configurations():
            cached = config.get_cached_factory(factory_type)
            if cached is not None:
                return cached

        # Factory 정의가 있는 Configuration 찾기
        config = self.find_configuration_for_factory(factory_type)
        if config is None:
            return None

        # Factory 인스턴스 생성
        return await config.create_factory(factory_type)

    async def get_factory[T](self, factory_type: type[T]) -> T:
        """Factory 인스턴스 조회 (없으면 예외 발생)

        Args:
            factory_type: 반환 타입

        Returns:
            Factory 인스턴스

        Raises:
            ValueError: 해당 타입의 Factory가 없는 경우
        """
        instance = await self.get_or_create_factory_instance(factory_type)
        if instance is None:
            raise ValueError(f"No Factory found for type '{factory_type.__name__}'")
        return instance

    async def initialize_all_factories(self) -> None:
        """모든 Configuration의 Factory들을 초기화

        의존성 순서를 고려하여 모든 인스턴스를 생성합니다.
        """
        for factory_type in self.get_all_factory_types():
            await self.get_or_create_factory_instance(factory_type)

    # 하위 호환성을 위한 별칭
    get_factories = get_configurations
    get_or_create_factory = get_or_create_factory_instance


container_manager_contexts: ContextVar[ContainerManager | None] = ContextVar(
    "current_container", default=None
)


def get_container_registry() -> dict[type | Callable, dict[COMPONENT_ID, "Container"]]:
    """현재 컨테이너 레지스트리 조회"""
    return containers


def get_container_manager() -> ContainerManager:
    """현재 컨테이너 매니저 조회"""
    manager = container_manager_contexts.get()
    if manager is None:
        manager = ContainerManager()
        container_manager_contexts.set(manager)
    return manager
