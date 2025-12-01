"""DirtyTracker 테스트 - 엔티티 변경 추적 시스템"""

import pytest

from bloom.db.tracker import DirtyTracker, EntityState, FieldChange


# =============================================================================
# EntityState Tests
# =============================================================================


class TestEntityState:
    """EntityState 열거형 테스트"""

    def test_transient_state(self):
        """TRANSIENT 상태"""
        assert EntityState.TRANSIENT.value == "transient"

    def test_managed_state(self):
        """MANAGED 상태"""
        assert EntityState.MANAGED.value == "managed"

    def test_detached_state(self):
        """DETACHED 상태"""
        assert EntityState.DETACHED.value == "detached"

    def test_deleted_state(self):
        """DELETED 상태"""
        assert EntityState.DELETED.value == "deleted"


# =============================================================================
# FieldChange Tests
# =============================================================================


class TestFieldChange:
    """FieldChange 테스트"""

    def test_create_field_change(self):
        """FieldChange 생성"""
        change = FieldChange(
            field_name="name",
            old_value="alice",
            new_value="bob",
        )

        assert change.field_name == "name"
        assert change.old_value == "alice"
        assert change.new_value == "bob"

    def test_field_change_with_none(self):
        """None 값 변경"""
        change = FieldChange(
            field_name="email",
            old_value=None,
            new_value="alice@example.com",
        )

        assert change.old_value is None
        assert change.new_value == "alice@example.com"


# =============================================================================
# DirtyTracker Basic Tests
# =============================================================================


class TestDirtyTrackerBasic:
    """DirtyTracker 기본 테스트"""

    def test_default_state(self):
        """기본 상태"""
        tracker = DirtyTracker()

        assert tracker.state == EntityState.TRANSIENT
        assert tracker.is_new is True
        assert tracker.is_dirty is False

    def test_is_new_initially_true(self):
        """새로 생성된 트래커는 is_new=True"""
        tracker = DirtyTracker()
        assert tracker.is_new is True

    def test_empty_dirty_fields(self):
        """초기 dirty 필드 없음"""
        tracker = DirtyTracker()

        assert tracker.get_dirty_fields() == []
        assert tracker.get_changes() == []


# =============================================================================
# Mark Dirty Tests
# =============================================================================


class TestMarkDirty:
    """dirty 마킹 테스트"""

    def test_mark_dirty(self):
        """필드 dirty 마킹"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")

        assert tracker.is_dirty is True
        assert tracker.is_field_dirty("name") is True
        assert "name" in tracker.get_dirty_fields()

    def test_mark_dirty_multiple_fields(self):
        """여러 필드 dirty 마킹"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")
        tracker.mark_dirty("age", 25, 30)

        assert len(tracker.get_dirty_fields()) == 2
        assert "name" in tracker.get_dirty_fields()
        assert "age" in tracker.get_dirty_fields()

    def test_mark_dirty_same_field_multiple_times(self):
        """같은 필드 여러 번 변경"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")
        tracker.mark_dirty("name", "bob", "charlie")

        # 원래 값은 alice로 유지
        change = tracker.get_change("name")
        assert change is not None
        assert change.old_value == "alice"
        assert change.new_value == "charlie"

    def test_original_value_preserved(self):
        """원래 값 보존"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")
        tracker.mark_dirty("name", "bob", "charlie")
        tracker.mark_dirty("name", "charlie", "david")

        # 첫 번째 값만 저장됨
        assert tracker.get_original_value("name") == "alice"


# =============================================================================
# Get Changes Tests
# =============================================================================


