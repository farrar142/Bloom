"""EntryGroup - Entry들을 그룹화하는 클래스

여러 Entry를 그룹화하여 일괄 관리합니다.
그룹 단위로 활성화/비활성화가 가능합니다.

사용 예시:
    class MiddlewareGroup(EntryGroup[Middleware]):
        pass

    group = MiddlewareGroup("auth")
    group.add(jwt_middleware, session_middleware)
    group.disable()  # 그룹 전체 비활성화
"""

from typing import Generic, TypeVar, Iterator

T = TypeVar("T")


class EntryGroup(Generic[T]):
    """
    Entry들을 그룹화하는 클래스

    여러 항목을 그룹으로 묶어 관리합니다.
    그룹 전체를 활성화/비활성화할 수 있습니다.

    Attributes:
        name: 그룹 이름 (디버깅용)
        enabled: 그룹 활성화 상태

    사용 예시:
        group = EntryGroup[Middleware]("security")
        group.add(cors, auth, csrf)
        group.disable()
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._items: list[T] = []
        self._enabled = True
        # 개별 비활성화된 항목 id
        self._disabled_items: set[int] = set()

    @property
    def enabled(self) -> bool:
        """그룹 활성화 상태"""
        return self._enabled

    @property
    def items(self) -> list[T]:
        """그룹에 속한 모든 항목"""
        return self._items

    def add(self, *items: T) -> "EntryGroup[T]":
        """
        항목 추가

        Args:
            *items: 추가할 항목들

        Returns:
            self (메서드 체이닝용)
        """
        for item in items:
            self._items.append(item)
        return self

    def remove(self, item: T) -> bool:
        """
        항목 제거

        Args:
            item: 제거할 항목

        Returns:
            제거 성공 여부
        """
        if item in self._items:
            self._items.remove(item)
            self._disabled_items.discard(id(item))
            return True
        return False

    def disable(self) -> "EntryGroup[T]":
        """그룹 비활성화"""
        self._enabled = False
        return self

    def enable(self) -> "EntryGroup[T]":
        """그룹 활성화"""
        self._enabled = True
        return self

    def disable_item(self, item: T) -> "EntryGroup[T]":
        """개별 항목 비활성화"""
        self._disabled_items.add(id(item))
        return self

    def enable_item(self, item: T) -> "EntryGroup[T]":
        """개별 항목 활성화"""
        self._disabled_items.discard(id(item))
        return self

    def is_item_disabled(self, item: T) -> bool:
        """항목이 개별적으로 비활성화되었는지 확인"""
        return id(item) in self._disabled_items

    def get_active_items(self) -> list[T]:
        """
        활성화된 항목 목록 반환

        그룹이 비활성화되면 빈 리스트를 반환합니다.
        개별 비활성화된 항목도 제외됩니다.
        """
        if not self._enabled:
            return []
        return [item for item in self._items if not self.is_item_disabled(item)]

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter(self._items)

    def __contains__(self, item: T) -> bool:
        return item in self._items

    def __repr__(self) -> str:
        status = "enabled" if self._enabled else "disabled"
        return f"{self.__class__.__name__}(name={self.name}, items={len(self._items)}, {status})"
