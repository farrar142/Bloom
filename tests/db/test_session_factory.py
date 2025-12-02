"""SessionFactory 및 Session 테스트

SQLiteBackend를 :memory: 모드로 사용하여 인메모리 DB 테스트를 수행합니다.
"""

import pytest

from bloom.db import (
    Entity,
    IntegerColumn,
    PrimaryKey,
    StringColumn,
    create,
)
from bloom.db.backends import SQLiteBackend
from bloom.db.session import SessionFactory

# =============================================================================
# Test Entities
# =============================================================================


@Entity(table_name="test_users")
class User:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100, default="")
    email = StringColumn(max_length=255, nullable=True)
    age = IntegerColumn(default=0)


@Entity(table_name="test_posts")
class Post:
    id = PrimaryKey[int](auto_increment=True)
    title = StringColumn(max_length=200, default="")
    content = StringColumn(nullable=True, default="")
    user_id = IntegerColumn(nullable=True)


@Entity(table_name="test_tags")
class Tag:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=50, default="")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def backend(request):
    """인메모리 SQLite 백엔드 (각 테스트마다 고유한 DB로 격리)"""
    import uuid

    # 각 테스트마다 고유한 DB 이름 생성
    db_name = f"test_{uuid.uuid4().hex[:8]}"
    return SQLiteBackend(f"file:{db_name}?mode=memory&cache=shared")


@pytest.fixture
def session_factory(backend):
    """SessionFactory 인스턴스"""
    return SessionFactory(backend)


@pytest.fixture
def initialized_factory(session_factory):
    """테이블이 생성된 SessionFactory"""
    session_factory.create_tables(User, Post, Tag)
    return session_factory


# =============================================================================
# SessionFactory Tests
# =============================================================================


class TestSessionFactory:
    """SessionFactory 기본 기능 테스트"""

    def test_create_from_backend(self, backend):
        """Backend로 SessionFactory 생성"""
        factory = SessionFactory(backend)
        assert factory.backend is backend
        assert factory.dialect is not None

    def test_dialect_from_backend(self, backend):
        """Backend의 dialect가 SessionFactory로 전파"""
        factory = SessionFactory(backend)
        assert factory.dialect == backend.dialect

    def test_create_session(self, session_factory):
        """세션 생성"""
        session = session_factory.create()
        assert session is not None
        session.close()

    def test_session_context_manager(self, session_factory):
        """컨텍스트 매니저로 세션 사용"""
        with session_factory.session() as session:
            assert session is not None
            assert not session._closed

    def test_create_tables(self, session_factory):
        """테이블 생성"""
        session_factory.create_tables(User)

        # 테이블이 생성되었는지 확인 (INSERT가 성공하면 테이블 존재)
        with session_factory.session() as session:
            user = create(User, name="test")
            session.add(user)
            # commit은 context manager가 자동으로 수행

    def test_drop_tables(self, initialized_factory):
        """테이블 삭제"""
        initialized_factory.drop_tables(Tag)

        # 삭제된 테이블에 INSERT 시도하면 에러
        with pytest.raises(Exception):
            with initialized_factory.session() as session:
                tag = create(Tag, name="test")
                session.add(tag)


# =============================================================================
# Session CRUD Tests
# =============================================================================


