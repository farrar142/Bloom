"""ContainerManager 클래스"""

from contextvars import ContextVar
from typing import Any, Literal, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from .container import Container


# 현재 활성 매니저를 저장하는 ContextVar
_current_manager: ContextVar["ContainerManager | None"] = ContextVar(
    "current_manager", default=None
)


def get_current_manager() -> "ContainerManager":
    """현재 활성화된 ContainerManager 반환"""
    if manager := _current_manager.get():
        return manager
    raise RuntimeError(
        "No active ContainerManager. Ensure Application.scan() is called first."
    )


def try_get_current_manager() -> "ContainerManager | None":
    """현재 활성화된 ContainerManager 반환 (없으면 None)"""
    return _current_manager.get()


def set_current_manager(manager: "ContainerManager | None") -> None:
    """현재 ContainerManager 설정"""
    _current_manager.set(manager)


class ContainerManager:
    """
    컨테이너와 인스턴스를 관리하는 매니저

    Application마다 독립적인 ContainerManager 인스턴스를 가짐
    """

    def __init__(self, app_name: str):
        self.app_name = app_name
        # type -> qualifier -> Container
        self.container_registry: dict[type, dict[str, "Container"]] = {}
        # type -> qualifier -> instance
        self.instance_registry: dict[type, dict[str, Any]] = {}

    def register_container(
        self, container: "Container", qualifier: str = "default"
    ) -> None:
        """컨테이너 등록"""
        if container.target not in self.container_registry:
            self.container_registry[container.target] = {}
        self.container_registry[container.target][qualifier] = container
        # Container에 manager 참조 주입
        container.manager = self

    def scan_components(self, module: object) -> None:
        """모듈에서 컴포넌트 스캔"""
        from .container.base import Container as BaseContainer

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if container := BaseContainer.get_container(attr):
                qualifier = container.get_qual_name()
                self.register_container(container, qualifier)
            # Factory/Handler 메서드들도 스캔하고 owner_cls 주입
            if isinstance(attr, type):
                for method_name in dir(attr):
                    method = getattr(attr, method_name, None)
                    if method and (
                        child_container := BaseContainer.get_container(method)
                    ):
                        child_container.owner_cls = attr  # owner 클래스 주입
                        qualifier = child_container.get_qual_name()
                        self.register_container(child_container, qualifier)

    def get_all_containers(self) -> dict[type, dict[str, "Container"]]:
        """모든 컨테이너 반환"""
        return self.container_registry

    def get_container(
        self, target: type, qualifier: str = "default"
    ) -> "Container | None":
        """특정 타입의 컨테이너 반환"""
        type_containers = self.container_registry.get(target, {})
        if container := type_containers.get(qualifier, None):
            return container
        # qualifier가 없으면 첫 번째 컨테이너 반환
        if type_containers:
            return next(iter(type_containers.values()))
        return None

    def get_containers(self, target: type) -> list["Container"]:
        """특정 타입의 서브클래스 컨테이너들 반환"""
        containers = []
        for kls, qual_containers in self.container_registry.items():
            if issubclass(kls, target):
                containers.extend(qual_containers.values())
        return containers

    def set_instance[T](
        self, target: type[T], instance: T, qualifier: str = "default"
    ) -> None:
        """인스턴스 저장"""
        if target not in self.instance_registry:
            self.instance_registry[target] = {}
        self.instance_registry[target][qualifier] = instance

    @overload
    def get_instance[T](
        self, target: type[T], raise_exception: Literal[False], qualifier: str = ...
    ) -> T | None: ...
    @overload
    def get_instance[T](
        self,
        target: type[T],
        raise_exception: Literal[True] = ...,
        qualifier: str = ...,
    ) -> T: ...
    def get_instance[T](
        self, target: type[T], raise_exception: bool = True, qualifier: str = "default"
    ) -> T | None:
        """인스턴스 조회"""
        type_instances = self.instance_registry.get(target, {})
        if instance := type_instances.get(qualifier, None):
            return instance
        # qualifier가 없으면 첫 번째 인스턴스 반환
        if type_instances:
            return next(iter(type_instances.values()))
        if raise_exception:
            raise Exception(
                f"Instance for {target} with qualifier '{qualifier}' not found"
            )
        return None

    def get_sub_instances[T](self, target: type[T]) -> list[T]:
        """특정 타입의 서브클래스 인스턴스들 반환"""
        instances = []
        for kls, qual_instances in self.instance_registry.items():
            if issubclass(kls, target):
                instances.extend(qual_instances.values())
        return instances

    def get_all_instances(self) -> dict[type, dict[str, Any]]:
        """모든 인스턴스 반환"""
        return self.instance_registry

    def clear(self) -> None:
        """레지스트리 초기화"""
        self.container_registry.clear()
        self.instance_registry.clear()
