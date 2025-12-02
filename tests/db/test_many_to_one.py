"""ManyToOne relationship tests"""

import pytest
from bloom.db import (
    Entity,
    PrimaryKey,
    StringColumn,
    ManyToOne,
    OneToMany,
    FetchType,
    create,
    SessionFactory,
)
from bloom.db.backends import SQLiteBackend


# =============================================================================
# 테스트용 엔티티
# =============================================================================


@Entity(table_name="users")
class User:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(max_length=100)
    posts = OneToMany("Post", foreign_key="user_id")


@Entity(table_name="posts")
class Post:
    id = PrimaryKey[int](auto_increment=True)
    title = StringColumn(max_length=200)
    user = ManyToOne(User)  # FK: user_id 자동 생성


@Entity(table_name="comments")
class Comment:
    id = PrimaryKey[int](auto_increment=True)
    content = StringColumn(max_length=500)
    post = ManyToOne("Post", foreign_key="post_id")  # 명시적 FK


# =============================================================================
# ManyToOne 디스크립터 테스트
# =============================================================================


class TestManyToOneDescriptor:
    """ManyToOne 디스크립터 기본 테스트"""

    def test_class_level_access_returns_field_expression(self):
        """클래스 레벨 접근 시 FieldExpression 반환 (쿼리용)"""
        from bloom.db.columns import FieldExpression
        
        # 클래스 레벨 접근은 FieldExpression 반환 (쿼리에 사용)
        assert isinstance(Post.user, FieldExpression)
        assert Post.user.name == "user_id"  # FK 컬럼명
        
        # 디스크립터 자체에 접근하려면 __dict__ 사용
        assert isinstance(Post.__dict__["user"], ManyToOne)

    def test_db_name_auto_inference(self):
        """FK 컬럼명 자동 추론"""
        descriptor = Post.__dict__["user"]
        # user + id → user_id
        assert descriptor.db_name == "user_id"

    def test_db_name_explicit(self):
        """명시적 FK 컬럼명"""
        descriptor = Comment.__dict__["post"]
        assert descriptor.db_name == "post_id"

    def test_registered_in_columns(self):
        """__bloom_columns__에 등록됨"""
        assert "user" in Post.__bloom_columns__
        assert isinstance(Post.__bloom_columns__["user"], ManyToOne)

    def test_registered_in_relations(self):
        """__bloom_relations__에 등록됨"""
        assert hasattr(Post, "__bloom_relations__")
        assert "user" in Post.__bloom_relations__

    def test_references_table(self):
        """참조 테이블명"""
        descriptor = Post.__dict__["user"]
        assert descriptor.references_table == "users"

    def test_references_column(self):
        """참조 컬럼명"""
        descriptor = Post.__dict__["user"]
        assert descriptor.references_column == "id"

    def test_constraint_definition(self):
        """FK 제약조건 DDL"""
        descriptor = Post.__dict__["user"]
        constraint = descriptor.get_constraint_definition()
        assert "FOREIGN KEY (user_id)" in constraint
        assert "REFERENCES users(id)" in constraint


class TestManyToOneGetSet:
    """ManyToOne get/set 테스트"""

    def test_set_relation_object(self):
        """관계 객체 설정"""
        user = create(User, id=1, name="Alice")
        post = create(Post, title="Hello")

        post.user = user

        # FK 값이 설정됨
        fk_value = Post.__dict__["user"].get_fk_value(post)
        assert fk_value == 1

    def test_set_none_clears_fk(self):
        """None 설정 시 FK도 None"""
        user = create(User, id=1, name="Alice")
        post = create(Post, title="Hello")

        post.user = user
        post.user = None

        fk_value = Post.__dict__["user"].get_fk_value(post)
        assert fk_value is None

    def test_get_without_session_raises_error(self):
        """Session 없이 lazy 접근하면 에러"""
        post = create(Post, id=1, title="Hello")
        Post.__dict__["user"].set_fk_value(post, 1)
        post.__bloom_tracker__.mark_persisted()

        with pytest.raises(ValueError, match="has no bound session"):
            _ = post.user

    def test_get_without_fk_returns_none(self):
        """FK 없으면 None 반환"""
        post = create(Post, title="Hello")
        assert post.user is None

    def test_type_check_on_set(self):
        """잘못된 타입 설정 시 에러"""
        post = create(Post, title="Hello")

        with pytest.raises(TypeError, match="Expected User"):
            post.user = "not a user"