class TestSessionCRUD:
    """Session CRUD 작업 테스트"""

    def test_add_and_commit(self, initialized_factory):
        """엔티티 추가 및 커밋"""
        with initialized_factory.session() as session:
            user = create(User, name="alice", email="alice@example.com", age=25)
            session.add(user)

        # 새 세션에서 조회
        with initialized_factory.session() as session:
            found = session.get(User, 1)
            assert found is not None
            assert found.name == "alice"
            assert found.email == "alice@example.com"
            assert found.age == 25

    def test_add_returns_entity(self, initialized_factory):
        """add()가 엔티티를 반환"""
        with initialized_factory.session() as session:
            user = create(User, name="bob")
            returned = session.add(user)
            assert returned is user

    def test_add_all(self, initialized_factory):
        """여러 엔티티 추가"""
        with initialized_factory.session() as session:
            users = [
                create(User, name="user1"),
                create(User, name="user2"),
                create(User, name="user3"),
            ]
            session.add_all(users)

        with initialized_factory.session() as session:
            assert session.get(User, 1) is not None
            assert session.get(User, 2) is not None
            assert session.get(User, 3) is not None

    def test_auto_increment_pk(self, initialized_factory):
        """auto_increment PK 자동 할당"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            assert user.id is None
            session.add(user)
            session.flush()
            assert user.id is not None
            assert user.id == 1

    def test_sequential_auto_increment(self, initialized_factory):
        """순차적 auto_increment"""
        with initialized_factory.session() as session:
            user1 = create(User, name="user1")
            user2 = create(User, name="user2")
            session.add(user1)
            session.add(user2)
            session.flush()
            # ID가 할당되고 서로 다른 값인지 확인
            assert user1.id is not None
            assert user2.id is not None
            assert user1.id != user2.id

    def test_get_existing_entity(self, initialized_factory):
        """존재하는 엔티티 조회"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

        with initialized_factory.session() as session:
            found = session.get(User, 1)
            assert found is not None
            assert found.name == "alice"

    def test_get_nonexistent_entity(self, initialized_factory):
        """존재하지 않는 엔티티 조회"""
        with initialized_factory.session() as session:
            found = session.get(User, 999)
            assert found is None

    def test_delete_entity(self, initialized_factory):
        """엔티티 삭제"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

        with initialized_factory.session() as session:
            user = session.get(User, 1)
            session.delete(user)

        with initialized_factory.session() as session:
            found = session.get(User, 1)
            assert found is None

    def test_delete_new_entity(self, initialized_factory):
        """새로 추가된 엔티티 삭제 (INSERT 취소)"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            session.delete(user)
            session.flush()
            # flush 후에도 INSERT가 발생하지 않아야 함

        with initialized_factory.session() as session:
            found = session.get(User, 1)
            assert found is None


# =============================================================================
# Session Identity Map Tests
# =============================================================================


class TestSessionIdentityMap:
    """Session Identity Map 테스트"""

    def test_same_pk_returns_same_instance(self, initialized_factory):
        """같은 PK로 조회하면 동일 인스턴스 반환"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

        with initialized_factory.session() as session:
            user1 = session.get(User, 1)
            user2 = session.get(User, 1)
            assert user1 is user2

    def test_identity_map_isolation(self, initialized_factory):
        """세션 간 Identity Map 격리"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

        with initialized_factory.session() as session1:
            user1 = session1.get(User, 1)

        with initialized_factory.session() as session2:
            user2 = session2.get(User, 1)

        # 다른 세션에서 조회한 엔티티는 다른 인스턴스
        assert user1 is not user2
        assert user1.name == user2.name


# =============================================================================
# Session Transaction Tests
# =============================================================================


