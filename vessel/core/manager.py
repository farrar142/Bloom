"""ContainerManager 클래스"""

from typing import Any, Literal, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from .container import Container


class ContainerManager:
    # app_name -> type -> qualifier -> Container
    global_container_registry = dict[str, dict[type, dict[str, "Container"]]]()
    # app_name -> type -> qualifier -> instance
    global_instance_registry = dict[str, dict[type, dict[str, Any]]]()
    app_name: str = ""

    @staticmethod
    def is_container(obj: Any) -> bool:
        """객체가 컨테이너를 가지고 있는지 확인"""
        return getattr(obj, "__container__", None) is not None

    @classmethod
    def register_container(
        cls, container: "Container", qualifier: str = "default"
    ) -> None:
        """현재 레지스트리에 컨테이너 등록"""
        if cls.app_name not in cls.global_container_registry:
            cls.global_container_registry[cls.app_name] = {}
        if container.target not in cls.global_container_registry[cls.app_name]:
            cls.global_container_registry[cls.app_name][container.target] = {}
        cls.global_container_registry[cls.app_name][container.target][
            qualifier
        ] = container

    @classmethod
    def scan_components(cls, module: object) -> None:
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if cls.is_container(attr):
                container = getattr(attr, "__container__")
                qualifier = container.get_qual_name()
                cls.register_container(container, qualifier)
            # Factory/Handler 메서드들도 스캔하고 owner_cls 주입
            if isinstance(attr, type):
                for method_name in dir(attr):
                    method = getattr(attr, method_name, None)
                    if method and cls.is_container(method):
                        child_container = getattr(method, "__container__")
                        child_container.owner_cls = attr  # owner 클래스 주입
                        qualifier = child_container.get_qual_name()
                        cls.register_container(child_container, qualifier)

    @classmethod
    def get_all_containers(cls) -> dict[type, dict[str, "Container"]]:
        return cls.global_container_registry.get(cls.app_name, {})

    @classmethod
    def get_container(cls, target: type, qualifier: str = "default") -> "Container":
        type_containers = cls.get_all_containers().get(target, {})
        if container := type_containers.get(qualifier, None):
            return container
        # qualifier가 없으면 첫 번째 컨테이너 반환
        if type_containers:
            return next(iter(type_containers.values()))
        raise Exception(
            f"Container for {target} with qualifier '{qualifier}' not found"
        )

    @classmethod
    def get_containers(cls, target: type) -> list["Container"]:
        containers = []
        for kls, qual_containers in cls.get_all_containers().items():
            if issubclass(kls, target):
                containers.extend(qual_containers.values())
        return containers

    @classmethod
    def set_instance[T](
        cls, target: type[T], instance: T, qualifier: str = "default"
    ) -> None:
        if cls.app_name not in cls.global_instance_registry:
            cls.global_instance_registry[cls.app_name] = {}
        if target not in cls.global_instance_registry[cls.app_name]:
            cls.global_instance_registry[cls.app_name][target] = {}
        cls.global_instance_registry[cls.app_name][target][qualifier] = instance

    @overload
    @classmethod
    def get_instance[T](
        cls, target: type[T], raise_exception: Literal[False], qualifier: str = ...
    ) -> T | None: ...
    @overload
    @classmethod
    def get_instance[T](
        cls, target: type[T], raise_exception: Literal[True] = ..., qualifier: str = ...
    ) -> T: ...
    @classmethod
    def get_instance[T](
        cls, target: type[T], raise_exception: bool = True, qualifier: str = "default"
    ) -> T | None:
        type_instances = cls.global_instance_registry.get(cls.app_name, {}).get(
            target, {}
        )
        print("initialize", target, qualifier)
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

    @classmethod
    def get_sub_instances[T](cls, target: type[T]) -> list[T]:
        instances = []
        for kls, qual_instances in cls.global_instance_registry.get(
            cls.app_name, {}
        ).items():
            if issubclass(kls, target):
                instances.extend(qual_instances.values())
        return instances

    @classmethod
    def get_all_instances(cls) -> dict[type, dict[str, Any]]:
        return cls.global_instance_registry.get(cls.app_name, {})