class TestGetChanges:
    """변경 정보 조회 테스트"""

    def test_get_changes(self):
        """모든 변경 정보 조회"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")
        tracker.mark_dirty("age", 25, 30)

        changes = tracker.get_changes()

        assert len(changes) == 2
        assert all(isinstance(c, FieldChange) for c in changes)

    def test_get_change(self):
        """특정 필드 변경 정보"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")

        change = tracker.get_change("name")

        assert change is not None
        assert change.field_name == "name"
        assert change.old_value == "alice"
        assert change.new_value == "bob"

    def test_get_change_not_found(self):
        """없는 필드 변경 정보"""
        tracker = DirtyTracker()

        change = tracker.get_change("nonexistent")

        assert change is None

    def test_get_original_value(self):
        """원래 값 조회"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")

        assert tracker.get_original_value("name") == "alice"

    def test_get_original_value_not_found(self):
        """없는 필드 원래 값"""
        tracker = DirtyTracker()

        assert tracker.get_original_value("nonexistent") is None


# =============================================================================
# Clear Tests
# =============================================================================


class TestClear:
    """clear 테스트"""

    def test_clear_dirty_fields(self):
        """dirty 필드 초기화"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")
        tracker.mark_dirty("age", 25, 30)

        tracker.clear()

        assert tracker.is_dirty is False
        assert tracker.get_dirty_fields() == []
        assert tracker.get_changes() == []

    def test_clear_preserves_state(self):
        """clear는 state 보존"""
        tracker = DirtyTracker()
        tracker.state = EntityState.MANAGED

        tracker.mark_dirty("name", "alice", "bob")
        tracker.clear()

        assert tracker.state == EntityState.MANAGED

    def test_clear_resets_original_values(self):
        """clear는 original values도 초기화"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")
        tracker.clear()

        assert tracker.get_original_value("name") is None


# =============================================================================
# State Transition Tests
# =============================================================================


class TestStateTransitions:
    """상태 전이 테스트"""

    def test_mark_persisted(self):
        """persist 완료 마킹"""
        tracker = DirtyTracker()
        tracker.mark_dirty("name", "alice", "bob")

        tracker.mark_persisted()

        assert tracker.state == EntityState.MANAGED
        assert tracker.is_new is False
        assert tracker.is_dirty is False

    def test_mark_loaded(self):
        """DB에서 로드됨 마킹"""
        tracker = DirtyTracker()
        values = {"name": "alice", "age": 25}

        tracker.mark_loaded(values)

        assert tracker.state == EntityState.MANAGED
        assert tracker.is_new is False
        assert tracker.is_dirty is False
        assert tracker.get_original_value("name") == "alice"
        assert tracker.get_original_value("age") == 25

    def test_mark_loaded_copies_values(self):
        """mark_loaded는 값 복사"""
        tracker = DirtyTracker()
        values = {"name": "alice"}

        tracker.mark_loaded(values)

        # 원본 수정해도 tracker에 영향 없음
        values["name"] = "bob"
        assert tracker.get_original_value("name") == "alice"

    def test_mark_deleted(self):
        """삭제 마킹"""
        tracker = DirtyTracker()
        tracker.state = EntityState.MANAGED

        tracker.mark_deleted()

        assert tracker.state == EntityState.DELETED

    def test_detach(self):
        """세션 분리"""
        tracker = DirtyTracker()
        tracker.state = EntityState.MANAGED

        tracker.detach()

        assert tracker.state == EntityState.DETACHED


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_mark_dirty_with_none_values(self):
        """None 값으로 dirty 마킹"""
        tracker = DirtyTracker()

        tracker.mark_dirty("email", None, "alice@example.com")

        change = tracker.get_change("email")
        assert change is not None
        assert change.old_value is None
        assert change.new_value == "alice@example.com"

    def test_mark_dirty_to_none(self):
        """None으로 변경"""
        tracker = DirtyTracker()

        tracker.mark_dirty("email", "alice@example.com", None)

        change = tracker.get_change("email")
        assert change is not None
        assert change.old_value == "alice@example.com"
        assert change.new_value is None

    def test_is_field_dirty_false(self):
        """dirty가 아닌 필드"""
        tracker = DirtyTracker()

        tracker.mark_dirty("name", "alice", "bob")

        assert tracker.is_field_dirty("name") is True
        assert tracker.is_field_dirty("age") is False

    def test_repr(self):
        """repr"""
        tracker = DirtyTracker()
        tracker.state = EntityState.MANAGED
        tracker.mark_dirty("name", "alice", "bob")

        repr_str = repr(tracker)

        assert "managed" in repr_str
        assert "name" in repr_str


# =============================================================================
# Integration Tests
# =============================================================================


class TestTrackerIntegration:
    """트래커 통합 테스트"""

    def test_full_lifecycle(self):
        """전체 생명주기"""
        tracker = DirtyTracker()

        # 1. 새로 생성 (TRANSIENT)
        assert tracker.state == EntityState.TRANSIENT
        assert tracker.is_new is True

        # 2. persist 완료 (MANAGED)
        tracker.mark_persisted()
        assert tracker.state == EntityState.MANAGED
        assert tracker.is_new is False

        # 3. 값 변경 (dirty)
        tracker.mark_dirty("name", "alice", "bob")
        assert tracker.is_dirty is True

        # 4. flush (dirty 초기화)
        tracker.clear()
        assert tracker.is_dirty is False

        # 5. 삭제 (DELETED)
        tracker.mark_deleted()
        assert tracker.state == EntityState.DELETED

    def test_load_modify_save_cycle(self):
        """로드 → 수정 → 저장 사이클"""
        tracker = DirtyTracker()

        # 1. DB에서 로드
        tracker.mark_loaded({"name": "alice", "age": 25})
        assert tracker.state == EntityState.MANAGED
        assert tracker.is_dirty is False

        # 2. 수정
        tracker.mark_dirty("name", "alice", "bob")
        assert tracker.is_dirty is True

        changes = tracker.get_changes()
        assert len(changes) == 1
        assert changes[0].field_name == "name"

        # 3. 저장 (flush)
        tracker.clear()
        assert tracker.is_dirty is False

    def test_detach_and_merge_cycle(self):
        """분리 → 병합 사이클"""
        tracker = DirtyTracker()

        # 1. 관리 상태
        tracker.mark_persisted()
        assert tracker.state == EntityState.MANAGED

        # 2. 분리
        tracker.detach()
        assert tracker.state == EntityState.DETACHED

        # 3. 병합 (mark_loaded로 시뮬레이션)
        tracker.mark_loaded({"name": "updated"})
        assert tracker.state == EntityState.MANAGED

    def test_multiple_changes_tracking(self):
        """다중 변경 추적"""
        tracker = DirtyTracker()

        # 초기값 설정
        tracker.mark_loaded({"name": "alice", "age": 25, "status": "active"})

        # 여러 번 변경
        tracker.mark_dirty("name", "alice", "bob")
        tracker.mark_dirty("age", 25, 26)
        tracker.mark_dirty("name", "bob", "charlie")  # 다시 변경

        # 원래 값 확인
        assert tracker.get_original_value("name") == "alice"
        assert tracker.get_original_value("age") == 25

        # 최종 값 확인
        changes = {c.field_name: c.new_value for c in tracker.get_changes()}
        assert changes["name"] == "charlie"
        assert changes["age"] == 26

        # status는 변경 안됨
        assert tracker.is_field_dirty("status") is False


# =============================================================================
# Thread Safety Note
# =============================================================================


class TestTrackerNotes:
    """트래커 참고사항 테스트"""

    def test_tracker_is_instance_specific(self):
        """트래커는 인스턴스별"""
        tracker1 = DirtyTracker()
        tracker2 = DirtyTracker()

        tracker1.mark_dirty("name", "a", "b")

        assert tracker1.is_dirty is True
        assert tracker2.is_dirty is False

    def test_tracker_state_isolation(self):
        """트래커 상태 격리"""
        tracker1 = DirtyTracker()
        tracker2 = DirtyTracker()

        tracker1.state = EntityState.MANAGED
        tracker2.state = EntityState.DELETED

        assert tracker1.state != tracker2.state
