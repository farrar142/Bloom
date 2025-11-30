"""DirtyTracker - Entity 변경 추적 시스템"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    pass


class EntityState(Enum):
    """엔티티 상태"""

    TRANSIENT = "transient"  # 새로 생성됨, DB에 없음
    MANAGED = "managed"  # 세션에서 관리 중
    DETACHED = "detached"  # 세션에서 분리됨
    DELETED = "deleted"  # 삭제 예정


@dataclass
class FieldChange:
    """필드 변경 정보"""

    field_name: str
    old_value: Any
    new_value: Any


@dataclass
class DirtyTracker:
    """엔티티 변경 추적기

    엔티티 인스턴스의 필드 변경을 추적합니다.
    dirty tracking을 통해 UPDATE 시 변경된 필드만 업데이트합니다.

    Examples:
        user = User(name="alice")
        user.__bloom_tracker__ = DirtyTracker()

        user.name = "bob"  # Column.__set__에서 자동 추적

        if user.__bloom_tracker__.is_dirty:
            changes = user.__bloom_tracker__.get_changes()
            # [FieldChange(field_name="name", old_value="alice", new_value="bob")]
    """

    state: EntityState = EntityState.TRANSIENT
    _dirty_fields: dict[str, FieldChange] = field(default_factory=dict)
    _original_values: dict[str, Any] = field(default_factory=dict)
    _is_new: bool = True

    def mark_dirty(self, field_name: str, old_value: Any, new_value: Any) -> None:
        """필드를 dirty로 마킹"""
        if field_name not in self._original_values:
            self._original_values[field_name] = old_value

        self._dirty_fields[field_name] = FieldChange(
            field_name=field_name,
            old_value=self._original_values[field_name],
            new_value=new_value,
        )

    def is_field_dirty(self, field_name: str) -> bool:
        """특정 필드가 dirty인지 확인"""
        return field_name in self._dirty_fields

    @property
    def is_dirty(self) -> bool:
        """변경된 필드가 있는지 확인"""
        return len(self._dirty_fields) > 0

    @property
    def is_new(self) -> bool:
        """새로 생성된 엔티티인지 (아직 persist 안됨)"""
        return self._is_new

    def get_dirty_fields(self) -> list[str]:
        """dirty 필드명 목록 반환"""
        return list(self._dirty_fields.keys())

    def get_changes(self) -> list[FieldChange]:
        """모든 변경 정보 반환"""
        return list(self._dirty_fields.values())

    def get_change(self, field_name: str) -> FieldChange | None:
        """특정 필드의 변경 정보 반환"""
        return self._dirty_fields.get(field_name)

    def get_original_value(self, field_name: str) -> Any:
        """필드의 원본 값 반환"""
        return self._original_values.get(field_name)

    def clear(self) -> None:
        """dirty 상태 초기화 (flush 후 호출)"""
        self._dirty_fields.clear()
        self._original_values.clear()

    def mark_persisted(self) -> None:
        """persist 완료 마킹"""
        self._is_new = False
        self.state = EntityState.MANAGED
        self.clear()

    def mark_loaded(self, values: dict[str, Any]) -> None:
        """DB에서 로드됨 마킹"""
        self._is_new = False
        self.state = EntityState.MANAGED
        self._original_values = values.copy()
        self._dirty_fields.clear()

    def mark_deleted(self) -> None:
        """삭제 마킹"""
        self.state = EntityState.DELETED

    def detach(self) -> None:
        """세션에서 분리"""
        self.state = EntityState.DETACHED

    def __repr__(self) -> str:
        dirty = list(self._dirty_fields.keys())
        return f"DirtyTracker(state={self.state.value}, dirty={dirty})"