class TestManyToOneWithSession:
    """실제 Session과 함께 ManyToOne 테스트"""

    @pytest.fixture
    def session(self):
        """인메모리 SQLite 세션"""
        backend = SQLiteBackend(":memory:")
        factory = SessionFactory(backend)

        with factory.session() as session:
            session._connection.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100)
                )
            """
            )
            session._connection.execute(
                """
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title VARCHAR(200),
                    user_id INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """
            )
            yield session

    def test_lazy_loading(self, session):
        """Lazy 로딩 테스트"""
        # 데이터 추가
        session._connection.execute(
            "INSERT INTO users (name) VALUES (:name)", {"name": "Alice"}
        )
        session._connection.execute(
            "INSERT INTO posts (title, user_id) VALUES (:title, :user_id)",
            {"title": "Hello", "user_id": 1},
        )
        session.commit()

        # Post 조회
        post = session.query(Post).filter(Post.id == 1).first()
        assert post is not None

        # User lazy 로딩
        user = post.user
        assert user is not None
        assert user.name == "Alice"

    def test_set_relation_adds_to_session(self, session):
        """관계 설정 시 세션에 추가"""
        # User 저장
        session._connection.execute(
            "INSERT INTO users (name) VALUES (:name)", {"name": "Bob"}
        )
        session.commit()

        user = session.query(User).filter(User.id == 1).first()

        # 새 Post 생성 및 관계 설정
        post = create(Post, title="New Post")
        post.user = user  # 이 시점에 session.add(post) 호출됨

        # 세션에 추가됨
        assert post in session._new

        # FK 값 설정됨
        fk_value = Post.__dict__["user"].get_fk_value(post)
        assert fk_value == 1

    def test_save_with_relation(self, session):
        """관계와 함께 저장"""
        # User 저장
        session._connection.execute(
            "INSERT INTO users (name) VALUES (:name)", {"name": "Charlie"}
        )
        session.commit()

        user = session.query(User).filter(User.id == 1).first()

        # 새 Post 생성 및 저장
        post = create(Post, title="Charlie's Post")
        post.user = user
        session.flush()

        # DB에서 확인
        result = session._connection.execute(
            "SELECT user_id FROM posts WHERE id = :id", {"id": post.id}
        ).fetchone()
        assert result["user_id"] == 1

    def test_caching(self, session):
        """캐싱 동작 확인"""
        session._connection.execute(
            "INSERT INTO users (name) VALUES (:name)", {"name": "Diana"}
        )
        session._connection.execute(
            "INSERT INTO posts (title, user_id) VALUES (:title, :user_id)",
            {"title": "Cached Post", "user_id": 1},
        )
        session.commit()

        post = session.query(Post).filter(Post.id == 1).first()

        # 첫 접근
        user1 = post.user
        # 두 번째 접근 - 캐시 반환
        user2 = post.user

        assert user1 is user2


class TestManyToOneIntegration:
    """ManyToOne과 OneToMany 통합 테스트"""

    @pytest.fixture
    def session(self):
        """인메모리 SQLite 세션"""
        backend = SQLiteBackend(":memory:")
        factory = SessionFactory(backend)

        with factory.session() as session:
            session._connection.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100)
                )
            """
            )
            session._connection.execute(
                """
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title VARCHAR(200),
                    user_id INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """
            )
            yield session

    def test_bidirectional_relationship(self, session):
        """양방향 관계 테스트"""
        # User 생성
        session._connection.execute(
            "INSERT INTO users (name) VALUES (:name)", {"name": "Eve"}
        )
        session.commit()

        user = session.query(User).filter(User.id == 1).first()

        # Post 생성 via OneToMany
        post1 = create(Post, title="Post 1")
        user.posts.append(post1)

        # Post 생성 via ManyToOne
        post2 = create(Post, title="Post 2")
        post2.user = user

        session.flush()

        # 양쪽 모두 FK가 설정됨
        assert Post.__dict__["user"].get_fk_value(post1) == 1
        assert Post.__dict__["user"].get_fk_value(post2) == 1

    def test_navigate_both_directions(self, session):
        """양방향 탐색"""
        session._connection.execute(
            "INSERT INTO users (name) VALUES (:name)", {"name": "Frank"}
        )
        session._connection.execute(
            "INSERT INTO posts (title, user_id) VALUES (:title, :user_id)",
            {"title": "Frank's Post", "user_id": 1},
        )
        session.commit()

        # User → Posts
        user = session.query(User).filter(User.id == 1).first()
        posts = user.posts
        assert len(posts) == 1

        # Post → User
        post = posts[0]
        loaded_user = post.user
        assert loaded_user.name == "Frank"


class TestManyToOneWithTransaction:
    """트랜잭션에서 ManyToOne 테스트"""

    @pytest.fixture
    def factory(self):
        """세션 팩토리"""
        backend = SQLiteBackend(":memory:")
        return SessionFactory(backend)

    def test_auto_save_on_transaction_exit(self, factory):
        """트랜잭션 종료 시 자동 저장"""
        # 테이블 생성
        with factory.session() as session:
            session._connection.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(100)
                )
            """
            )
            session._connection.execute(
                """
                CREATE TABLE posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title VARCHAR(200),
                    user_id INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """
            )
            session._connection.execute(
                "INSERT INTO users (name) VALUES (:name)", {"name": "Grace"}
            )

        # 새 세션에서 관계 설정
        with factory.session() as session:
            user = session.query(User).filter(User.id == 1).first()

            post = create(Post, title="Grace's Post")
            post.user = user
            # 트랜잭션 종료 시 자동 커밋

        # 새 세션에서 확인
        with factory.session() as session:
            post = session.query(Post).filter(Post.id == 1).first()
            assert post is not None
            assert post.title == "Grace's Post"

            fk_value = Post.__dict__["user"].get_fk_value(post)
            assert fk_value == 1
