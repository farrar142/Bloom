"""마이그레이션 시스템 TDD 테스트

앱별 마이그레이션 생성, 앱 간 의존성 관리 테스트
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from bloom.db import Entity, PrimaryKey, ForeignKey, IntegerColumn, StringColumn
from bloom.db.migrations import (
    Migration,
    MigrationRegistry,
    MigrationManager,
    MigrationGenerator,
    CreateTable,
)


# =============================================================================
# 테스트용 엔티티 정의 (다중 앱 시뮬레이션)
# =============================================================================


# App: accounts
@Entity
class User:
    __tablename__ = "users"
    __app__ = "accounts"

    id: int = PrimaryKey[int]()
    username: str = StringColumn(max_length=100)
    email: str = StringColumn(max_length=255)


@Entity
class Profile:
    __tablename__ = "profiles"
    __app__ = "accounts"

    id: int = PrimaryKey[int]()
    user_id: int = ForeignKey[int](User)
    bio: str = StringColumn(max_length=500, nullable=True)


# App: blog
@Entity
class Post:
    __tablename__ = "posts"
    __app__ = "blog"

    id: int = PrimaryKey[int]()
    author_id: int = ForeignKey[int](User)  # accounts 앱 의존
    title: str = StringColumn(max_length=200)
    content: str = StringColumn(max_length=10000)


@Entity
class Comment:
    __tablename__ = "comments"
    __app__ = "blog"

    id: int = PrimaryKey[int]()
    post_id: int = ForeignKey[int](Post)
    author_id: int = ForeignKey[int](User)  # accounts 앱 의존
    content: str = StringColumn(max_length=1000)


# App: orders (accounts 의존)
@Entity
class Order:
    __tablename__ = "orders"
    __app__ = "orders"

    id: int = PrimaryKey[int]()
    user_id: int = ForeignKey[int](User)  # accounts 앱 의존
    total: int = IntegerColumn(default=0)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_migrations_dir():
    """임시 마이그레이션 디렉토리"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def session_factory():
    """테스트용 세션 팩토리 (SQLite 메모리)"""
    from bloom.db.session import SessionFactory
    from bloom.db.backends.sqlite import SQLiteBackend

    backend = SQLiteBackend(":memory:")
    return SessionFactory(backend)


# =============================================================================
# Test: 앱별 마이그레이션 디렉토리 구조
# =============================================================================


class TestAppMigrationDirectory:
    """앱별 마이그레이션 디렉토리 테스트"""

    def test_create_app_migration_directory(self, temp_migrations_dir):
        """앱별 마이그레이션 디렉토리 생성"""
        from bloom.db.migrations import AppMigrationGenerator

        generator = AppMigrationGenerator(base_dir=temp_migrations_dir)

        # accounts 앱 디렉토리 생성
        accounts_dir = generator.get_app_migrations_dir("accounts")
        assert accounts_dir.exists()
        assert accounts_dir.name == "accounts"
        assert (accounts_dir / "__init__.py").exists()

    def test_multiple_app_directories(self, temp_migrations_dir):
        """여러 앱 디렉토리 생성"""
        from bloom.db.migrations import AppMigrationGenerator

        generator = AppMigrationGenerator(base_dir=temp_migrations_dir)

        apps = ["accounts", "blog", "orders"]
        for app in apps:
            app_dir = generator.get_app_migrations_dir(app)
            assert app_dir.exists()
            assert (temp_migrations_dir / app).is_dir()


# =============================================================================
# Test: 앱별 마이그레이션 생성
# =============================================================================


