"""TrackedList와 세션 통합 테스트 - call_scope 시나리오 재현"""

import pytest
from bloom.db.entity import Entity
from bloom.db.columns import (
    PrimaryKey,
    StringColumn,
    ManyToOne,
    OneToMany,
    TrackedList,
    IntegerColumn,
)
from bloom.db.session import Session, SessionFactory
from bloom.db.backends.sqlite import SQLiteBackend


# =============================================================================
# 테스트용 엔티티 정의
# =============================================================================


@Entity
class User:
    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn()
    email = StringColumn(nullable=True)
    posts = OneToMany["Post"]("Post", foreign_key="user_id")


@Entity
class Post:
    id = PrimaryKey[int](auto_increment=True)
    title = StringColumn()
    user_id = IntegerColumn(nullable=True)  # FK 컬럼


# =============================================================================
# 테스트 케이스
# =============================================================================


class TestTrackedListWithSession:
    """사용자의 call_scope 시나리오 재현"""

    @pytest.fixture
    def factory(self):
        """세션 팩토리"""
        backend = SQLiteBackend(":memory:")
        return SessionFactory(backend)

    @pytest.fixture
    def setup_tables(self, factory):
        """테이블 생성"""
        with factory.session() as session:
            session._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT
                )
                """
            )
            session._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS post (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    user_id INTEGER REFERENCES user(id)
                )
                """
            )
            session.commit()
        return factory

    def test_append_without_save_does_not_persist(self, setup_tables):
        """append만 하고 save 안하면 저장 안됨 - 이게 문제의 원인"""
        factory = setup_tables

        # Scope 1: 빈 상태 확인
        with factory.session() as session:
            users = session.query(User).all()
            assert len(users) == 0
            print(f"Scope 1: users = {users}")

        # Scope 2: User 생성하고 Post append - save 안함!
        with factory.session() as session:
            u = User()
            u.name = "Test User"
            u.email = "test@example.com"

            p = Post()
            p.title = "First Post"

            # 여기가 문제!
            # u.posts.append(p) 하면:
            # 1. p.user_id = u.id 설정 시도 (하지만 u.id는 아직 None!)
            # 2. session.add(p) 호출 (하지만 u는 아직 저장 안됨)
            u.posts.append(p)

            # User를 save하지 않았음!
            # session.add(u)  # 이게 빠졌음
            # session.flush() 또는 commit() 도 없음

        # Scope 3: 확인 - 당연히 빈 상태
        with factory.session() as session:
            users = session.query(User).all()
            posts = session.query(Post).all()
            print(f"Scope 3: users = {users}, posts = {posts}")
            assert len(users) == 0  # User save 안했으니 당연히 0
            assert len(posts) == 0  # Post도 당연히 0

    def test_proper_save_flow(self, setup_tables):
        """올바른 저장 플로우"""
        factory = setup_tables

        # Scope 2: 올바르게 저장
        with factory.session() as session:
            u = User()
            u.name = "Test User"
            u.email = "test@example.com"
            session.add(u)  # User 먼저 추가
            session.flush()  # User ID 할당받음

            p = Post()
            p.title = "First Post"
            u.posts.append(p)  # 이제 u.id가 있으므로 p.user_id 설정됨

            session.commit()

        # Scope 3: 확인
        with factory.session() as session:
            users = session.query(User).all()
            posts = session.query(Post).all()
            print(f"users = {users}, posts = {posts}")
            assert len(users) == 1
            assert len(posts) == 1
            assert posts[0].user_id == users[0].id

    def test_what_happens_to_tracked_list_on_new_entity(self, setup_tables):
        """새 엔티티의 TrackedList 상태 확인"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Test"

            # 새 엔티티의 posts는 어떤 상태?
            print(f"u.posts type: {type(u.posts)}")
            print(f"u.posts: {u.posts}")

            # TrackedList가 세션에 바인딩 안되어 있을 수 있음
            if isinstance(u.posts, TrackedList):
                print(f"u.posts._session: {u.posts._session}")
                print(f"u.posts._owner: {u.posts._owner}")
                print(f"u.posts._fk_field_name: {u.posts._fk_field_name}")

            p = Post()
            p.title = "Test Post"
            u.posts.append(p)

            # p의 user_id는?
            print(f"p.user_id after append: {p.user_id}")

            # p가 세션에 추가됐나?
            print(
                f"p in session._identity_map: {p in session._identity_map.values() if hasattr(session, '_identity_map') else 'N/A'}"
            )

    def test_user_not_added_to_session(self, setup_tables):
        """User가 세션에 추가되지 않으면 posts도 저장 안됨"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Test"

            # User를 세션에 추가 안함
            # session.add(u)

            p = Post()
            p.title = "Test"
            u.posts.append(p)

            # p가 세션에 추가됐는지 확인
            # TrackedList가 세션 없이 동작하면 p도 세션에 없음
            print(
                f"Session pending: {len(session._pending) if hasattr(session, '_pending') else 'N/A'}"
            )

            session.commit()

        with factory.session() as session:
            users = session.query(User).all()
            posts = session.query(Post).all()
            assert len(users) == 0
            assert len(posts) == 0

    def test_append_with_explicit_session_add(self, setup_tables):
        """명시적으로 session.add 하는 경우"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Test"
            u.email = "test@example.com"

            p = Post()
            p.title = "Test"

            # 방법 1: 둘 다 명시적으로 추가
            session.add(u)
            session.add(p)

            # FK 수동 설정 (아직 u.id가 None일 수 있음)
            session.flush()  # ID 할당
            p.user_id = u.id

            session.commit()

        with factory.session() as session:
            users = session.query(User).all()
            posts = session.query(Post).all()
            assert len(users) == 1
            assert len(posts) == 1


class TestTrackedListSessionBinding:
    """TrackedList의 세션 바인딩 테스트"""

    @pytest.fixture
    def factory(self):
        backend = SQLiteBackend(":memory:")
        return SessionFactory(backend)

    @pytest.fixture
    def setup_tables(self, factory):
        with factory.session() as session:
            session._connection.execute(
                "CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT, email TEXT)"
            )
            session._connection.execute(
                "CREATE TABLE post (id INTEGER PRIMARY KEY, title TEXT, user_id INTEGER)"
            )
            session.commit()
        return factory

    def test_new_entity_tracked_list_has_no_session(self, setup_tables):
        """새로 생성한 엔티티의 TrackedList는 세션이 없음"""
        u = User()
        u.name = "Test"

        # OneToMany가 반환하는 TrackedList 확인
        posts = u.posts

        if isinstance(posts, TrackedList):
            # 세션이 없을 것임
            assert posts._session is None, "새 엔티티의 TrackedList는 세션이 없어야 함"

    def test_loaded_entity_tracked_list_has_session(self, setup_tables):
        """DB에서 로드한 엔티티의 TrackedList는 세션이 있어야 함"""
        factory = setup_tables

        # User 생성
        with factory.session() as session:
            session._connection.execute(
                "INSERT INTO user (name, email) VALUES ('Test', 'test@example.com')"
            )
            session.commit()

        # User 로드
        with factory.session() as session:
            u = session.query(User).first()
            posts = u.posts

            if isinstance(posts, TrackedList):
                # 세션이 있어야 함
                assert (
                    posts._session is not None
                ), "로드된 엔티티의 TrackedList는 세션이 있어야 함"
                assert posts._session is session

    def test_session_add_binds_tracked_list(self, setup_tables):
        """session.add() 하면 TrackedList에도 세션 바인딩되어야 함"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Test"

            # add 전 - 먼저 posts에 접근해서 TrackedList 생성
            posts_before = u.posts
            if isinstance(posts_before, TrackedList):
                session_before = posts_before._session
                print(f"Before add: session = {session_before}")
                assert session_before is None, "add 전에는 세션이 없어야 함"

            session.add(u)

            # add 후 - 같은 TrackedList 인스턴스에 세션이 바인딩되어야 함
            posts_after = u.posts
            if isinstance(posts_after, TrackedList):
                session_after = posts_after._session
                print(f"After add: session = {session_after}")
                assert session_after is session, "add 후 TrackedList에 세션이 바인딩되어야 함"


