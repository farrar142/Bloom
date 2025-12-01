"""Repository 패턴 테스트"""

import pytest
from typing import Optional

from bloom.db import (
    Entity,
    PrimaryKey,
    StringColumn,
    IntegerColumn,
    create,
)
from bloom.db.session import SessionFactory
from bloom.db.repository import CrudRepository, RepositoryFactory, RepositoryProvider
from bloom.db.expressions import Condition, OrderBy
from bloom.db.backends.sqlite import SQLiteBackend


# =============================================================================
# Test Entities
# =============================================================================


@Entity(table_name="repo_users")
class User:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100, default="")
    email = StringColumn(max_length=255, nullable=True)
    age = IntegerColumn(nullable=True)
    status = StringColumn(max_length=50, default="active")


@Entity(table_name="repo_posts")
class Post:
    id = PrimaryKey[int](auto_increment=True)
    title = StringColumn(max_length=200, default="")
    content = StringColumn(nullable=True, default="")
    author_id = IntegerColumn(nullable=True)


# =============================================================================
# Custom Repository
# =============================================================================


class UserRepository(CrudRepository[User, int]):
    """사용자 정의 리포지토리"""

    def find_by_email(self, email: str) -> User | None:
        return self.find_one_by(email=email)

    def find_active_users(self) -> list[User]:
        return self.query().filter(Condition("status", "=", "active")).all()

    def find_adults(self) -> list[User]:
        return self.query().filter(Condition("age", ">=", 18)).all()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def backend(tmp_path):
    """임시 파일 SQLite 백엔드"""
    db_path = tmp_path / "repo_test.db"
    return SQLiteBackend(str(db_path))


@pytest.fixture
def session_factory(backend):
    """세션 팩토리"""
    factory = SessionFactory(backend)
    factory.create_tables(User, Post)
    return factory


# =============================================================================
# CrudRepository Basic Tests
# =============================================================================


class TestCrudRepositoryBasic:
    """CrudRepository 기본 테스트"""

    def test_create_repository(self, session_factory):
        """리포지토리 생성"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            assert repo.entity_class == User
            assert repo.session is session

    def test_entity_class_property(self, session_factory):
        """entity_class 프로퍼티"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)
            assert repo.entity_class == User

    def test_session_property(self, session_factory):
        """session 프로퍼티"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)
            assert repo.session is session

    def test_non_entity_raises_error(self, session_factory):
        """Entity가 아닌 클래스는 에러"""

        class NotAnEntity:
            pass

        with session_factory.session() as session:
            with pytest.raises(ValueError, match="not an Entity"):
                CrudRepository(NotAnEntity, session)


# =============================================================================
# CRUD Operations Tests
# =============================================================================


class TestCrudOperations:
    """CRUD 연산 테스트"""

    def test_save_new_entity(self, session_factory):
        """새 엔티티 저장"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            user = create(User, name="alice")
            saved = repo.save(user)

            assert saved.id is not None
            assert saved.name == "alice"

    def test_save_existing_entity(self, session_factory):
        """기존 엔티티 저장 (UPDATE)"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            user = create(User, name="alice")
            repo.save(user)
            session.commit()

            pk = user.id

        # 새 세션에서 조회 후 수정
        with session_factory.session() as session:
            repo = CrudRepository(User, session)
            user = repo.find_by_id(pk)
            assert user is not None
            
            user.name = "alice_updated"
            repo.save(user)  # save는 merge 후 flush
            session.commit()

        with session_factory.session() as session:
            repo = CrudRepository(User, session)
            found = repo.find_by_id(pk)

            assert found is not None
            assert found.name == "alice_updated"

    def test_save_all(self, session_factory):
        """여러 엔티티 저장"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            users = [create(User, name=f"user{i}") for i in range(3)]
            saved = repo.save_all(users)

            assert len(saved) == 3
            assert all(u.id is not None for u in saved)

    def test_find_by_id(self, session_factory):
        """ID로 조회"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            user = create(User, name="alice")
            repo.save(user)
            session.commit()

            found = repo.find_by_id(user.id)

            assert found is not None
            assert found.name == "alice"

    def test_find_by_id_not_found(self, session_factory):
        """ID로 조회 - 없음"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            found = repo.find_by_id(999)

            assert found is None

    def test_find_all(self, session_factory):
        """전체 조회"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            for i in range(5):
                repo.save(create(User, name=f"user{i}"))
            session.commit()

            users = repo.find_all()

            assert len(users) == 5

    def test_find_all_by_id(self, session_factory):
        """여러 ID로 조회"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            users = [create(User, name=f"user{i}") for i in range(5)]
            repo.save_all(users)
            session.commit()

            ids = [users[0].id, users[2].id, users[4].id]
            found = repo.find_all_by_id(ids)

            assert len(found) == 3

    def test_find_all_by_id_empty(self, session_factory):
        """빈 ID 목록"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            found = repo.find_all_by_id([])

            assert found == []

    def test_delete(self, session_factory):
        """엔티티 삭제"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            user = create(User, name="alice")
            repo.save(user)
            session.commit()
            pk = user.id

            repo.delete(user)
            session.commit()

        with session_factory.session() as session:
            repo = CrudRepository(User, session)
            found = repo.find_by_id(pk)

            assert found is None

    def test_delete_by_id(self, session_factory):
        """ID로 삭제"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            user = create(User, name="alice")
            repo.save(user)
            session.commit()
            pk = user.id

            result = repo.delete_by_id(pk)
            session.commit()

            assert result is True

        with session_factory.session() as session:
            repo = CrudRepository(User, session)
            found = repo.find_by_id(pk)

            assert found is None

    def test_delete_by_id_not_found(self, session_factory):
        """없는 ID 삭제"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            result = repo.delete_by_id(999)

            assert result is False

    def test_delete_all_entities(self, session_factory):
        """여러 엔티티 삭제"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            users = [create(User, name=f"user{i}") for i in range(3)]
            repo.save_all(users)
            session.commit()

            repo.delete_all(users[:2])  # 처음 2개 삭제
            session.commit()

            remaining = repo.find_all()
            assert len(remaining) == 1

    def test_delete_all_by_id(self, session_factory):
        """여러 ID로 삭제"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            users = [create(User, name=f"user{i}") for i in range(5)]
            repo.save_all(users)
            session.commit()

            ids = [users[0].id, users[2].id]
            repo.delete_all_by_id(ids)
            session.commit()

            remaining = repo.find_all()
            assert len(remaining) == 3


