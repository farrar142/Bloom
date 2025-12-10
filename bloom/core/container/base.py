from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable
from uuid import uuid4
from .manager import get_container_manager, get_container_registry

if TYPE_CHECKING:
    from .scope import Scope


class ContainerTransferError(Exception):
    """컨테이너 간 흡수/전이 불가능 시 발생하는 예외"""

    pass


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
    default_value: object = None  # 기본값
    is_async_proxy: bool = False  # AsyncProxy[T]로 선언되었는지 여부
    raw_type_hint: object = None  # 원본 타입 힌트 (AsyncProxy[T] 등)


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
        """element에서 scope 조회 (없으면 SINGLETON 기본값)"""
        from .scope import Scope

        try:
            return self.get_element("scope", Scope.SINGLETON)
        except KeyError:
            return Scope.SINGLETON

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
    def register(cls, kls: type) -> "Container":
        """클래스를 Container로 등록

        기존에 더 구체적인 컨테이너(subclass)가 있으면 elements만 추가합니다.
        """
        if not hasattr(kls, "__component_id__"):
            kls.__component_id__ = str(uuid4())

        new_container = cls(kls, kls.__component_id__)
        return cls.transfer_or_absorb(kls, new_container)

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

    # =========================================================================
    # 컨테이너 흡수/전이 시스템
    # =========================================================================

    def can_transfer_to(self, other_type: type["Container"]) -> bool:
        """다른 컨테이너 타입으로 전이 가능한지 확인

        규칙:
        - 같은 타입: 가능
        - self가 other의 subclass (더 구체적): 불가능 (other가 self를 흡수해야 함)
        - other가 self의 subclass (더 구체적): 가능 (self -> other로 전이)
        - 상속 관계 없음: 불가능
        """
        self_type = type(self)

        # 같은 타입
        if self_type == other_type:
            return True

        # other가 self의 subclass (예: Container -> HandlerContainer)
        # self의 element를 other로 전이
        if issubclass(other_type, self_type):
            return True

        return False

    def can_absorb_from(self, other: "Container") -> bool:
        """다른 컨테이너의 element를 흡수할 수 있는지 확인

        규칙:
        - 같은 타입: 가능
        - self가 other의 subclass (더 구체적): 가능 (self가 other 흡수)
        - other가 self의 subclass: 불가능 (other가 self를 흡수해야 함)
        - 상속 관계 없음: 불가능
        """
        self_type = type(self)
        other_type = type(other)

        # 같은 타입
        if self_type == other_type:
            return True

        # self가 other의 subclass (예: HandlerContainer가 Container 흡수)
        if issubclass(self_type, other_type):
            return True

        return False

    def absorb_elements_from(self, other: "Container") -> None:
        """다른 컨테이너의 elements를 흡수"""
        if not self.can_absorb_from(other):
            raise ContainerTransferError(
                f"Cannot absorb: {type(self).__name__} cannot absorb from {type(other).__name__}. "
                f"They are incompatible container types."
            )

        # other의 모든 elements 복사
        for element in other.elements:
            self.add_element(element.key, element.value)

    @classmethod
    def transfer_or_absorb(
        cls,
        kls: type | Callable,
        new_container: "Container",
    ) -> "Container":
        """기존 컨테이너가 있으면 흡수/전이 처리, 없으면 새 컨테이너 등록

        Args:
            kls: 대상 클래스/함수
            new_container: 새로 생성하려는 컨테이너

        Returns:
            최종 컨테이너 (흡수/전이 결과 또는 new_container)

        Raises:
            ContainerTransferError: 호환 불가능한 컨테이너 타입 간 충돌 시
        """
        registry = get_container_registry()
        component_id = getattr(kls, "__component_id__", None)

        # 기존 컨테이너가 없으면 새 컨테이너 등록
        if kls not in registry or not component_id or component_id not in registry[kls]:
            if not hasattr(kls, "__component_id__"):
                kls.__component_id__ = new_container.component_id  # type: ignore[attr-defined]
            if kls not in registry:
                registry[kls] = {}
            registry[kls][new_container.component_id] = new_container
            return new_container

        existing = registry[kls][component_id]
        new_type = type(new_container)
        existing_type = type(existing)

        # 같은 타입이면 elements만 합침
        if existing_type == new_type:
            for element in new_container.elements:
                existing.add_element(element.key, element.value)
            return existing

        # existing이 new로 전이 가능 (예: Container -> HandlerContainer)
        # new가 existing의 elements를 흡수
        if existing.can_transfer_to(new_type):
            new_container.absorb_elements_from(existing)
            registry[kls][component_id] = new_container
            return new_container

        # new가 existing으로 전이 가능 (예: Container가 먼저, HandlerContainer가 나중)
        # 위 조건에서 이미 처리됨 (can_transfer_to는 subclass 방향)

        # existing이 new를 흡수 가능 (예: HandlerContainer가 Container 흡수)
        if existing.can_absorb_from(new_container):
            existing.absorb_elements_from(new_container)
            return existing

        # 호환 불가능
        raise ContainerTransferError(
            f"Cannot combine containers: {existing_type.__name__} and {new_type.__name__} "
            f"are incompatible. They have no inheritance relationship."
        )
