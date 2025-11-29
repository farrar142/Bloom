"""ContainerManager 클래스"""

from contextvars import ContextVar
from typing import Any, Literal, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from .container import Container
    from .lifecycle import LifecycleManager


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


class AmbiguousInstanceError(Exception):
    """동일 타입의 인스턴스가 여러 개일 때 발생"""

    pass


class ContainerManager:
    """
    컨테이너와 인스턴스를 관리하는 매니저

    Application마다 독립적인 ContainerManager 인스턴스를 가짐

    레지스트리 구조:
    - container_registry: dict[type, list[Container]]
    - instance_registry: dict[type, list[T]]
    """

    def __init__(self, app_name: str):
        self.app_name = app_name
        # type -> list[Container]
        self.container_registry: dict[type, list["Container"]] = {}
        # type -> list[instance]
        self.instance_registry: dict[type, list[Any]] = {}
        # 라이프사이클 관리자 (lazy initialization)
        self._lifecycle: "LifecycleManager | None" = None

    def reset(self) -> None:
        """모든 레지스트리 초기화 (테스트 또는 재시작 용도)"""
        self.container_registry.clear()
        self.instance_registry.clear()
        self._lifecycle = None

    @property
    def lifecycle(self) -> "LifecycleManager":
        """라이프사이클 매니저 반환 (lazy initialization)"""
        if self._lifecycle is None:
            from .lifecycle import LifecycleManager

            self._lifecycle = LifecycleManager(self)
        return self._lifecycle

    def register_container(self, container: "Container") -> None:
        """컨테이너 등록"""
        if container.target not in self.container_registry:
            self.container_registry[container.target] = []
        # 중복 등록 방지
        if container not in self.container_registry[container.target]:
            self.container_registry[container.target].append(container)
        # Container에 manager 참조 주입
        container.manager = self

    def unregister_container(self, container: "Container") -> None:
        """컨테이너 등록 해제"""
        containers = self.container_registry.get(container.target, [])
        if container in containers:
            containers.remove(container)
            if not containers:
                del self.container_registry[container.target]

    def scan(self, module: object) -> None:
        """모듈에서 컴포넌트 스캔"""
        from .container.base import Container as BaseContainer

        # module 자체가 클래스일 때 (Controller 등) 클래스 자체도 등록
        if isinstance(module, type):
            if container := BaseContainer.get_container(module):
                self.register_container(container)

        for attr_name in dir(module):
            try:
                attr = getattr(module, attr_name)
            except Exception:
                continue  # Pydantic 등 일부 라이브러리에서 getattr 시 예외 발생 가능
            if container := BaseContainer.get_container(attr):
                self.register_container(container)
            # Factory/Handler 메서드들도 스캔하고 owner_cls 주입
            if isinstance(attr, type):
                for method_name in dir(attr):
                    try:
                        method = getattr(attr, method_name, None)
                        if method is None:
                            continue
                        child_container = BaseContainer.get_container(method)
                    except Exception:
                        continue
                    if child_container:
                        child_container.owner_cls = attr  # owner 클래스 주입
                        self.register_container(child_container)

    def get_all_containers(self) -> dict[type, list["Container"]]:
        """모든 컨테이너 반환"""
        return self.container_registry

    def get_container(self, target: type) -> "Container | None":
        """
        특정 타입의 컨테이너 반환

        - 1개: 반환
        - 0개: 서브클래스 중 1개면 반환, 아니면 None
        - 2개 이상: 첫 번째 반환 (Factory Chain 등에서 사용)
        """
        # forward reference (str) 체크
        if not isinstance(target, type):
            return None

        containers = self.container_registry.get(target, [])
        if containers:
            return containers[0]
        # 서브클래스 검색
        for kls, kls_containers in self.container_registry.items():
            try:
                if kls != target and issubclass(kls, target) and kls_containers:
                    return kls_containers[0]
            except TypeError:
                # issubclass에 유효하지 않은 타입이 들어온 경우
                continue
        return None

    def get_containers(
        self, target: type, include_subclasses: bool = True
    ) -> list["Container"]:
        """
        특정 타입의 컨테이너들 반환

        Args:
            target: 대상 타입
            include_subclasses: True면 서브클래스 컨테이너도 포함
        """
        if not include_subclasses:
            return self.container_registry.get(target, [])

        containers = []
        for kls, kls_containers in self.container_registry.items():
            if issubclass(kls, target):
                containers.extend(kls_containers)
        return containers

    def set_instance[T](self, target: type[T], instance: T) -> None:
        """인스턴스 저장"""
        if target not in self.instance_registry:
            self.instance_registry[target] = []
        # 중복 등록 방지
        if instance not in self.instance_registry[target]:
            self.instance_registry[target].append(instance)

    @overload
    def get_instance[T](
        self, target: type[T], raise_exception: Literal[False]
    ) -> T | None: ...
    @overload
    def get_instance[T](
        self,
        target: type[T],
        raise_exception: Literal[True] = ...,
    ) -> T: ...
    def get_instance[T](
        self, target: type[T], raise_exception: bool = True
    ) -> T | None:
        """
        정확한 타입의 인스턴스 1개 반환

        - 1개: 반환
        - 0개: 서브클래스 검색, 1개면 반환, 아니면 None/Exception
        - 2개 이상: AmbiguousInstanceError
        """
        instances = self.instance_registry.get(target, [])

        if len(instances) == 1:
            return instances[0]
        elif len(instances) > 1:
            raise AmbiguousInstanceError(
                f"Multiple instances of {target.__name__} found ({len(instances)}). "
                f"Use get_instances() to get all instances."
            )

        # 정확한 타입 없으면 서브클래스 검색
        sub_instances = self.get_instances(target, include_subclasses=True)
        if len(sub_instances) == 1:
            return sub_instances[0]
        elif len(sub_instances) > 1:
            raise AmbiguousInstanceError(
                f"Multiple subclass instances of {target.__name__} found ({len(sub_instances)}). "
                f"Use get_instances() to get all instances or specify exact type."
            )

        if raise_exception:
            raise Exception(f"Instance for {target.__name__} not found")
        return None

    def get_instances[T](
        self, target: type[T], include_subclasses: bool = True
    ) -> list[T]:
        """
        타입의 인스턴스들 반환

        Args:
            target: 대상 타입
            include_subclasses: True면 서브클래스 인스턴스도 포함
        """
        if not include_subclasses:
            return list(self.instance_registry.get(target, []))

        instances = []
        for kls, kls_instances in self.instance_registry.items():
            # kls가 클래스인 경우에만 issubclass 체크
            if isinstance(kls, type) and issubclass(kls, target):
                instances.extend(kls_instances)
        return instances

    # 하위 호환성을 위한 별칭
    def get_sub_instances[T](self, target: type[T]) -> list[T]:
        """특정 타입의 서브클래스 인스턴스들 반환 (get_instances의 별칭)"""
        return self.get_instances(target, include_subclasses=True)

    def get_all_instances(self) -> dict[type, list[Any]]:
        """모든 인스턴스 반환"""
        return self.instance_registry

    def clear(self) -> None:
        """레지스트리 초기화"""
        self.container_registry.clear()
        self.instance_registry.clear()