class TestIdealWorkflow:
    """사용자가 원하는 이상적인 워크플로우 테스트"""

    @pytest.fixture
    def factory(self):
        backend = SQLiteBackend(":memory:")
        return SessionFactory(backend)

    @pytest.fixture
    def setup_tables(self, factory):
        with factory.session() as session:
            session._connection.execute(
                "CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT, email TEXT)"
            )
            session._connection.execute(
                "CREATE TABLE post (id INTEGER PRIMARY KEY, title TEXT, user_id INTEGER)"
            )
            session.commit()
        return factory

    def test_ideal_append_workflow(self, setup_tables):
        """이상적인 append 워크플로우
        
        사용자가 원하는 동작:
        1. User 생성 + session.add()
        2. Post 생성 + user.posts.append()
        3. commit 하면 둘 다 저장되고 FK도 설정됨
        """
        factory = setup_tables

        with factory.session() as session:
            # 1. User 생성 및 세션에 추가
            u = User()
            u.name = "Test User"
            u.email = "test@example.com"
            session.add(u)

            # 2. Post 생성 및 append
            p = Post()
            p.title = "First Post"
            u.posts.append(p)

            # 이 시점에서:
            # - p는 세션에 추가되어야 함
            # - p.user_id는 아직 None (u.id가 아직 None이므로)
            print(f"Before commit: u.id={u.id}, p.user_id={p.user_id}")
            print(f"p in session._new: {p in session._new}")

            # 3. commit - 이 때 FK가 동기화되어야 함
            session.commit()

            print(f"After commit: u.id={u.id}, p.user_id={p.user_id}")

        # 4. 검증
        with factory.session() as session:
            users = session.query(User).all()
            posts = session.query(Post).all()
            
            print(f"Loaded: users={users}, posts={posts}")
            
            assert len(users) == 1, "User가 저장되어야 함"
            assert len(posts) == 1, "Post가 저장되어야 함"
            assert posts[0].user_id == users[0].id, "FK가 설정되어야 함"

    def test_append_before_add_should_fail_or_warn(self, setup_tables):
        """session.add() 전에 append하면 저장 안됨 (경고 필요?)"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Test"
            
            p = Post()
            p.title = "Test"
            
            # session.add(u) 안함!
            u.posts.append(p)
            
            # p가 세션에 없으므로 저장 안됨
            session.commit()

        with factory.session() as session:
            users = session.query(User).all()
            posts = session.query(Post).all()
            
            # 둘 다 저장 안됨
            assert len(users) == 0
            assert len(posts) == 0
