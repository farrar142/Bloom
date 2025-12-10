from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
)
from uuid import uuid4
from .manager import get_container_manager, get_container_registry

if TYPE_CHECKING:
    from .scope import Scope


class Element[T]:
    key: str
    value: T

    def __init__(self, key: str, value: T) -> None:
        self.key = key
        self.value = value


@dataclass
class DependencyInfo:
    """의존성 정보"""

    field_name: str  # 필드명
    field_type: type  # 타입 (AsyncProxy[T]인 경우 T)
    is_optional: bool = False  # Optional 여부
    default_value: Any = None  # 기본값
    is_async_proxy: bool = False  # AsyncProxy[T]로 선언되었는지 여부
    raw_type_hint: Any = None  # 원본 타입 힌트 (AsyncProxy[T] 등)


class HandlerWrapper[**P, T: type, R]:
    pass


class Container[T]:
    """컨테이너 클래스 - 순수 데이터 홀더

    Container는 메타데이터만 저장하고, 로직은 manager 하위 모듈이 담당합니다.
    - scope 조회 → __scope__ 메타데이터 직접 읽기
    - 의존성 분석 → manager.registry.factory.analyze_dependencies(container)
    - 핸들러 바인딩 → manager.lifecycle._bind_handler_methods(container)
    """

    instance: T | None
    kls: type[T]
    elements: list[Element]
    _dependencies: list[DependencyInfo] | None  # Lazy: ContainerManager가 분석

    def __init__(self, kls: type[T], component_id: str):
        self.kls = kls
        self.component_id = component_id
        self.instance = None
        self.elements = []
        self._dependencies = None  # Lazy initialization
        self.parent_instance: object | None = None
        self.parent_container: Container | None = None

    @property
    def scope(self) -> "Scope":
        """데코레이터 순서와 무관하게 __scope__ 메타데이터를 직접 읽음"""
        from .scope import get_scope

        return get_scope(self.kls)

    @property
    def dependencies(self) -> list[DependencyInfo]:
        """의존성 정보 (Lazy - ContainerFactory가 분석)"""
        if self._dependencies is None:
            self._dependencies = (
                get_container_manager().factory_manager.analyze_dependencies(self)
            )
        return self._dependencies

    async def initialize(self) -> T:
        """컨테이너 초기화 메서드 (비동기)"""
        instance = self.kls()
        return instance

    async def shutdown(self) -> None:
        """컨테이너 종료 메서드 (비동기)"""

    @classmethod
    def register[U: type](cls, kls: U) -> "Container[U]":
        if not hasattr(kls, "__component_id__"):
            kls.__component_id__ = str(uuid4())

        registry = get_container_registry()

        if kls not in registry:
            registry[kls] = {}

        if kls.__component_id__ not in registry[kls]:
            registry[kls][kls.__component_id__] = Container(kls, kls.__component_id__)
        container = registry[kls][kls.__component_id__]
        return container

    def add_element(self, key: str, value: object) -> None:
        element = Element(key, value)
        self.elements.append(element)

    def get_elements(self, key: str) -> list:
        """특정 키에 해당하는 요소들 반환"""
        return [element.value for element in self.elements if element.key == key]

    def get_element[U](self, key: str, default: U | None = None) -> U:
        elements = self.get_elements(key)
        if elements:
            return elements[0]  # 첫 번째 요소 반환
        else:
            if default is not None:
                return default
            raise KeyError(f"Element with key '{key}' not found.")