# =============================================================================
# Query Methods Tests
# =============================================================================


class TestQueryMethods:
    """쿼리 메서드 테스트"""

    def test_exists_by_id(self, session_factory):
        """ID 존재 여부"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            user = create(User, name="alice")
            repo.save(user)
            session.commit()

            assert repo.exists_by_id(user.id) is True
            assert repo.exists_by_id(999) is False

    def test_count(self, session_factory):
        """개수 조회"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            assert repo.count() == 0

            for i in range(3):
                repo.save(create(User, name=f"user{i}"))
            session.commit()

            assert repo.count() == 3

    def test_find_by(self, session_factory):
        """필드 조건 조회"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            repo.save_all([
                create(User, name="alice", status="active"),
                create(User, name="bob", status="inactive"),
                create(User, name="charlie", status="active"),
            ])
            session.commit()

            active_users = repo.find_by(status="active")

            assert len(active_users) == 2

    def test_find_one_by(self, session_factory):
        """단일 조건 조회"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            repo.save(create(User, name="alice", email="alice@example.com"))
            session.commit()

            found = repo.find_one_by(email="alice@example.com")

            assert found is not None
            assert found.name == "alice"

    def test_find_one_by_not_found(self, session_factory):
        """단일 조건 조회 - 없음"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            found = repo.find_one_by(email="nonexistent@example.com")

            assert found is None

    def test_find_all_ordered(self, session_factory):
        """정렬 조회"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            repo.save_all([
                create(User, name="charlie"),
                create(User, name="alice"),
                create(User, name="bob"),
            ])
            session.commit()

            users = repo.find_all_ordered(OrderBy("name", "ASC"))
            names = [u.name for u in users]

            assert names == ["alice", "bob", "charlie"]

    def test_find_page(self, session_factory):
        """페이지네이션"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            for i in range(10):
                repo.save(create(User, name=f"user{i:02d}"))
            session.commit()

            page0 = repo.find_page(page=0, size=3)
            page1 = repo.find_page(page=1, size=3)
            page2 = repo.find_page(page=2, size=3)

            assert len(page0) == 3
            assert len(page1) == 3
            assert len(page2) == 3

    def test_find_slice(self, session_factory):
        """슬라이스 조회"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            for i in range(10):
                repo.save(create(User, name=f"user{i}"))
            session.commit()

            users = repo.find_slice(offset=2, limit=5)

            assert len(users) == 5


# =============================================================================
# Query Builder Integration Tests
# =============================================================================


