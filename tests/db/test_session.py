"""Session 상세 기능 테스트"""

import pytest

from bloom.db import (
    Entity,
    IntegerColumn,
    PrimaryKey,
    StringColumn,
    create,
)
from bloom.db.backends.sqlite import SQLiteBackend
from bloom.db.expressions import OrderBy
from bloom.db.session import SessionFactory
from bloom.db.tracker import DirtyTracker, EntityState

# =============================================================================
# Test Entities
# =============================================================================


@Entity(table_name="session_users")
class User:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100, default="")
    email = StringColumn(max_length=255, nullable=True)
    age = IntegerColumn(nullable=True)


@Entity(table_name="session_posts")
class Post:
    id = PrimaryKey[int](auto_increment=True)
    title = StringColumn(max_length=200, default="")
    content = StringColumn(nullable=True, default="")
    author_id = IntegerColumn(nullable=True)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def backend():
    """인메모리 SQLite 백엔드 (각 테스트마다 고유한 DB로 격리)"""
    import uuid

    # 각 테스트마다 고유한 DB 이름 생성
    db_name = f"test_{uuid.uuid4().hex[:8]}"
    return SQLiteBackend(f"file:{db_name}?mode=memory&cache=shared")


@pytest.fixture
def session_factory(backend):
    """세션 팩토리"""
    factory = SessionFactory(backend)
    factory.create_tables(User, Post)
    return factory


# =============================================================================
# Session Lifecycle Tests
# =============================================================================


class TestSessionLifecycle:
    """세션 생명주기 테스트"""

    def test_session_open_close(self, session_factory):
        """세션 열기/닫기"""
        session = session_factory.create()
        assert session._closed is False

        session.close()
        assert session._closed is True

    def test_session_context_manager_closes(self, session_factory):
        """컨텍스트 매니저로 자동 종료"""
        with session_factory.session() as session:
            assert session._closed is False

        assert session._closed is True

    def test_operations_on_closed_session_raise(self, session_factory):
        """닫힌 세션에서 연산 시 예외"""
        session = session_factory.create()
        session.close()

        with pytest.raises(RuntimeError, match="closed"):
            session.add(create(User, name="test"))

        with pytest.raises(RuntimeError, match="closed"):
            session.get(User, 1)

        with pytest.raises(RuntimeError, match="closed"):
            session.flush()

    def test_double_close_is_safe(self, session_factory):
        """중복 close는 안전"""
        session = session_factory.create()
        session.close()
        session.close()  # 예외 없음


# =============================================================================
# Dirty Tracking Tests
# =============================================================================


