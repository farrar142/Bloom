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
                assert (
                    session_after is session
                ), "add 후 TrackedList에 세션이 바인딩되어야 함"


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
        """session.add(u) 전에 append해도 cascade로 저장됨"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Test"

            p = Post()
            p.title = "Test"

            # append 먼저 (session.add(u) 전)
            u.posts.append(p)

            # 이제 session.add(u)하면 p도 cascade로 추가됨
            session.add(u)
            session.commit()

        with factory.session() as session:
            users = session.query(User).all()
            posts = session.query(Post).all()

            # 둘 다 저장됨!
            assert len(users) == 1
            assert len(posts) == 1


class TestCascadeAddSync:
    """동기 세션의 cascade add 테스트"""

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

    def test_append_before_session_add_cascades_child(self, setup_tables):
        """append 먼저 → session.add(parent) → child도 cascade로 저장됨"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Alice"

            p = Post()
            p.title = "Hello World"

            # append 먼저 (아직 세션에 안 추가됨)
            u.posts.append(p)

            # 이 시점에서 둘 다 세션에 없음
            assert u not in session._new
            assert p not in session._new

            # session.add(u) → p도 cascade로 추가됨
            session.add(u)

            # 이제 둘 다 세션에 있음
            assert u in session._new
            assert p in session._new

            session.flush()

        # DB 확인
        with factory.session() as session:
            users = session.query(User).all()
            posts = session.query(Post).all()

            assert len(users) == 1
            assert len(posts) == 1

            # FK도 설정됨 (DB에서)
            result = session._connection.execute(
                "SELECT user_id FROM post WHERE id = 1"
            ).fetchone()
            assert result["user_id"] == 1

    def test_multiple_children_cascade(self, setup_tables):
        """여러 자식 엔티티도 모두 cascade로 저장됨"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Bob"

            p1 = Post()
            p1.title = "Post 1"
            p2 = Post()
            p2.title = "Post 2"
            p3 = Post()
            p3.title = "Post 3"

            # 모두 append
            u.posts.append(p1)
            u.posts.append(p2)
            u.posts.append(p3)

            # session.add(u) → 모든 posts도 cascade
            session.add(u)

            assert p1 in session._new
            assert p2 in session._new
            assert p3 in session._new

            session.commit()

        # 확인
        with factory.session() as session:
            posts = session.query(Post).all()
            assert len(posts) == 3

    def test_extend_cascades_children(self, setup_tables):
        """extend로 추가한 자식들도 cascade로 저장됨"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Charlie"

            posts_to_add = [
                Post(),
                Post(),
            ]
            posts_to_add[0].title = "Ext 1"
            posts_to_add[1].title = "Ext 2"

            # extend 사용
            u.posts.extend(posts_to_add)

            session.add(u)
            session.commit()

        with factory.session() as session:
            posts = session.query(Post).all()
            assert len(posts) == 2

    def test_add_then_append_also_works(self, setup_tables):
        """session.add 먼저 → append도 정상 동작"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Dave"

            session.add(u)  # 먼저 add

            p = Post()
            p.title = "After Add"
            u.posts.append(p)  # 나중에 append

            # p도 세션에 추가됨 (TrackedList에 세션 바인딩됨)
            assert p in session._new

            session.commit()

        with factory.session() as session:
            posts = session.query(Post).all()
            assert len(posts) == 1

    def test_duplicate_add_is_skipped(self, setup_tables):
        """이미 추가된 엔티티는 중복 추가 안됨"""
        factory = setup_tables

        with factory.session() as session:
            u = User()
            u.name = "Eve"
            p = Post()
            p.title = "Test"

            u.posts.append(p)
            session.add(u)  # u와 p 추가

            # 다시 add해도 중복 안됨
            session.add(u)
            session.add(p)

            # _new에는 각각 1번씩만
            assert list(session._new).count(u) == 1
            assert list(session._new).count(p) == 1

            session.commit()


class TestCascadeAddAsync:
    """비동기 세션의 cascade add 테스트"""

    @pytest.fixture
    async def setup_tables(self):
        backend = SQLiteBackend(":memory:")
        factory = SessionFactory(backend)
        async with factory.session_async() as session:
            await session._connection.execute(
                "CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT, email TEXT)"
            )
            await session._connection.execute(
                "CREATE TABLE post (id INTEGER PRIMARY KEY, title TEXT, user_id INTEGER)"
            )
            await session.commit()
        yield factory
        # 테스트 후 비동기 연결 정리
        pool = backend._pool
        if pool:
            await pool.close_all_async()

    async def test_append_before_session_add_cascades_child(self, setup_tables):
        """비동기: append 먼저 → session.add(parent) → child도 cascade로 저장됨"""
        factory = setup_tables

        async with factory.session_async() as session:
            u = User()
            u.name = "Alice"

            p = Post()
            p.title = "Hello World"

            # append 먼저
            u.posts.append(p)

            # 둘 다 세션에 없음
            assert u not in session._new
            assert p not in session._new

            # session.add(u) → p도 cascade
            session.add(u)

            # 둘 다 세션에 있음
            assert u in session._new
            assert p in session._new

            await session.flush()

        # DB 확인
        async with factory.session_async() as session:
            result = await session._connection.execute(
                "SELECT COUNT(*) as cnt FROM user"
            )
            row = await result.fetchone()
            assert row["cnt"] == 1

            result = await session._connection.execute(
                "SELECT COUNT(*) as cnt FROM post"
            )
            row = await result.fetchone()
            assert row["cnt"] == 1

    async def test_multiple_children_cascade_async(self, setup_tables):
        """비동기: 여러 자식도 cascade"""
        factory = setup_tables

        async with factory.session_async() as session:
            u = User()
            u.name = "Bob"

            for i in range(5):
                p = Post()
                p.title = f"Post {i}"
                u.posts.append(p)

            session.add(u)
            await session.commit()

        async with factory.session_async() as session:
            result = await session._connection.execute(
                "SELECT COUNT(*) as cnt FROM post"
            )
            row = await result.fetchone()
            assert row["cnt"] == 5

    async def test_add_then_append_async(self, setup_tables):
        """비동기: session.add 먼저 → append"""
        factory = setup_tables

        async with factory.session_async() as session:
            u = User()
            u.name = "Charlie"

            session.add(u)

            p = Post()
            p.title = "After Add"
            u.posts.append(p)

            assert p in session._new

            await session.commit()

        async with factory.session_async() as session:
            result = await session._connection.execute(
                "SELECT COUNT(*) as cnt FROM post"
            )
            row = await result.fetchone()
            assert row["cnt"] == 1

    async def test_duplicate_add_skipped_async(self, setup_tables):
        """비동기: 중복 add 스킵"""
        factory = setup_tables

        async with factory.session_async() as session:
            u = User()
            u.name = "Dave"
            p = Post()
            p.title = "Test"

            u.posts.append(p)
            session.add(u)
            session.add(u)  # 중복
            session.add(p)  # 중복

            assert list(session._new).count(u) == 1
            assert list(session._new).count(p) == 1

            await session.commit()