class TestQueryBuilderIntegration:
    """Query Builder 통합 테스트"""

    def test_query_with_filter(self, session_factory):
        """필터 쿼리"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            repo.save_all([
                create(User, name="alice", age=25),
                create(User, name="bob", age=17),
                create(User, name="charlie", age=30),
            ])
            session.commit()

            adults = repo.query().filter(Condition("age", ">=", 18)).all()

            assert len(adults) == 2

    def test_query_with_multiple_filters(self, session_factory):
        """다중 필터"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            repo.save_all([
                create(User, name="alice", age=25, status="active"),
                create(User, name="bob", age=30, status="inactive"),
                create(User, name="charlie", age=35, status="active"),
            ])
            session.commit()

            result = (
                repo.query()
                .filter(Condition("age", ">=", 25))
                .filter(Condition("status", "=", "active"))
                .all()
            )

            assert len(result) == 2

    def test_query_with_order_and_limit(self, session_factory):
        """정렬과 제한"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            for i in range(10):
                repo.save(create(User, name=f"user{i}", age=20 + i))
            session.commit()

            result = (
                repo.query()
                .order_by(OrderBy("age", "DESC"))
                .limit(3)
                .all()
            )

            assert len(result) == 3
            assert result[0].age == 29  # 가장 나이 많은


# =============================================================================
# Iterator Tests
# =============================================================================


class TestRepositoryIterator:
    """이터레이터 테스트"""

    def test_iterate_repository(self, session_factory):
        """리포지토리 순회"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            repo.save_all([create(User, name=f"user{i}") for i in range(3)])
            session.commit()

            names = [u.name for u in repo]

            assert len(names) == 3

    def test_len_repository(self, session_factory):
        """리포지토리 길이"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            repo.save_all([create(User, name=f"user{i}") for i in range(5)])
            session.commit()

            assert len(repo) == 5


# =============================================================================
# Custom Repository Tests
# =============================================================================


class TestCustomRepository:
    """커스텀 리포지토리 테스트"""

    def test_custom_find_by_email(self, session_factory):
        """커스텀 메서드 - 이메일로 찾기"""
        with session_factory.session() as session:
            repo = UserRepository(User, session)

            repo.save(create(User, name="alice", email="alice@example.com"))
            session.commit()

            found = repo.find_by_email("alice@example.com")

            assert found is not None
            assert found.name == "alice"

    def test_custom_find_active_users(self, session_factory):
        """커스텀 메서드 - 활성 사용자 찾기"""
        with session_factory.session() as session:
            repo = UserRepository(User, session)

            repo.save_all([
                create(User, name="alice", status="active"),
                create(User, name="bob", status="inactive"),
                create(User, name="charlie", status="active"),
            ])
            session.commit()

            active = repo.find_active_users()

            assert len(active) == 2

    def test_custom_find_adults(self, session_factory):
        """커스텀 메서드 - 성인 찾기"""
        with session_factory.session() as session:
            repo = UserRepository(User, session)

            repo.save_all([
                create(User, name="alice", age=25),
                create(User, name="bob", age=15),
                create(User, name="charlie", age=30),
            ])
            session.commit()

            adults = repo.find_adults()

            assert len(adults) == 2


# =============================================================================
# Repository Factory Tests
# =============================================================================


class TestRepositoryFactory:
    """RepositoryFactory 테스트"""

    def test_create_repository(self, session_factory):
        """리포지토리 생성"""
        factory = RepositoryFactory(session_factory)

        with session_factory.session() as session:
            repo = factory.create(User, session)

            assert isinstance(repo, CrudRepository)
            assert repo.entity_class == User

    def test_for_session(self, session_factory):
        """세션 바인딩 프로바이더"""
        factory = RepositoryFactory(session_factory)

        with session_factory.session() as session:
            provider = factory.for_session(session)

            assert isinstance(provider, RepositoryProvider)


# =============================================================================
# Repository Provider Tests
# =============================================================================


class TestRepositoryProvider:
    """RepositoryProvider 테스트"""

    def test_get_repository(self, session_factory):
        """리포지토리 가져오기"""
        factory = RepositoryFactory(session_factory)

        with session_factory.session() as session:
            provider = factory.for_session(session)
            repo = provider.get(User)

            assert isinstance(repo, CrudRepository)
            assert repo.entity_class == User

    def test_repository_caching(self, session_factory):
        """리포지토리 캐싱"""
        factory = RepositoryFactory(session_factory)

        with session_factory.session() as session:
            provider = factory.for_session(session)

            repo1 = provider.get(User)
            repo2 = provider.get(User)

            assert repo1 is repo2  # 같은 인스턴스

    def test_getitem_syntax(self, session_factory):
        """[] 문법"""
        factory = RepositoryFactory(session_factory)

        with session_factory.session() as session:
            provider = factory.for_session(session)
            repo = provider[User]

            assert isinstance(repo, CrudRepository)

    def test_multiple_entity_types(self, session_factory):
        """여러 엔티티 타입"""
        factory = RepositoryFactory(session_factory)

        with session_factory.session() as session:
            provider = factory.for_session(session)

            user_repo = provider[User]
            post_repo = provider[Post]

            assert user_repo.entity_class == User
            assert post_repo.entity_class == Post
            assert user_repo is not post_repo


# =============================================================================
# Transaction Integration Tests
# =============================================================================


class TestRepositoryTransaction:
    """리포지토리 트랜잭션 테스트"""

    def test_repository_uses_session_transaction(self, session_factory):
        """리포지토리는 세션 트랜잭션 사용"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            user = create(User, name="alice")
            repo.save(user)
            session.commit()

        # 커밋 후 보임
        with session_factory.session() as session:
            repo = CrudRepository(User, session)
            found = repo.find_by_id(user.id)
            assert found is not None

    def test_rollback_affects_repository(self, session_factory):
        """롤백 시 리포지토리 변경도 취소"""
        with session_factory.session() as session:
            repo = CrudRepository(User, session)

            user = create(User, name="alice")
            repo.save(user)
            session.flush()
            pk = user.id

            session.rollback()

        # 롤백되어 없음
        with session_factory.session() as session:
            repo = CrudRepository(User, session)
            found = repo.find_by_id(pk)
            assert found is None
