"""GroupRegistry - EntryGroup들을 관리하는 Registry

EntryGroup들을 관리하고, 그룹 단위로 항목들을 제어합니다.

사용 예시:
    class MiddlewareChain(GroupRegistry[Middleware]):
        pass

    chain = MiddlewareChain()
    chain.add_group_after(auth_middleware, logging_middleware)
    chain.disable(auth_middleware)
"""

from abc import ABC
from typing import Generic, TypeVar, Iterator, Optional

from .group import EntryGroup

T = TypeVar("T")


class GroupRegistry(ABC, Generic[T]):
    """
    EntryGroup들을 관리하는 Registry

    여러 EntryGroup을 관리하고, 그룹 추가/제거, 항목 활성화/비활성화를 지원합니다.

    Attributes:
        groups: 등록된 그룹 리스트
        default_group: 기본 그룹

    사용 예시:
        registry = GroupRegistry[Middleware]()
        registry.add_group_after(middleware1, middleware2)
        registry.disable(middleware1)
    """

    # 서브클래스에서 오버라이드 가능한 그룹 타입
    group_type: type[EntryGroup] = EntryGroup

    def __init__(self):
        self._groups: list[EntryGroup[T]] = []
        self._default_group = self.group_type("default")
        self._groups.append(self._default_group)
        # 캐시 (성능 최적화)
        self._items_cache: list[T] | None = None

    @property
    def groups(self) -> list[EntryGroup[T]]:
        """등록된 그룹 리스트"""
        return self._groups

    @property
    def default_group(self) -> EntryGroup[T]:
        """기본 그룹"""
        return self._default_group

    def add_group(self, name: str) -> EntryGroup[T]:
        """
        새 그룹 추가 (마지막에)

        Args:
            name: 그룹 이름

        Returns:
            생성된 그룹
        """
        group = self.group_type(name)
        self._groups.append(group)
        self._invalidate_cache()
        return group

    def add_group_before(
        self,
        *items: T,
        target_group: Optional[EntryGroup[T]] = None,
    ) -> EntryGroup[T]:
        """
        특정 그룹 앞에 새 그룹 추가

        Args:
            *items: 추가할 항목들
            target_group: 대상 그룹 (None이면 default 그룹 앞)

        Returns:
            생성된 그룹
        """
        target = target_group or self._default_group
        index = self._groups.index(target)

        new_group = self.group_type(f"before_{target.name}")
        new_group.add(*items)
        self._groups.insert(index, new_group)
        self._invalidate_cache()

        return new_group

    def add_group_after(
        self,
        *items: T,
        target_group: Optional[EntryGroup[T]] = None,
    ) -> EntryGroup[T]:
        """
        특정 그룹 뒤에 새 그룹 추가

        Args:
            *items: 추가할 항목들
            target_group: 대상 그룹 (None이면 default 그룹 뒤)

        Returns:
            생성된 그룹
        """
        target = target_group or self._default_group
        index = self._groups.index(target) + 1

        new_group = self.group_type(f"after_{target.name}")
        new_group.add(*items)
        self._groups.insert(index, new_group)
        self._invalidate_cache()

        return new_group

    def get_default_group(self) -> EntryGroup[T]:
        """기본 그룹 반환"""
        return self._default_group

    def find_item(self, item: T) -> tuple[EntryGroup[T], int] | None:
        """
        항목이 속한 그룹과 인덱스 찾기

        Args:
            item: 찾을 항목

        Returns:
            (그룹, 인덱스) 튜플 또는 None
        """
        for group in self._groups:
            if item in group:
                return group, group.items.index(item)
        return None

    def disable(self, *items: T) -> "GroupRegistry[T]":
        """
        특정 항목 비활성화

        Args:
            *items: 비활성화할 항목들

        Returns:
            self (메서드 체이닝용)
        """
        for item in items:
            result = self.find_item(item)
            if result:
                group, _ = result
                group.disable_item(item)
        self._invalidate_cache()
        return self

    def enable(self, *items: T) -> "GroupRegistry[T]":
        """
        특정 항목 활성화

        Args:
            *items: 활성화할 항목들

        Returns:
            self (메서드 체이닝용)
        """
        for item in items:
            result = self.find_item(item)
            if result:
                group, _ = result
                group.enable_item(item)
        self._invalidate_cache()
        return self

    def is_disabled(self, item: T) -> bool:
        """항목이 비활성화되었는지 확인"""
        result = self.find_item(item)
        if result:
            group, _ = result
            return group.is_item_disabled(item)
        return False

    def get_all_items(self) -> list[T]:
        """
        모든 활성화된 항목을 순서대로 반환 (캐싱됨)

        Returns:
            항목 리스트
        """
        if self._items_cache is not None:
            return self._items_cache

        all_items = []
        for group in self._groups:
            all_items.extend(group.get_active_items())

        self._items_cache = all_items
        return all_items

    def _invalidate_cache(self) -> None:
        """캐시 무효화"""
        self._items_cache = None

    def __len__(self) -> int:
        return sum(len(group) for group in self._groups)

    def __iter__(self) -> Iterator[EntryGroup[T]]:
        return iter(self._groups)

    def __repr__(self) -> str:
        active_count = len(self.get_all_items())
        return f"{self.__class__.__name__}(groups={len(self._groups)}, active_items={active_count})"