class TestAppMigrationGeneration:
    """앱별 마이그레이션 생성 테스트"""

    @pytest.mark.asyncio
    async def test_generate_migration_for_single_app(
        self, session_factory, temp_migrations_dir
    ):
        """단일 앱 마이그레이션 생성"""
        from bloom.db.migrations import AppMigrationGenerator

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # accounts 앱 엔티티만으로 마이그레이션 생성
        migration = generator.make_app_migrations(
            app_name="accounts",
            entity_classes=[User, Profile],
        )

        assert migration is not None
        assert migration.app_name == "accounts"
        assert len(migration.operations) > 0

        # users, profiles 테이블 생성 연산 확인
        table_names = [
            op.table_name for op in migration.operations if isinstance(op, CreateTable)
        ]
        assert "users" in table_names
        assert "profiles" in table_names

    @pytest.mark.asyncio
    async def test_migration_file_saved_in_app_directory(
        self, session_factory, temp_migrations_dir
    ):
        """마이그레이션 파일이 앱 디렉토리에 저장됨"""
        from bloom.db.migrations import AppMigrationGenerator

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        migration = generator.make_app_migrations(
            app_name="accounts",
            entity_classes=[User],
        )

        # 파일 저장
        file_path = generator.write_migration(migration)

        assert file_path.exists()
        assert file_path.parent.name == "accounts"
        assert file_path.suffix == ".py"

    @pytest.mark.asyncio
    async def test_migration_numbering_per_app(
        self, session_factory, temp_migrations_dir
    ):
        """앱별 독립적인 마이그레이션 넘버링"""
        from bloom.db.migrations import AppMigrationGenerator

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # accounts 앱 첫 번째 마이그레이션
        m1 = generator.make_app_migrations(
            app_name="accounts",
            entity_classes=[User],
        )
        generator.write_migration(m1)

        # blog 앱 첫 번째 마이그레이션
        m2 = generator.make_app_migrations(
            app_name="blog",
            entity_classes=[Post],
        )
        generator.write_migration(m2)

        # 둘 다 0001로 시작해야 함
        assert m1.name.startswith("0001_")
        assert m2.name.startswith("0001_")


# =============================================================================
# Test: 앱 간 의존성 분석
# =============================================================================


class TestAppDependencyAnalysis:
    """앱 간 의존성 분석 테스트"""

    def test_detect_foreign_key_dependencies(self):
        """ForeignKey로 앱 간 의존성 감지"""
        from bloom.db.migrations import AppDependencyAnalyzer

        analyzer = AppDependencyAnalyzer()

        # Post는 User를 참조 (blog → accounts)
        deps = analyzer.get_entity_dependencies(Post)

        assert "accounts" in deps
        assert User in deps["accounts"]

    def test_detect_multiple_dependencies(self):
        """여러 앱에 대한 의존성 감지"""
        from bloom.db.migrations import AppDependencyAnalyzer

        analyzer = AppDependencyAnalyzer()

        # Comment는 Post(blog, 같은 앱)와 User(accounts)를 참조
        # 다른 앱에 대한 의존성만 감지됨
        deps = analyzer.get_entity_dependencies(Comment)

        # accounts 의존성은 있어야 함 (User 참조)
        assert "accounts" in deps
        # blog는 같은 앱이므로 의존성에 포함되지 않음
        assert "blog" not in deps

    def test_build_app_dependency_graph(self):
        """앱 의존성 그래프 생성"""
        from bloom.db.migrations import AppDependencyAnalyzer

        analyzer = AppDependencyAnalyzer()

        # 모든 엔티티로 의존성 그래프 빌드
        graph = analyzer.build_dependency_graph([User, Profile, Post, Comment, Order])

        # accounts는 의존성 없음 (루트)
        assert graph.get_dependencies("accounts") == set()

        # blog는 accounts에 의존
        assert "accounts" in graph.get_dependencies("blog")

        # orders는 accounts에 의존
        assert "accounts" in graph.get_dependencies("orders")

    def test_topological_sort_apps(self):
        """앱 의존성 순서 정렬 (토폴로지 정렬)"""
        from bloom.db.migrations import AppDependencyAnalyzer

        analyzer = AppDependencyAnalyzer()
        graph = analyzer.build_dependency_graph([User, Profile, Post, Comment, Order])

        # 의존성 순서대로 정렬
        sorted_apps = graph.topological_sort()

        # accounts가 blog, orders보다 먼저
        accounts_idx = sorted_apps.index("accounts")
        blog_idx = sorted_apps.index("blog")
        orders_idx = sorted_apps.index("orders")

        assert accounts_idx < blog_idx
        assert accounts_idx < orders_idx

    def test_detect_circular_dependency(self):
        """순환 의존성 감지"""
        from bloom.db.migrations import AppDependencyGraph

        graph = AppDependencyGraph()
        graph.add_dependency("app_a", "app_b")
        graph.add_dependency("app_b", "app_c")
        graph.add_dependency("app_c", "app_a")  # 순환!

        with pytest.raises(ValueError, match="[Cc]ircular"):
            graph.topological_sort()


# =============================================================================
# Test: 마이그레이션 의존성 자동 설정
# =============================================================================


