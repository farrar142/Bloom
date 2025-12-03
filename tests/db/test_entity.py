"""Entity 테스트"""

import pytest
from bloom.db import Entity, PrimaryKey, StringColumn, IntegerColumn, BooleanColumn
from bloom.db.entity import get_entity_meta, get_pk_value, set_pk_value, entity_to_dict
from bloom.db.tracker import EntityState


class TestEntityDecorator:
    """@Entity 데코레이터 테스트"""

    def test_entity_creates_meta(self):
        """엔티티 메타데이터 생성"""

        @Entity
        class TestEntity:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn()

        meta = get_entity_meta(TestEntity)
        assert meta is not None
        assert meta.table_name == "testentity"
        assert "id" in meta.columns
        assert "name" in meta.columns
        assert meta.primary_key == "id"

    def test_entity_custom_table_name(self):
        """커스텀 테이블명"""

        @Entity(table_name="custom_users")
        class User:
            id = PrimaryKey[int]()
            name = StringColumn()

        meta = get_entity_meta(User)
        assert meta is not None
        assert meta.table_name == "custom_users"

    def test_entity_instance_has_tracker(self):
        """엔티티 인스턴스는 DirtyTracker를 가짐"""

        @Entity
        class TrackedEntity:
            id = PrimaryKey[int]()
            value = StringColumn()

        entity = TrackedEntity()
        tracker = getattr(entity, "__bloom_tracker__", None)

        assert tracker is not None
        assert tracker.state == EntityState.TRANSIENT


class TestColumns:
    """Column 테스트"""

    def test_primary_key_auto_increment(self):
        """PrimaryKey auto_increment"""

        @Entity
        class AutoIncEntity:
            id = PrimaryKey[int](auto_increment=True)

        meta = get_entity_meta(AutoIncEntity)
        assert meta is not None
        pk_col = meta.columns["id"]
        assert pk_col.auto_increment is True

    def test_column_nullable(self):
        """Column nullable 옵션"""

        @Entity
        class NullableEntity:
            id = PrimaryKey[int]()
            required = StringColumn(nullable=False)
            optional = StringColumn(nullable=True)

        meta = get_entity_meta(NullableEntity)
        assert meta is not None
        assert meta.columns["required"].nullable is False
        assert meta.columns["optional"].nullable is True

    def test_column_default(self):
        """Column default 값"""

        @Entity
        class DefaultEntity:
            id = PrimaryKey[int]()
            count = IntegerColumn(default=0)
            active = BooleanColumn(default=True)

        meta = get_entity_meta(DefaultEntity)
        assert meta is not None
        assert meta.columns["count"].default == 0
        assert meta.columns["active"].default is True

    def test_column_unique(self):
        """Column unique 제약"""

        @Entity
        class UniqueEntity:
            id = PrimaryKey[int]()
            email = StringColumn(unique=True)

        meta = get_entity_meta(UniqueEntity)
        assert meta is not None
        assert meta.columns["email"].unique is True


class TestEntityHelpers:
    """Entity 헬퍼 함수 테스트"""

    def test_get_pk_value(self):
        """PK 값 조회"""

        @Entity
        class PKEntity:
            id = PrimaryKey[int]()
            name = StringColumn()

        entity = PKEntity()
        entity.id = 42

        assert get_pk_value(entity) == 42

    def test_set_pk_value(self):
        """PK 값 설정"""

        @Entity
        class PKEntity:
            id = PrimaryKey[int]()
            name = StringColumn()

        entity = PKEntity()
        set_pk_value(entity, 100)

        assert entity.id == 100

    def test_entity_to_dict(self):
        """엔티티를 딕셔너리로 변환"""

        @Entity
        class DictEntity:
            id = PrimaryKey[int]()
            name = StringColumn()
            age = IntegerColumn()

        entity = DictEntity()
        entity.id = 1
        entity.name = "alice"
        entity.age = 25

        result = entity_to_dict(entity)

        assert result["id"] == 1
        assert result["name"] == "alice"
        assert result["age"] == 25


class TestDirtyTracking:
    """Dirty Tracking 테스트"""

    def test_track_changes(self):
        """변경 추적"""

        @Entity
        class TrackedEntity:
            id = PrimaryKey[int]()
            name = StringColumn()
            value = IntegerColumn()

        entity = TrackedEntity()
        entity.id = 1
        entity.name = "original"
        entity.value = 100

        tracker = getattr(entity, "__bloom_tracker__")

        # mark_loaded로 초기 상태 설정 (DB에서 로드된 것처럼)
        tracker.mark_loaded({"id": 1, "name": "original", "value": 100})

        # 변경
        entity.name = "modified"

        # 변경 확인
        changes = tracker.get_changes()
        assert len(changes) == 1
        assert changes[0].field_name == "name"
        assert changes[0].old_value == "original"
        assert changes[0].new_value == "modified"

    def test_dirty_flag(self):
        """Dirty 플래그"""

        @Entity
        class DirtyEntity:
            id = PrimaryKey[int]()
            name = StringColumn()

        entity = DirtyEntity()
        entity.id = 1
        entity.name = "test"

        tracker = getattr(entity, "__bloom_tracker__")
        tracker.mark_loaded({"id": 1, "name": "test"})

        # 변경 전
        assert not tracker.is_dirty

        # 변경 후
        entity.name = "changed"
        assert tracker.is_dirty
