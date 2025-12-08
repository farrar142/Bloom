from contextvars import ContextVar
import inspect
import types
from typing import TYPE_CHECKING, Callable, TypeGuard, overload

if TYPE_CHECKING:
    from . import Container

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
        # 현재, 컨테이너에서 클래스의 인스턴스 업데이트
        target_containers = [
            container
            for container_type, container_list in self.containers.items()
            if inspect.isclass(container_type)
            for container in container_list.values()
        ]
        for container in target_containers:
            await self.replace_handler_methods(container)
        # TODO 인스턴스에서 핸들러들을 업데이트

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