class TestMigrationDependencies:
    """마이그레이션 간 의존성 테스트"""

    @pytest.mark.asyncio
    async def test_migration_depends_on_other_app(
        self, session_factory, temp_migrations_dir
    ):
        """타 앱 마이그레이션에 대한 의존성 설정"""
        from bloom.db.migrations import AppMigrationGenerator

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # 먼저 accounts 마이그레이션 생성
        accounts_migration = generator.make_app_migrations(
            app_name="accounts",
            entity_classes=[User],
        )
        generator.write_migration(accounts_migration)

        # blog 마이그레이션 생성 (accounts에 의존)
        blog_migration = generator.make_app_migrations(
            app_name="blog",
            entity_classes=[Post],
        )

        # blog 마이그레이션은 accounts의 마이그레이션에 의존해야 함
        assert any(
            dep.startswith("accounts:") for dep in blog_migration.dependencies
        ) or any("accounts" in str(dep) for dep in blog_migration.dependencies)

    @pytest.mark.asyncio
    async def test_same_app_dependency(self, session_factory, temp_migrations_dir):
        """같은 앱 내 마이그레이션 의존성"""
        from bloom.db.migrations import AppMigrationGenerator

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # accounts 첫 번째 마이그레이션
        m1 = generator.make_app_migrations(
            app_name="accounts",
            entity_classes=[User],
        )
        generator.write_migration(m1)

        # accounts 두 번째 마이그레이션 (Profile 추가)
        m2 = generator.make_app_migrations(
            app_name="accounts",
            entity_classes=[User, Profile],
        )

        # 같은 앱의 이전 마이그레이션에 의존
        assert m1.name in m2.dependencies or any(
            "accounts" in dep for dep in m2.dependencies
        )


# =============================================================================
# Test: 마이그레이션 적용 순서
# =============================================================================


