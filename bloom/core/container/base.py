"""Container 베이스 클래스"""

from typing import Any, Self, Optional, cast, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from ..manager import ContainerManager

from ..manager import get_current_manager, try_get_current_manager
from .element import Element


class Container[T]:
    """
    @Component
    class MyService:
        pass
    에서 MyService 클래스에 대한 컨테이너 역할을 한다
    Container 인스턴스는 MyService.__container__ 속성으로 접근 가능하다
    initialize후에 인스턴스가 생성되고
    인스턴스에 필드 주입이 이루어진 후
    글로벌인스턴스레지스트리에 인스턴스가 저장된다
    """

    def __init__(self, target: type[T]):
        self.target = target
        self.elements = list[Element[T]]()
        self.owner_cls: type | None = None  # Factory/Handler의 부모 클래스
        self.manager: "ContainerManager | None" = None  # scan 시점에 주입됨

    def _get_manager(self) -> "ContainerManager":
        """manager 반환 (없으면 현재 활성 매니저 반환)"""
        if self.manager is not None:
            return self.manager
        return get_current_manager()

    def add_elements(self, *elements: Element[T]) -> None:
        self.elements.extend(elements)

    def __repr__(self) -> str:
        return f"Container(target={self.target.__name__}, elements={self.elements})"

    def get_dependencies(self) -> list[type]:
        """이 컨테이너가 의존하는 타입들을 반환"""
        dependencies = []
        for field_type in getattr(self.target, "__annotations__", {}).values():
            dependencies.append(field_type)
        return dependencies

    def _get_cached_instance(self) -> T | None:
        """캐시된 인스턴스가 있으면 반환"""
        return self._get_manager().get_instance(self.target, raise_exception=False)

    def _inject_dependencies(self, annotations: dict[str, type]) -> dict[str, Any]:
        """어노테이션 기반으로 의존성을 주입하여 kwargs 반환"""
        manager = self._get_manager()
        kwargs = {}
        for name, dep_type in annotations.items():
            if name == "return":
                continue
            if dep_container := manager.get_container(dep_type):
                kwargs[name] = dep_container.initialize_instance()
        return kwargs

    def _create_instance(self) -> T:
        """실제 인스턴스 생성 로직"""
        annotations = getattr(self.target, "__annotations__", {})
        kwargs = self._inject_dependencies(annotations)
        instance = self.target()
        instance.__dict__.update(kwargs)
        return instance

    def initialize_instance(self) -> T:
        """인스턴스 초기화 (캐시 확인 후 생성)"""
        if instance := self._get_cached_instance():
            return instance
        return self._create_instance()

    def get_qual_name(self) -> str:
        for element in self.elements:
            if qual_name := element.metadata.get("qualifier", None):
                return qual_name
        return "default"

    @classmethod
    def get_or_create(cls, kls: type[T]) -> Self:
        """
        컨테이너 어노테이션이 붙은 클래스에 컨테이너 생성
        
        현재 활성 manager가 있으면 자동으로 등록됨.
        없으면 나중에 scan() 시점에 등록됨.
        """
        if not (container := getattr(kls, "__container__", None)):
            container = cls(kls)
            setattr(kls, "__container__", container)
            # 현재 활성 manager가 있으면 자동 등록
            if manager := try_get_current_manager():
                manager.register_container(container, container.get_qual_name())
        return container

    def add_element(self, element: "Element[T]") -> None:
        """컨테이너에 엘리먼트 추가"""
        self.elements.append(element)

    def get_metadatas[U](self, key: str, default: Optional[U] = None) -> list[U]:
        """
        주어진 메타데이터 키에 해당하는 모든 값들을 리스트로 반환한다.

        - elements를 순회하며 element.metadata에 key가 있으면 그 값을 수집한다.
        - 수집된 값이 없다면 default가 제공되었을 경우 [default]를 반환하고,
          그렇지 않으면 빈 리스트를 반환한다.

        사용 예:
            container.get_metadatas("request_mapping") -> ["/api/v1"]
        """
        values: list[U] = []
        for element in self.elements:
            if key in element.metadata:
                val = element.metadata.get(key)
                values.append(cast(U, val))

        if not values and default is not None:
            return [default]

        return values

    @overload
    def get_metadata[U](
        self, key: str, default: Optional[U] = None, raise_exception: bool = True
    ) -> U: ...
    @overload
    def get_metadata[U](
        self, key: str, default: Optional[U] = None, raise_exception: bool = False
    ) -> U | None: ...

    def get_metadata[U](
        self, key: str, default: Optional[U] = None, raise_exception: bool = False
    ) -> U | None:
        """
        주어진 메타데이터 키에 해당하는 첫 번째 값을 반환한다.

        - elements를 순회하며 element.metadata에 key가 있으면 그 값을 반환한다.
        - 수집된 값이 없다면 default가 제공되었을 경우 default를 반환하고,
          그렇지 않으면 None을 반환한다.

        사용 예:
            container.get_metadata("request_mapping") -> "/api/v1"
        """
        for element in self.elements:
            if key in element.metadata:
                val = element.metadata.get(key)
                return cast(U, val)

        if default is not None:
            return default
        if raise_exception:
            raise KeyError(f"Metadata key '{key}' not found in container elements.")
        return None