class TestDirtyTracking:
    """변경 추적 테스트"""

    def test_new_entity_has_tracker(self, session_factory):
        """새 엔티티에 트래커 부착"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

            tracker = getattr(user, "__bloom_tracker__", None)
            assert tracker is not None
            assert isinstance(tracker, DirtyTracker)

    def test_new_entity_state_is_managed(self, session_factory):
        """새 엔티티 상태는 MANAGED"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

            tracker: DirtyTracker = user.__bloom_tracker__  # type: ignore
            assert tracker.state == EntityState.MANAGED

    def test_field_change_marks_dirty(self, session_factory):
        """필드 변경 시 dirty 마킹"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.commit()

            # 변경
            user.name = "bob"

            tracker: DirtyTracker = user.__bloom_tracker__  # type: ignore
            assert tracker.is_dirty
            assert "name" in tracker.get_dirty_fields()

    def test_flush_clears_dirty(self, session_factory):
        """flush 후 dirty 상태 초기화"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.flush()

            tracker: DirtyTracker = user.__bloom_tracker__  # type: ignore
            # flush 후에는 더 이상 새 엔티티가 아님
            assert tracker.is_new is False

    def test_deleted_entity_state(self, session_factory):
        """삭제된 엔티티 상태"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.commit()

            session.delete(user)

            tracker: DirtyTracker = user.__bloom_tracker__  # type: ignore
            assert tracker.state == EntityState.DELETED


# =============================================================================
# Identity Map Tests
# =============================================================================


class TestIdentityMap:
    """Identity Map 테스트"""

    def test_same_pk_returns_same_instance(self, session_factory):
        """같은 PK는 같은 인스턴스 반환"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.commit()

            pk = user.id

            # 두 번 조회해도 같은 인스턴스
            user1 = session.get(User, pk)
            user2 = session.get(User, pk)

            assert user1 is user2

    def test_identity_map_isolation_between_sessions(self, session_factory):
        """세션 간 Identity Map 격리"""
        # 세션 1에서 추가
        with session_factory.session() as session1:
            user = create(User, name="alice")
            session1.add(user)
            session1.commit()
            pk = user.id

        # 세션 2에서 조회
        with session_factory.session() as session2:
            user2 = session2.get(User, pk)
            assert user2 is not None
            assert user2 is not user  # 다른 인스턴스

    def test_identity_map_prevents_duplicate(self, session_factory):
        """Identity Map이 중복 조회 방지"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.flush()
            pk = user.id

            # 직접 SQL로 조회해도 캐시된 인스턴스 반환
            found = session.get(User, pk)
            assert found is user


# =============================================================================
# Flush/Commit Tests
# =============================================================================


class TestFlushCommit:
    """Flush/Commit 테스트"""

    def test_flush_writes_to_db(self, session_factory):
        """flush는 DB에 쓰기"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.flush()

            # flush 후 PK 할당됨
            assert user.id is not None

    def test_commit_without_flush(self, session_factory):
        """commit은 자동으로 flush"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.commit()

            assert user.id is not None

    def test_rollback_discards_changes(self, session_factory):
        """rollback은 변경 취소"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.flush()
            pk = user.id

            session.rollback()

            # 롤백 후 _new 비워짐
            assert len(session._new) == 0

        # 다른 세션에서 조회 시 없음
        with session_factory.session() as session:
            found = session.get(User, pk)
            assert found is None

    def test_autoflush_on_query(self, session_factory):
        """쿼리 전 자동 flush (autoflush=True)"""
        with session_factory.session() as session:
            assert session._autoflush is True

            user = create(User, name="alice")
            session.add(user)

            # 쿼리 수행 시 자동 flush
            results = session.query(User).all()
            assert len(results) == 1
            assert user.id is not None

    def test_no_autoflush_when_disabled(self, session_factory):
        """autoflush=False면 수동 flush 필요"""
        session = session_factory.create()
        session._autoflush = False

        try:
            user = create(User, name="alice")
            session.add(user)

            # autoflush가 꺼져 있어도 쿼리는 동작
            # (단, 새로 추가된 엔티티는 아직 DB에 없음)
            assert user.id is None
        finally:
            session.close()


# =============================================================================
# Merge/Refresh Tests
# =============================================================================