class TestSessionTransaction:
    """Session 트랜잭션 테스트"""

    def test_commit_persists_changes(self, initialized_factory):
        """commit으로 변경사항 영속화"""
        session = initialized_factory.create()
        try:
            user = create(User, name="alice")
            session.add(user)
            session.commit()
        finally:
            session.close()

        with initialized_factory.session() as session:
            found = session.get(User, 1)
            assert found is not None

    def test_rollback_discards_changes(self, initialized_factory):
        """rollback으로 변경사항 취소"""
        session = initialized_factory.create()
        try:
            user = create(User, name="alice")
            session.add(user)
            session.flush()
            session.rollback()
        finally:
            session.close()

        with initialized_factory.session() as session:
            found = session.get(User, 1)
            assert found is None

    def test_exception_triggers_rollback(self, initialized_factory):
        """예외 발생 시 자동 롤백"""
        try:
            with initialized_factory.session() as session:
                user = create(User, name="alice")
                session.add(user)
                session.flush()
                raise ValueError("test error")
        except ValueError:
            pass

        with initialized_factory.session() as session:
            found = session.get(User, 1)
            assert found is None

    def test_autoflush(self, initialized_factory):
        """autoflush 동작 확인"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)
            # 명시적 flush 없이 query 실행 시 자동 flush
            rows = list(session.execute("SELECT * FROM test_users"))
            assert len(rows) == 1


# =============================================================================
# Session Closed State Tests
# =============================================================================


class TestSessionClosedState:
    """닫힌 세션 테스트"""

    def test_operations_on_closed_session_raise_error(self, initialized_factory):
        """닫힌 세션에서 작업 시 에러"""
        session = initialized_factory.create()
        session.close()

        with pytest.raises(RuntimeError, match="Session is closed"):
            session.add(create(User, name="test"))

        with pytest.raises(RuntimeError, match="Session is closed"):
            session.get(User, 1)

        with pytest.raises(RuntimeError, match="Session is closed"):
            session.delete(create(User, name="test"))

        with pytest.raises(RuntimeError, match="Session is closed"):
            session.commit()

        with pytest.raises(RuntimeError, match="Session is closed"):
            session.rollback()


# =============================================================================
# Session Merge & Refresh Tests
# =============================================================================


class TestSessionMergeRefresh:
    """Session merge와 refresh 테스트"""

    def test_refresh_reloads_from_db(self, initialized_factory):
        """refresh로 DB에서 다시 로드"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

        with initialized_factory.session() as session:
            user = session.get(User, 1)

            # DB에서 직접 업데이트 (다른 연결에서)
            session.execute_update(
                "UPDATE test_users SET name = :name WHERE id = :id",
                {"name": "bob", "id": 1},
            )

            # refresh 전
            assert user.name == "alice"

            # refresh 후
            session.refresh(user)
            assert user.name == "bob"

    def test_merge_detached_entity(self, initialized_factory):
        """detached 엔티티 merge - 기존 엔티티를 반환하고 값이 복사됨"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

        # 새 세션에서 같은 PK의 엔티티 merge
        detached_user = create(User, id=1, name="bob", email="bob@example.com")

        with initialized_factory.session() as session:
            merged = session.merge(detached_user)
            # merge된 객체는 새로운 값을 가짐
            assert merged.name == "bob"
            assert merged.email == "bob@example.com"
            # 명시적으로 dirty로 표시해야 DB에 저장됨
            session._dirty.add(merged)

        with initialized_factory.session() as session:
            found = session.get(User, 1)
            assert found.name == "bob"

    def test_merge_new_entity(self, initialized_factory):
        """새 엔티티 merge (add와 동일)"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            merged = session.merge(user)
            assert merged is user

        with initialized_factory.session() as session:
            found = session.get(User, 1)
            assert found is not None


# =============================================================================
# Session Query Tests
# =============================================================================


class TestSessionQuery:
    """Session 쿼리 테스트"""

    def test_execute_select(self, initialized_factory):
        """execute로 SELECT 실행"""
        with initialized_factory.session() as session:
            session.add(create(User, name="alice"))
            session.add(create(User, name="bob"))

        with initialized_factory.session() as session:
            rows = list(session.execute("SELECT * FROM test_users ORDER BY name"))
            assert len(rows) == 2
            assert rows[0]["name"] == "alice"
            assert rows[1]["name"] == "bob"

    def test_execute_with_params(self, initialized_factory):
        """파라미터가 있는 쿼리 실행"""
        with initialized_factory.session() as session:
            session.add(create(User, name="alice", age=25))
            session.add(create(User, name="bob", age=30))

        with initialized_factory.session() as session:
            rows = list(
                session.execute(
                    "SELECT * FROM test_users WHERE age > :min_age", {"min_age": 26}
                )
            )
            assert len(rows) == 1
            assert rows[0]["name"] == "bob"

    def test_execute_update(self, initialized_factory):
        """execute_update로 UPDATE 실행"""
        with initialized_factory.session() as session:
            session.add(create(User, name="alice"))
            session.add(create(User, name="bob"))

        with initialized_factory.session() as session:
            affected = session.execute_update(
                "UPDATE test_users SET age = :age WHERE name = :name",
                {"age": 30, "name": "alice"},
            )
            assert affected == 1
            session.commit()  # execute_update 후 commit 필요

        with initialized_factory.session() as session:
            # name으로 조회해서 검증
            users = list(
                session.execute(
                    "SELECT * FROM test_users WHERE name = :name", {"name": "alice"}
                )
            )
            assert len(users) == 1
            assert users[0]["age"] == 30

    def test_query_builder(self, initialized_factory):
        """Query 빌더 사용"""
        with initialized_factory.session() as session:
            session.add(create(User, name="alice", age=25))
            session.add(create(User, name="bob", age=30))
            session.add(create(User, name="charlie", age=35))

        with initialized_factory.session() as session:
            query = session.query(User)
            # Query 객체가 반환되는지 확인
            assert query is not None


