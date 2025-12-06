from contextvars import ContextVar
from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from .container import Container

containers = dict[type, list["Container"]]()


def is_container_registered[T](container_type: type[T]) -> TypeGuard[type[T]]:
    return container_type in containers


class ContainerManager:
    def __init__(self) -> None:
        self.containers = dict[type, list[object]]()

    async def initialize(self) -> None:
        """모든 컨테이너 초기화"""
        for container_type, container_list in containers.items():
            for container in container_list:
                instance = await container.initialize()
                self.containers.setdefault(container_type, []).append(instance)

    async def shutdown(self) -> None:
        """모든 컨테이너 종료"""
        for container_type, container_list in containers.items():
            for container in container_list:
                await container.shutdown()

    def get_instances[T](self, container_type: type[T]) -> list[T]:
        """특정 타입의 컨테이너 인스턴스 조회"""
        if container_type not in self.containers:
            raise ValueError(f"No containers initialized for type: {container_type}")
        return self.containers.get(container_type, [])  # type:ignore

    def get_instance[T](self, container_type: type[T]) -> T | None:
        """특정 타입의 컨테이너 인스턴스 단일 조회"""
        instance = self.get_instances(container_type)
        return instance[0] if instance else None


container_manager_contexts: ContextVar[ContainerManager | None] = ContextVar(
    "current_container", default=None
)


def get_container_registry() -> dict[type, list["Container"]]:
    """현재 컨테이너 레지스트리 조회"""
    return containers


def get_container_manager() -> ContainerManager:
    """현재 컨테이너 매니저 조회"""
    manager = container_manager_contexts.get()
    if manager is None:
        manager = ContainerManager()
        container_manager_contexts.set(manager)
    return manager