class TestMergeRefresh:
    """Merge/Refresh 테스트"""

    def test_refresh_reloads_data(self, session_factory):
        """refresh는 DB에서 다시 로드"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.commit()

            # 로컬에서 변경 (아직 커밋 안함)
            user.name = "bob"

            # refresh로 DB 값 복원
            session.refresh(user)

            assert user.name == "alice"

    def test_refresh_updates_tracker(self, session_factory):
        """refresh 후 tracker 상태 갱신"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.commit()

            user.name = "bob"
            tracker: DirtyTracker = user.__bloom_tracker__  # type: ignore
            assert tracker.is_dirty

            session.refresh(user)

            # refresh 후 dirty 해제
            assert tracker.is_dirty is False

    def test_merge_detached_entity(self, session_factory):
        """detached 엔티티 merge"""
        # 세션 1에서 생성
        with session_factory.session() as session1:
            user = create(User, name="alice")
            session1.add(user)
            session1.commit()
            pk = user.id

        # 새 세션에서 조회 후 수정하고 merge
        with session_factory.session() as session2:
            user = session2.get(User, pk)
            assert user is not None
            user.name = "bob"
            merged = session2.merge(user)  # merge를 통해 변경사항 반영
            session2.commit()

        # 검증
        with session_factory.session() as session3:
            found = session3.get(User, pk)
            assert found is not None
            assert found.name == "bob"

    def test_merge_new_entity(self, session_factory):
        """새 엔티티 merge는 add처럼 동작"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            merged = session.merge(user)
            session.commit()

            assert merged.id is not None


# =============================================================================
# Delete Tests
# =============================================================================


class TestDelete:
    """삭제 테스트"""

    def test_delete_persisted_entity(self, session_factory):
        """저장된 엔티티 삭제"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.commit()
            pk = user.id

            session.delete(user)
            session.commit()

        # 삭제 확인
        with session_factory.session() as session:
            found = session.get(User, pk)
            assert found is None

    def test_delete_new_entity(self, session_factory):
        """새 엔티티 삭제 (아직 DB에 없음)"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

            assert user in session._new

            session.delete(user)

            # _new에서 제거됨
            assert user not in session._new
            assert user not in session._deleted

    def test_delete_removes_from_dirty(self, session_factory):
        """삭제 시 dirty set에서도 제거"""
        with session_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.commit()

            user.name = "bob"
            session._dirty.add(user)

            session.delete(user)

            assert user not in session._dirty
            assert user in session._deleted


# =============================================================================
# Transaction Edge Cases
# =============================================================================


class TestTransactionEdgeCases:
    """트랜잭션 엣지 케이스"""

    def test_exception_triggers_rollback(self, session_factory):
        """예외 발생 시 자동 롤백"""
        pk = None
        try:
            with session_factory.session() as session:
                user = create(User, name="alice")
                session.add(user)
                session.flush()
                pk = user.id

                raise ValueError("test error")
        except ValueError:
            pass

        # 롤백되어 없음
        with session_factory.session() as session:
            found = session.get(User, pk)
            assert found is None

    def test_multiple_adds_in_one_transaction(self, session_factory):
        """하나의 트랜잭션에서 여러 add"""
        with session_factory.session() as session:
            users = [create(User, name=f"user{i}") for i in range(5)]
            session.add_all(users)
            session.commit()

        with session_factory.session() as session:
            count = session.query(User).count()
            assert count == 5

    def test_mixed_operations_in_transaction(self, session_factory):
        """한 트랜잭션에서 혼합 연산"""
        with session_factory.session() as session:
            # INSERT
            user1 = create(User, name="alice")
            user2 = create(User, name="bob")
            session.add_all([user1, user2])
            session.flush()

            # UPDATE (dirty tracking + merge)
            user1.name = "alice_updated"
            session.merge(user1)  # merge를 통해 변경사항 반영

            # DELETE
            session.delete(user2)

            session.commit()

        with session_factory.session() as session:
            users = session.query(User).all()
            assert len(users) == 1
            assert users[0].name == "alice_updated"


# =============================================================================
# Query Execution Tests
# =============================================================================


class TestQueryExecution:
    """쿼리 실행 테스트"""

    def test_execute_raw_sql(self, session_factory):
        """raw SQL 실행"""
        with session_factory.session() as session:
            user = create(User, name="alice", age=25)
            session.add(user)
            session.commit()

            result = list(
                session.execute(
                    "SELECT * FROM session_users WHERE age = :age", {"age": 25}
                )
            )
            assert len(result) == 1
            assert result[0]["name"] == "alice"

    def test_execute_returns_iterator(self, session_factory):
        """execute는 iterator 반환"""
        with session_factory.session() as session:
            session.add(create(User, name="alice"))
            session.commit()

            result = session.execute("SELECT * FROM session_users")
            # Iterator 확인
            assert hasattr(result, "__iter__")
            assert hasattr(result, "__next__")

    def test_query_builder_integration(self, session_factory):
        """Query 빌더 통합"""
        with session_factory.session() as session:
            session.add_all(
                [
                    create(User, name="alice", age=25),
                    create(User, name="bob", age=30),
                    create(User, name="charlie", age=25),
                ]
            )
            session.commit()

            users = session.query(User).filter_by(age=25).all()
            assert len(users) == 2

    def test_query_with_order(self, session_factory):
        """정렬 쿼리"""
        with session_factory.session() as session:
            session.add_all(
                [
                    create(User, name="charlie"),
                    create(User, name="alice"),
                    create(User, name="bob"),
                ]
            )
            session.commit()

            # Query 객체의 order_by 사용
            users = session.query(User).order_by(OrderBy("name", "ASC")).all()

            names = [u.name for u in users]
            assert names == ["alice", "bob", "charlie"]