# =============================================================================
# Multiple Entity Tests
# =============================================================================


class TestMultipleEntities:
    """여러 엔티티 타입 테스트"""

    def test_multiple_tables(self, initialized_factory):
        """여러 테이블 사용"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

        with initialized_factory.session() as session:
            user = session.get(User, 1)
            post = create(Post, title="Hello", content="World", user_id=user.id)
            session.add(post)

        with initialized_factory.session() as session:
            post = session.get(Post, 1)
            assert post is not None
            assert post.title == "Hello"
            assert post.user_id == 1

    def test_cascade_like_operations(self, initialized_factory):
        """연관 데이터 수동 삭제"""
        with initialized_factory.session() as session:
            user = create(User, name="alice")
            session.add(user)

        with initialized_factory.session() as session:
            session.add(create(Post, title="Post 1", user_id=1))
            session.add(create(Post, title="Post 2", user_id=1))

        with initialized_factory.session() as session:
            # 사용자의 포스트 먼저 삭제
            session.execute_update(
                "DELETE FROM test_posts WHERE user_id = :user_id", {"user_id": 1}
            )
            # 사용자 삭제
            user = session.get(User, 1)
            session.delete(user)

        with initialized_factory.session() as session:
            assert session.get(User, 1) is None
            rows = list(session.execute("SELECT * FROM test_posts"))
            assert len(rows) == 0


# =============================================================================
# Backend Integration Tests
# =============================================================================


class TestBackendIntegration:
    """Backend 통합 테스트"""

    def test_backend_accessible_from_factory(self, session_factory, backend):
        """SessionFactory에서 Backend 접근 가능"""
        assert session_factory.backend is backend

    def test_dialect_consistency(self, session_factory):
        """Dialect가 일관되게 전파"""
        with session_factory.session() as session:
            assert session.dialect is session_factory.dialect
            assert session.dialect is session_factory.backend.dialect


# =============================================================================
# Connection Integration Tests
# =============================================================================


class TestConnectionIntegration:
    """Connection 통합 테스트 - backends.Connection이 직접 사용되는지 확인"""

    def test_session_uses_backend_connection(self, initialized_factory):
        """Session이 backends.Connection을 직접 사용"""
        from bloom.db.backends.base import Connection as BackendConnection

        session = initialized_factory.create()
        try:
            # Session의 _connection이 BackendConnection 인스턴스인지 확인
            assert isinstance(session._connection, BackendConnection)
        finally:
            session.close()

    def test_connection_has_dialect(self, initialized_factory):
        """Connection에 dialect가 있음"""
        session = initialized_factory.create()
        try:
            assert session._connection.dialect is not None
            assert session._connection.dialect is session.dialect
        finally:
            session.close()

    def test_connection_execute_returns_connection(self, initialized_factory):
        """Connection.execute()가 Connection을 반환"""
        from bloom.db.backends.sqlite import SQLiteConnection

        session = initialized_factory.create()
        try:
            result = session._connection.execute("SELECT 1")
            assert isinstance(result, SQLiteConnection)
        finally:
            session.close()

    def test_connection_fetchall_returns_dicts(self, initialized_factory):
        """Connection.fetchall()이 dict 리스트를 반환"""
        with initialized_factory.session() as session:
            session.add(create(User, name="alice"))

        with initialized_factory.session() as session:
            result = session._connection.execute("SELECT * FROM test_users")
            rows = result.fetchall()
            assert isinstance(rows, list)
            assert len(rows) == 1
            assert isinstance(rows[0], dict)
            assert rows[0]["name"] == "alice"