class TestMigrationApplyOrder:
    """마이그레이션 적용 순서 테스트"""

    @pytest.mark.asyncio
    async def test_apply_migrations_in_dependency_order(
        self, session_factory, temp_migrations_dir
    ):
        """의존성 순서대로 마이그레이션 적용"""
        from bloom.db.migrations import AppMigrationGenerator, AppMigrationManager

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # accounts 먼저 생성 (다른 앱이 의존함)
        accounts_migration = generator.make_app_migrations(
            app_name="accounts",
            entity_classes=[User],
        )
        generator.write_migration(accounts_migration)

        # blog는 accounts에 의존
        blog_migration = generator.make_app_migrations(
            app_name="blog",
            entity_classes=[Post],
        )
        generator.write_migration(blog_migration)

        # 매니저로 적용
        manager = AppMigrationManager(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # 의존성 순서대로 적용됨 (accounts → blog)
        applied = manager.migrate_all()

        # accounts가 먼저 적용되어야 함
        accounts_applied = [m for m in applied if "accounts" in m]
        blog_applied = [m for m in applied if "blog" in m]

        if accounts_applied and blog_applied:
            assert applied.index(accounts_applied[0]) < applied.index(blog_applied[0])

    @pytest.mark.asyncio
    async def test_skip_already_applied(self, session_factory, temp_migrations_dir):
        """이미 적용된 마이그레이션 스킵"""
        from bloom.db.migrations import AppMigrationGenerator, AppMigrationManager

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        migration = generator.make_app_migrations(
            app_name="accounts",
            entity_classes=[User],
        )
        generator.write_migration(migration)

        manager = AppMigrationManager(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # 첫 번째 적용
        applied1 = manager.migrate_all()
        assert len(applied1) > 0

        # 두 번째 적용 - 이미 적용된 것은 스킵
        applied2 = manager.migrate_all()
        assert len(applied2) == 0


# =============================================================================
# Test: 앱별 마이그레이션 상태
# =============================================================================


class TestAppMigrationStatus:
    """앱별 마이그레이션 상태 테스트"""

    @pytest.mark.asyncio
    async def test_get_app_migration_status(self, session_factory, temp_migrations_dir):
        """앱별 마이그레이션 상태 조회"""
        from bloom.db.migrations import AppMigrationGenerator, AppMigrationManager

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # accounts, blog 마이그레이션 생성
        m1 = generator.make_app_migrations("accounts", [User])
        generator.write_migration(m1)

        m2 = generator.make_app_migrations("blog", [Post])
        generator.write_migration(m2)

        manager = AppMigrationManager(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # accounts만 적용
        manager.migrate_app("accounts")

        # 상태 조회
        status = manager.status()

        assert "accounts" in status
        assert "blog" in status
        assert len(status["accounts"]["applied"]) > 0
        assert len(status["blog"]["pending"]) > 0


# =============================================================================
# Test: 앱별 롤백
# =============================================================================


class TestAppMigrationRollback:
    """앱별 롤백 테스트"""

    @pytest.mark.asyncio
    async def test_rollback_single_app(self, session_factory, temp_migrations_dir):
        """단일 앱 롤백"""
        from bloom.db.migrations import AppMigrationGenerator, AppMigrationManager

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        migration = generator.make_app_migrations("accounts", [User])
        generator.write_migration(migration)

        manager = AppMigrationManager(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # 적용
        manager.migrate_app("accounts")

        # 롤백
        rolled_back = manager.rollback_app("accounts", steps=1)

        assert len(rolled_back) > 0
        assert migration.name in rolled_back or any(
            "accounts" in r for r in rolled_back
        )

    @pytest.mark.asyncio
    async def test_rollback_respects_dependencies(
        self, session_factory, temp_migrations_dir
    ):
        """롤백 시 의존성 고려"""
        from bloom.db.migrations import AppMigrationGenerator, AppMigrationManager

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # accounts → blog 의존성
        m1 = generator.make_app_migrations("accounts", [User])
        generator.write_migration(m1)

        m2 = generator.make_app_migrations("blog", [Post])
        generator.write_migration(m2)

        manager = AppMigrationManager(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        manager.migrate_all()

        # accounts 롤백 시 blog가 의존하고 있으면 경고 또는 에러
        # (또는 blog도 함께 롤백)
        with pytest.raises(ValueError, match="[Dd]epend"):
            manager.rollback_app("accounts", check_dependencies=True)


# =============================================================================
# Test: 통합 시나리오
# =============================================================================


class TestIntegrationScenario:
    """통합 테스트 시나리오"""

    @pytest.mark.asyncio
    async def test_full_multi_app_migration_workflow(
        self, session_factory, temp_migrations_dir
    ):
        """전체 다중 앱 마이그레이션 워크플로우"""
        from bloom.db.migrations import AppMigrationGenerator, AppMigrationManager

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # 1. 각 앱별 마이그레이션 생성
        accounts_m = generator.make_app_migrations("accounts", [User, Profile])
        generator.write_migration(accounts_m)

        blog_m = generator.make_app_migrations("blog", [Post, Comment])
        generator.write_migration(blog_m)

        orders_m = generator.make_app_migrations("orders", [Order])
        generator.write_migration(orders_m)

        # 2. 모든 마이그레이션 적용 (의존성 순서)
        manager = AppMigrationManager(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        applied = manager.migrate_all()

        # 3. 테이블이 생성되었는지 확인
        with session_factory.session() as session:
            # 테이블 존재 확인
            tables = session._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            table_names = {t["name"] for t in tables}

            assert "users" in table_names
            assert "profiles" in table_names
            assert "posts" in table_names
            assert "comments" in table_names
            assert "orders" in table_names

        # 4. 상태 확인
        status = manager.status()
        for app in ["accounts", "blog", "orders"]:
            assert app in status
            assert len(status[app]["applied"]) > 0
            assert len(status[app]["pending"]) == 0

    @pytest.mark.asyncio
    async def test_incremental_migration(self, session_factory, temp_migrations_dir):
        """점진적 마이그레이션 (새 엔티티 추가)"""
        from bloom.db.migrations import AppMigrationGenerator, AppMigrationManager

        generator = AppMigrationGenerator(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )

        # 1. 초기 마이그레이션 (User만)
        m1 = generator.make_app_migrations("accounts", [User])
        assert m1 is not None
        generator.write_migration(m1)

        manager = AppMigrationManager(
            session_factory=session_factory,
            base_dir=temp_migrations_dir,
        )
        applied1 = manager.migrate_all()
        assert len(applied1) == 1

        # 2. Profile 추가 마이그레이션
        m2 = generator.make_app_migrations("accounts", [User, Profile])

        # Profile 테이블이 새로 추가되어야 하므로 m2가 생성되어야 함
        if m2:
            generator.write_migration(m2)
            
            # 새 매니저 인스턴스 생성하여 새 마이그레이션 파일 로드
            manager2 = AppMigrationManager(
                session_factory=session_factory,
                base_dir=temp_migrations_dir,
            )
            applied2 = manager2.migrate_all()
            # 새 마이그레이션이 적용되어야 함
            assert len(applied2) >= 1
            
            # Profile 테이블이 생성되었는지 확인
            with session_factory.session() as session:
                tables = session._connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                table_names = {t["name"] for t in tables}
                assert "profiles" in table_names
        else:
            # m2가 None이면 이미 Profile이 포함되어 있거나 변경사항 없음
            # 하지만 처음 Profile을 추가하면 m2가 생성되어야 함
            pytest.fail("Expected migration for Profile but got None")
