from contextvars import ContextVar
import inspect
from typing import TYPE_CHECKING, Callable, TypeGuard, overload

if TYPE_CHECKING:
    from .container import Container

containers = dict[type | Callable, dict[str, "Container"]]()


def is_container_registered[T](container_type: type[T]) -> TypeGuard[type[T]]:
    return container_type in containers


class ContainerManager:
    def __init__(self) -> None:
        self.containers = dict[type | Callable, list[object]]()

    async def initialize(self) -> None:
        """모든 컨테이너 초기화"""
        for container_type, container_list in containers.items():
            for container in container_list.values():
                print("Initializing container:", container.kls)
                instance = await container.initialize()
                self.containers.setdefault(container_type, []).append(instance)
                self._inject_fields_sync(container, instance)

    async def shutdown(self) -> None:
        """모든 컨테이너 종료"""
        for container_type, container_list in containers.items():
            for container in container_list.values():

                await container.shutdown()

    def get_containers[T](self, container_type: type[T]) -> dict[str, "Container[T]"]:
        """특정 타입의 컨테이너 조회"""
        if container_type not in containers:
            raise ValueError(f"No containers registered for type: {container_type}")
        return containers.get(container_type, {})  # type:ignore

    def get_container[T](
        self, container_type: type[T], component_id: str | None = None
    ) -> "Container[T]":
        """특정 타입과 컴포넌트 ID의 컨테이너 조회"""
        if container_type not in containers:
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
        if container_type not in self.containers:
            raise ValueError(f"No containers initialized for type: {container_type}")
        return self.containers.get(container_type, {})  # type:ignore

    @overload
    def get_instance[T](self, container_type: type[T]) -> T: ...

    @overload
    def get_instance[T](
        self, container_type: type[T], required: bool = False
    ) -> T | None: ...
    def get_instance[T](
        self, container_type: type[T], required: bool = True
    ) -> T | None:
        """특정 타입의 컨테이너 인스턴스 단일 조회"""
        instance = self.get_instances(container_type)
        if required and not instance:
            raise ValueError(f"No container instance found for type: {container_type}")
        return instance[0] if instance else None

    def _inject_fields_sync[T](self, container: "Container[T]", instance: T) -> None:
        """동기적으로 필드에 LazyProxy 주입"""
        from .proxy import LazyProxy

        for dep in container.dependencies:
            print("Processing dependency:", dep.field_name)
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
            print("Injecting LazyProxy for", dep.field_name)

            proxy_lp: LazyProxy[T] = LazyProxy(dep_container, self)
            setattr(instance, dep.field_name, proxy_lp)


container_manager_contexts: ContextVar[ContainerManager | None] = ContextVar(
    "current_container", default=None
)


def get_container_registry() -> dict[type | Callable, dict[str, "Container"]]:
    """현재 컨테이너 레지스트리 조회"""
    return containers


def get_container_manager() -> ContainerManager:
    """현재 컨테이너 매니저 조회"""
    manager = container_manager_contexts.get()
    if manager is None:
        manager = ContainerManager()
        container_manager_contexts.set(manager)
    return manager
