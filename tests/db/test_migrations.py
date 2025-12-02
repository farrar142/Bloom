"""
Migrations 테스트

- Operations (DDL 연산)
- Schema (SchemaEditor, SchemaIntrospector, SchemaDiff)
- Migration, MigrationRegistry, MigrationManager
- MigrationGenerator
"""

import pytest
from pathlib import Path

from bloom.db import Entity, PrimaryKey, IntegerColumn, StringColumn, create
from bloom.db.backends import SQLiteBackend
from bloom.db.session import SessionFactory
from bloom.db.migrations import (
    # Base
    Migration,
    MigrationRegistry,
    MigrationManager,
    # Operations
    Operation,
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    AlterColumn,
    CreateIndex,
    DropIndex,
    RenameColumn,
    RenameTable,
    RunSQL,
    RunPython,
    # Schema
    SchemaEditor,
    SchemaDiff,
    SchemaIntrospector,
    # Generator
    MigrationGenerator,
)
from bloom.db.migrations.schema import ColumnInfo, TableInfo


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def backend():
    """SQLite 인메모리 백엔드"""
    return SQLiteBackend(":memory:")


@pytest.fixture
def session_factory(backend):
    """SessionFactory"""
    return SessionFactory(backend)


@pytest.fixture
def connection(session_factory):
    """Connection for schema operations"""
    with session_factory.session() as session:
        yield session._connection


@pytest.fixture
def schema_editor(connection):
    """SchemaEditor"""
    return SchemaEditor(connection)


@pytest.fixture
def introspector(connection):
    """SchemaIntrospector"""
    return SchemaIntrospector(connection)


# =============================================================================
# SchemaDiff Tests
# =============================================================================


class TestSchemaDiff:
    """SchemaDiff 테스트"""

    async def test_empty_diff_has_no_changes(self):
        """빈 diff는 변경사항 없음"""
        diff = SchemaDiff()
        assert diff.has_changes is False

    async def test_tables_to_create_has_changes(self):
        """테이블 생성이 있으면 변경사항 있음"""
        diff = SchemaDiff(tables_to_create=["users"])
        assert diff.has_changes is True

    async def test_tables_to_drop_has_changes(self):
        """테이블 삭제가 있으면 변경사항 있음"""
        diff = SchemaDiff(tables_to_drop=["users"])
        assert diff.has_changes is True

    async def test_columns_to_add_has_changes(self):
        """컬럼 추가가 있으면 변경사항 있음"""
        diff = SchemaDiff(columns_to_add=[("users", "email", "VARCHAR(255)")])
        assert diff.has_changes is True

    async def test_columns_to_drop_has_changes(self):
        """컬럼 삭제가 있으면 변경사항 있음"""
        diff = SchemaDiff(columns_to_drop=[("users", "email")])
        assert diff.has_changes is True

    async def test_indexes_to_create_has_changes(self):
        """인덱스 생성이 있으면 변경사항 있음"""
        diff = SchemaDiff(indexes_to_create=[("users", "idx_email", ["email"])])
        assert diff.has_changes is True


# =============================================================================
# ColumnInfo and TableInfo Tests
# =============================================================================


class TestColumnInfo:
    """ColumnInfo 테스트"""

    async def test_create_column_info(self):
        """ColumnInfo 생성"""
        col = ColumnInfo(
            name="id",
            type="INTEGER",
            nullable=False,
            default=None,
            primary_key=True,
        )
        assert col.name == "id"
        assert col.type == "INTEGER"
        assert col.nullable is False
        assert col.primary_key is True

    async def test_nullable_column(self):
        """nullable 컬럼"""
        col = ColumnInfo(
            name="email",
            type="VARCHAR(255)",
            nullable=True,
            default=None,
            primary_key=False,
        )
        assert col.nullable is True
        assert col.primary_key is False


class TestTableInfo:
    """TableInfo 테스트"""

    async def test_create_table_info(self):
        """TableInfo 생성"""
        info = TableInfo(name="users")
        assert info.name == "users"
        assert info.columns == {}
        assert info.indexes == []
        assert info.foreign_keys == []

    async def test_table_info_with_columns(self):
        """컬럼이 있는 TableInfo"""
        col = ColumnInfo("id", "INTEGER", False, None, True)
        info = TableInfo(name="users", columns={"id": col})
        assert "id" in info.columns
        assert info.columns["id"].primary_key is True


# =============================================================================
# SchemaEditor Tests
# =============================================================================


class TestSchemaEditor:
    """SchemaEditor 테스트"""

    async def test_create_table(self, schema_editor, introspector):
        """테이블 생성"""
        schema_editor.create_table(
            "test_users",
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("name", "VARCHAR(100) NOT NULL"),
            ],
        )

        tables = introspector.get_tables()
        assert "test_users" in tables

    async def test_create_table_with_constraints(self, schema_editor, introspector):
        """제약조건이 있는 테이블 생성"""
        schema_editor.create_table(
            "test_posts",
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("title", "VARCHAR(200) NOT NULL"),
                ("user_id", "INTEGER"),
            ],
            constraints=["FOREIGN KEY (user_id) REFERENCES test_users(id)"],
        )

        tables = introspector.get_tables()
        assert "test_posts" in tables

    async def test_drop_table(self, schema_editor, introspector):
        """테이블 삭제"""
        schema_editor.create_table(
            "temp_table",
            [("id", "INTEGER PRIMARY KEY")],
        )
        assert "temp_table" in introspector.get_tables()

        schema_editor.drop_table("temp_table")
        assert "temp_table" not in introspector.get_tables()

    async def test_rename_table(self, schema_editor, introspector):
        """테이블 이름 변경"""
        schema_editor.create_table(
            "old_table",
            [("id", "INTEGER PRIMARY KEY")],
        )

        schema_editor.rename_table("old_table", "new_table")

        tables = introspector.get_tables()
        assert "old_table" not in tables
        assert "new_table" in tables

    async def test_add_column(self, schema_editor, introspector):
        """컬럼 추가"""
        schema_editor.create_table(
            "test_table",
            [("id", "INTEGER PRIMARY KEY")],
        )

        schema_editor.add_column("test_table", "email", "VARCHAR(255)")

        info = introspector.get_table_info("test_table")
        assert "email" in info.columns

    async def test_drop_column(self, schema_editor, introspector):
        """컬럼 삭제 (SQLite 3.35+)"""
        schema_editor.create_table(
            "test_table",
            [
                ("id", "INTEGER PRIMARY KEY"),
                ("name", "VARCHAR(100)"),
                ("email", "VARCHAR(255)"),
            ],
        )

        schema_editor.drop_column("test_table", "email")

        info = introspector.get_table_info("test_table")
        assert "email" not in info.columns
        assert "name" in info.columns

    async def test_rename_column(self, schema_editor, introspector):
        """컬럼 이름 변경"""
        schema_editor.create_table(
            "test_table",
            [
                ("id", "INTEGER PRIMARY KEY"),
                ("old_name", "VARCHAR(100)"),
            ],
        )

        schema_editor.rename_column("test_table", "old_name", "new_name")

        info = introspector.get_table_info("test_table")
        assert "old_name" not in info.columns
        assert "new_name" in info.columns

    async def test_create_index(self, schema_editor, introspector):
        """인덱스 생성"""
        schema_editor.create_table(
            "test_table",
            [
                ("id", "INTEGER PRIMARY KEY"),
                ("email", "VARCHAR(255)"),
            ],
        )

        schema_editor.create_index("test_table", "idx_email", ["email"])

        info = introspector.get_table_info("test_table")
        assert "idx_email" in info.indexes

    async def test_create_unique_index(self, schema_editor, introspector):
        """유니크 인덱스 생성"""
        schema_editor.create_table(
            "test_table",
            [
                ("id", "INTEGER PRIMARY KEY"),
                ("email", "VARCHAR(255)"),
            ],
        )

        schema_editor.create_index(
            "test_table", "idx_email_unique", ["email"], unique=True
        )

        info = introspector.get_table_info("test_table")
        assert "idx_email_unique" in info.indexes

    async def test_drop_index(self, schema_editor, introspector):
        """인덱스 삭제"""
        schema_editor.create_table(
            "test_table",
            [
                ("id", "INTEGER PRIMARY KEY"),
                ("email", "VARCHAR(255)"),
            ],
        )
        schema_editor.create_index("test_table", "idx_email", ["email"])

        schema_editor.drop_index("idx_email")

        info = introspector.get_table_info("test_table")
        assert "idx_email" not in info.indexes

    async def test_alter_column_not_supported(self, schema_editor):
        """ALTER COLUMN은 SQLite에서 지원 안 함"""
        with pytest.raises(NotImplementedError):
            schema_editor.alter_column("test_table", "name", "TEXT")

    async def test_add_constraint_not_supported(self, schema_editor):
        """ADD CONSTRAINT는 SQLite에서 지원 안 함"""
        with pytest.raises(NotImplementedError):
            schema_editor.add_constraint("test_table", "fk_user", "FOREIGN KEY ...")


# =============================================================================
# SchemaIntrospector Tests
# =============================================================================


class TestSchemaIntrospector:
    """SchemaIntrospector 테스트"""

    async def test_get_tables_empty(self, introspector):
        """빈 DB에서 테이블 목록"""
        tables = introspector.get_tables()
        assert tables == []

    async def test_get_tables(self, schema_editor, introspector):
        """테이블 목록 조회"""
        schema_editor.create_table("users", [("id", "INTEGER PRIMARY KEY")])
        schema_editor.create_table("posts", [("id", "INTEGER PRIMARY KEY")])

        tables = introspector.get_tables()
        assert "users" in tables
        assert "posts" in tables

    async def test_get_table_info(self, schema_editor, introspector):
        """테이블 상세 정보"""
        schema_editor.create_table(
            "users",
            [
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("name", "VARCHAR(100) NOT NULL"),
                ("email", "VARCHAR(255)"),
            ],
        )

        info = introspector.get_table_info("users")

        assert info.name == "users"
        assert "id" in info.columns
        assert "name" in info.columns
        assert "email" in info.columns

        assert info.columns["id"].primary_key is True
        assert info.columns["name"].nullable is False

    async def test_get_all_schema(self, schema_editor, introspector):
        """전체 스키마 정보"""
        schema_editor.create_table("table1", [("id", "INTEGER PRIMARY KEY")])
        schema_editor.create_table("table2", [("id", "INTEGER PRIMARY KEY")])

        schema = introspector.get_all_schema()

        assert "table1" in schema
        assert "table2" in schema
        assert isinstance(schema["table1"], TableInfo)

    async def test_compare_with_models_new_table(self, introspector):
        """모델과 비교 - 새 테이블"""

        @Entity(table_name="new_users")
        class NewUser:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)

        from bloom.db.entity import get_entity_meta

        meta = get_entity_meta(NewUser)

        diff = introspector.compare_with_models([meta])

        assert "new_users" in diff.tables_to_create

    async def test_compare_with_models_new_column(self, schema_editor, introspector):
        """모델과 비교 - 새 컬럼"""
        # 기존 테이블 생성
        schema_editor.create_table(
            "existing_users",
            [
                ("id", "INTEGER PRIMARY KEY"),
                ("name", "VARCHAR(100)"),
            ],
        )

        # 새 컬럼이 추가된 모델
        @Entity(table_name="existing_users")
        class ExistingUser:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)
            email = StringColumn(max_length=255)  # 새 컬럼

        from bloom.db.entity import get_entity_meta

        meta = get_entity_meta(ExistingUser)

        diff = introspector.compare_with_models([meta])

        # 새 컬럼 추가가 필요
        assert any(c[1] == "email" for c in diff.columns_to_add)


# =============================================================================
# Operations Tests
# =============================================================================


class TestOperationsDescribe:
    """Operation describe 테스트"""

    async def test_create_table_describe(self):
        """CreateTable describe"""
        op = CreateTable("users", [("id", "INTEGER PRIMARY KEY")])
        assert "Create table users" in op.describe()

    async def test_drop_table_describe(self):
        """DropTable describe"""
        op = DropTable("users")
        assert "Drop table users" in op.describe()

    async def test_add_column_describe(self):
        """AddColumn describe"""
        op = AddColumn("users", "email", "VARCHAR(255)")
        assert "Add column email to users" in op.describe()

    async def test_drop_column_describe(self):
        """DropColumn describe"""
        op = DropColumn("users", "email")
        assert "Drop column email from users" in op.describe()

    async def test_create_index_describe(self):
        """CreateIndex describe"""
        op = CreateIndex("users", "idx_email", ["email"])
        assert "Create" in op.describe()
        assert "index" in op.describe()

    async def test_rename_column_describe(self):
        """RenameColumn describe"""
        op = RenameColumn("users", "old_name", "new_name")
        assert "Rename column" in op.describe()

    async def test_rename_table_describe(self):
        """RenameTable describe"""
        op = RenameTable("old_table", "new_table")
        assert "Rename table" in op.describe()


class TestOperationsToSql:
    """Operation to_sql 테스트"""

    async def test_create_table_to_sql(self):
        """CreateTable to_sql"""
        op = CreateTable(
            "users",
            [
                ("id", "INTEGER PRIMARY KEY"),
                ("name", "VARCHAR(100)"),
            ],
        )
        sql = op.to_sql(None)  # dialect is not used in basic ops
        assert "CREATE TABLE users" in sql
        assert "id INTEGER PRIMARY KEY" in sql

    async def test_drop_table_to_sql(self):
        """DropTable to_sql"""
        op = DropTable("users")
        assert op.to_sql(None) == "DROP TABLE users"

    async def test_add_column_to_sql(self):
        """AddColumn to_sql"""
        op = AddColumn("users", "email", "VARCHAR(255)")
        sql = op.to_sql(None)
        assert "ALTER TABLE users ADD COLUMN email VARCHAR(255)" == sql

    async def test_create_index_to_sql(self):
        """CreateIndex to_sql"""
        op = CreateIndex("users", "idx_email", ["email"])
        sql = op.to_sql(None)
        assert "CREATE INDEX idx_email ON users (email)" == sql

    async def test_create_unique_index_to_sql(self):
        """CreateIndex unique to_sql"""
        op = CreateIndex("users", "idx_email", ["email"], unique=True)
        sql = op.to_sql(None)
        assert "CREATE UNIQUE INDEX" in sql


class TestOperationsForwardBackward:
    """Operation forward/backward 테스트"""

    async def test_create_table_forward(self, schema_editor, introspector):
        """CreateTable forward"""
        op = CreateTable("op_users", [("id", "INTEGER PRIMARY KEY")])
        op.forward(schema_editor)

        assert "op_users" in introspector.get_tables()

    async def test_create_table_backward(self, schema_editor, introspector):
        """CreateTable backward (drop)"""
        op = CreateTable("op_users", [("id", "INTEGER PRIMARY KEY")])
        op.forward(schema_editor)
        op.backward(schema_editor)

        assert "op_users" not in introspector.get_tables()

    async def test_drop_table_forward(self, schema_editor, introspector):
        """DropTable forward"""
        schema_editor.create_table("temp", [("id", "INTEGER PRIMARY KEY")])

        op = DropTable("temp")
        op.forward(schema_editor)

        assert "temp" not in introspector.get_tables()

    async def test_drop_table_backward_with_columns(self, schema_editor, introspector):
        """DropTable backward (recreate)"""
        op = DropTable(
            "temp",
            columns=[("id", "INTEGER PRIMARY KEY"), ("name", "VARCHAR(100)")],
        )
        # backward로 재생성
        op.backward(schema_editor)

        assert "temp" in introspector.get_tables()
        info = introspector.get_table_info("temp")
        assert "name" in info.columns

    async def test_add_column_forward(self, schema_editor, introspector):
        """AddColumn forward"""
        schema_editor.create_table("users", [("id", "INTEGER PRIMARY KEY")])

        op = AddColumn("users", "email", "VARCHAR(255)")
        op.forward(schema_editor)

        info = introspector.get_table_info("users")
        assert "email" in info.columns

    async def test_add_column_backward(self, schema_editor, introspector):
        """AddColumn backward (drop)"""
        schema_editor.create_table(
            "users",
            [("id", "INTEGER PRIMARY KEY"), ("email", "VARCHAR(255)")],
        )

        op = AddColumn("users", "email", "VARCHAR(255)")
        op.backward(schema_editor)

        info = introspector.get_table_info("users")
        assert "email" not in info.columns

    async def test_create_index_forward(self, schema_editor, introspector):
        """CreateIndex forward"""
        schema_editor.create_table(
            "users",
            [("id", "INTEGER PRIMARY KEY"), ("email", "VARCHAR(255)")],
        )

        op = CreateIndex("users", "idx_email", ["email"])
        op.forward(schema_editor)

        info = introspector.get_table_info("users")
        assert "idx_email" in info.indexes

    async def test_create_index_backward(self, schema_editor, introspector):
        """CreateIndex backward (drop)"""
        schema_editor.create_table(
            "users",
            [("id", "INTEGER PRIMARY KEY"), ("email", "VARCHAR(255)")],
        )
        schema_editor.create_index("users", "idx_email", ["email"])

        op = CreateIndex("users", "idx_email", ["email"])
        op.backward(schema_editor)

        info = introspector.get_table_info("users")
        assert "idx_email" not in info.indexes

    async def test_rename_table_forward(self, schema_editor, introspector):
        """RenameTable forward"""
        schema_editor.create_table("old_table", [("id", "INTEGER PRIMARY KEY")])

        op = RenameTable("old_table", "new_table")
        op.forward(schema_editor)

        tables = introspector.get_tables()
        assert "new_table" in tables
        assert "old_table" not in tables

    async def test_rename_table_backward(self, schema_editor, introspector):
        """RenameTable backward"""
        schema_editor.create_table("new_table", [("id", "INTEGER PRIMARY KEY")])

        op = RenameTable("old_table", "new_table")
        op.backward(schema_editor)

        tables = introspector.get_tables()
        assert "old_table" in tables
        assert "new_table" not in tables

    async def test_rename_column_forward(self, schema_editor, introspector):
        """RenameColumn forward"""
        schema_editor.create_table(
            "users",
            [("id", "INTEGER PRIMARY KEY"), ("old_col", "VARCHAR(100)")],
        )

        op = RenameColumn("users", "old_col", "new_col")
        op.forward(schema_editor)

        info = introspector.get_table_info("users")
        assert "new_col" in info.columns
        assert "old_col" not in info.columns

    async def test_rename_column_backward(self, schema_editor, introspector):
        """RenameColumn backward"""
        schema_editor.create_table(
            "users",
            [("id", "INTEGER PRIMARY KEY"), ("new_col", "VARCHAR(100)")],
        )

        op = RenameColumn("users", "old_col", "new_col")
        op.backward(schema_editor)

        info = introspector.get_table_info("users")
        assert "old_col" in info.columns
        assert "new_col" not in info.columns


class TestRunSQL:
    """RunSQL 테스트"""

    async def test_run_sql_forward(self, schema_editor, introspector):
        """RunSQL forward"""
        op = RunSQL("CREATE TABLE run_sql_test (id INTEGER PRIMARY KEY)")
        op.forward(schema_editor)

        assert "run_sql_test" in introspector.get_tables()

    async def test_run_sql_backward(self, schema_editor, introspector):
        """RunSQL backward"""
        schema_editor.execute("CREATE TABLE run_sql_test (id INTEGER PRIMARY KEY)")

        op = RunSQL(
            "CREATE TABLE run_sql_test (id INTEGER PRIMARY KEY)",
            reverse_sql="DROP TABLE run_sql_test",
        )
        op.backward(schema_editor)

        assert "run_sql_test" not in introspector.get_tables()

    async def test_run_sql_describe(self):
        """RunSQL describe"""
        op = RunSQL("SELECT * FROM users WHERE condition IS TRUE AND more")
        desc = op.describe()
        assert "Run SQL" in desc


class TestRunPython:
    """RunPython 테스트"""

    async def test_run_python_forward(self, schema_editor, introspector):
        """RunPython forward"""

        def create_table(schema: SchemaEditor):
            schema.create_table("python_test", [("id", "INTEGER PRIMARY KEY")])

        op = RunPython(create_table)
        op.forward(schema_editor)

        assert "python_test" in introspector.get_tables()

    async def test_run_python_backward(self, schema_editor, introspector):
        """RunPython backward"""
        schema_editor.create_table("python_test", [("id", "INTEGER PRIMARY KEY")])

        def create_table(schema: SchemaEditor):
            schema.create_table("python_test", [("id", "INTEGER PRIMARY KEY")])

        def drop_table(schema: SchemaEditor):
            schema.drop_table("python_test")

        op = RunPython(create_table, drop_table)
        op.backward(schema_editor)

        assert "python_test" not in introspector.get_tables()

    async def test_run_python_describe(self):
        """RunPython describe"""

        def my_custom_function(schema):
            pass

        op = RunPython(my_custom_function)
        assert "my_custom_function" in op.describe()


# =============================================================================
# Migration Tests
# =============================================================================


class TestMigration:
    """Migration 테스트"""

    async def test_create_migration(self):
        """Migration 생성"""
        migration = Migration(
            name="0001_initial",
            dependencies=[],
            operations=[
                CreateTable("users", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )

        assert migration.name == "0001_initial"
        assert migration.dependencies == []
        assert len(migration.operations) == 1

    async def test_migration_apply(self, schema_editor, introspector):
        """Migration apply"""
        migration = Migration(
            name="0001_initial",
            dependencies=[],
            operations=[
                CreateTable("mig_users", [("id", "INTEGER PRIMARY KEY")]),
                AddColumn("mig_users", "name", "VARCHAR(100)"),
            ],
        )

        migration.apply(schema_editor)

        assert "mig_users" in introspector.get_tables()
        info = introspector.get_table_info("mig_users")
        assert "name" in info.columns

    async def test_migration_rollback(self, schema_editor, introspector):
        """Migration rollback"""
        migration = Migration(
            name="0001_initial",
            dependencies=[],
            operations=[
                CreateTable("mig_users", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )

        migration.apply(schema_editor)
        assert "mig_users" in introspector.get_tables()

        migration.rollback(schema_editor)
        assert "mig_users" not in introspector.get_tables()

    async def test_migration_describe(self):
        """Migration describe"""
        migration = Migration(
            name="0001_initial",
            dependencies=[],
            operations=[
                CreateTable("users", [("id", "INTEGER PRIMARY KEY")]),
                CreateIndex("users", "idx_id", ["id"]),
            ],
        )

        desc = migration.describe()
        assert "0001_initial" in desc
        assert "Create table users" in desc


# =============================================================================
# MigrationRegistry Tests
# =============================================================================


class TestMigrationRegistry:
    """MigrationRegistry 테스트"""

    async def test_register_migration(self):
        """마이그레이션 등록"""
        registry = MigrationRegistry()
        migration = Migration(name="0001_initial", operations=[])

        registry.register(migration)

        assert registry.get("0001_initial") is migration

    async def test_register_duplicate_raises(self):
        """중복 등록 시 에러"""
        registry = MigrationRegistry()
        migration = Migration(name="0001_initial", operations=[])

        registry.register(migration)

        with pytest.raises(ValueError):
            registry.register(migration)

    async def test_get_nonexistent(self):
        """존재하지 않는 마이그레이션 조회"""
        registry = MigrationRegistry()
        assert registry.get("nonexistent") is None

    async def test_get_all(self):
        """모든 마이그레이션 조회"""
        registry = MigrationRegistry()
        m1 = Migration(name="0001", operations=[])
        m2 = Migration(name="0002", operations=[])

        registry.register(m1)
        registry.register(m2)

        all_migs = registry.get_all()
        assert len(all_migs) == 2
        assert all_migs[0].name == "0001"
        assert all_migs[1].name == "0002"

    async def test_get_pending(self):
        """미적용 마이그레이션 조회"""
        registry = MigrationRegistry()
        m1 = Migration(name="0001", operations=[])
        m2 = Migration(name="0002", operations=[])
        m3 = Migration(name="0003", operations=[])

        registry.register(m1)
        registry.register(m2)
        registry.register(m3)

        applied = {"0001", "0002"}
        pending = registry.get_pending(applied)

        assert len(pending) == 1
        assert pending[0].name == "0003"


# =============================================================================
# MigrationManager Tests
# =============================================================================


class TestMigrationManager:
    """MigrationManager 테스트"""

    @pytest.fixture
    def manager(self, session_factory):
        """MigrationManager with registry"""
        registry = MigrationRegistry()
        return MigrationManager(session_factory, registry)

    async def test_get_applied_migrations_empty(self, manager):
        """적용된 마이그레이션 없음"""
        applied = manager.get_applied_migrations()
        assert applied == set()

    async def test_migrate_single(self, manager, introspector):
        """단일 마이그레이션 적용"""
        migration = Migration(
            name="0001_initial",
            operations=[
                CreateTable("mgr_users", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )
        manager.registry.register(migration)

        applied = manager.migrate()

        assert "0001_initial" in applied
        assert "mgr_users" in introspector.get_tables()
        assert "0001_initial" in manager.get_applied_migrations()

    async def test_migrate_multiple(self, manager, introspector):
        """여러 마이그레이션 적용"""
        m1 = Migration(
            name="0001_initial",
            operations=[
                CreateTable("mgr_users", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )
        m2 = Migration(
            name="0002_add_name",
            dependencies=["0001_initial"],
            operations=[
                AddColumn("mgr_users", "name", "VARCHAR(100)"),
            ],
        )

        manager.registry.register(m1)
        manager.registry.register(m2)

        applied = manager.migrate()

        assert len(applied) == 2
        info = introspector.get_table_info("mgr_users")
        assert "name" in info.columns

    async def test_migrate_idempotent(self, manager):
        """중복 적용 방지"""
        migration = Migration(
            name="0001_initial",
            operations=[
                CreateTable("mgr_users", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )
        manager.registry.register(migration)

        # 첫 번째 적용
        applied1 = manager.migrate()
        assert len(applied1) == 1

        # 두 번째 적용 - 이미 적용됨
        applied2 = manager.migrate()
        assert len(applied2) == 0

    async def test_migrate_with_dependency_error(self, manager):
        """의존성 미충족 시 에러"""
        migration = Migration(
            name="0002_add_name",
            dependencies=["0001_initial"],  # 존재하지 않는 의존성
            operations=[
                AddColumn("users", "name", "VARCHAR(100)"),
            ],
        )
        manager.registry.register(migration)

        with pytest.raises(ValueError) as exc:
            manager.migrate()

        assert "depends on" in str(exc.value)

    async def test_rollback(self, manager, introspector):
        """마이그레이션 롤백"""
        migration = Migration(
            name="0001_initial",
            operations=[
                CreateTable("mgr_users", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )
        manager.registry.register(migration)

        manager.migrate()
        assert "mgr_users" in introspector.get_tables()

        rolled_back = manager.rollback(steps=1)

        assert "0001_initial" in rolled_back
        assert "mgr_users" not in introspector.get_tables()

    async def test_rollback_multiple(self, manager, introspector):
        """여러 마이그레이션 롤백"""
        m1 = Migration(
            name="0001_initial",
            operations=[
                CreateTable("mgr_users", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )
        m2 = Migration(
            name="0002_add_posts",
            dependencies=["0001_initial"],
            operations=[
                CreateTable("mgr_posts", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )

        manager.registry.register(m1)
        manager.registry.register(m2)

        manager.migrate()
        assert "mgr_users" in introspector.get_tables()
        assert "mgr_posts" in introspector.get_tables()

        rolled_back = manager.rollback(steps=2)

        assert len(rolled_back) == 2
        assert "mgr_users" not in introspector.get_tables()
        assert "mgr_posts" not in introspector.get_tables()

    async def test_rollback_to_target(self, manager, introspector):
        """특정 지점까지 롤백"""
        m1 = Migration(
            name="0001_initial",
            operations=[
                CreateTable("mgr_users", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )
        m2 = Migration(
            name="0002_add_posts",
            dependencies=["0001_initial"],
            operations=[
                CreateTable("mgr_posts", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )
        m3 = Migration(
            name="0003_add_comments",
            dependencies=["0002_add_posts"],
            operations=[
                CreateTable("mgr_comments", [("id", "INTEGER PRIMARY KEY")]),
            ],
        )

        manager.registry.register(m1)
        manager.registry.register(m2)
        manager.registry.register(m3)

        manager.migrate()

        # 0001까지 롤백 (0002, 0003 롤백)
        rolled_back = manager.rollback_to("0001_initial")

        assert "0002_add_posts" in rolled_back
        assert "0003_add_comments" in rolled_back
        assert "0001_initial" not in rolled_back

        assert "mgr_users" in introspector.get_tables()  # 유지
        assert "mgr_posts" not in introspector.get_tables()
        assert "mgr_comments" not in introspector.get_tables()

    async def test_status(self, manager):
        """마이그레이션 상태 확인"""
        m1 = Migration(name="0001_initial", operations=[])
        m2 = Migration(name="0002_second", operations=[])

        manager.registry.register(m1)
        manager.registry.register(m2)

        manager.migrate()

        status = manager.status()

        assert "0001_initial" in status["applied"]
        assert "0002_second" in status["applied"]
        assert status["pending"] == []
        assert status["total"] == 2

    async def test_get_pending_migrations(self, manager):
        """미적용 마이그레이션 조회"""
        m1 = Migration(name="0001_initial", operations=[])
        m2 = Migration(name="0002_second", operations=[])

        manager.registry.register(m1)
        manager.registry.register(m2)

        # 하나만 적용
        manager.migrate(target="0001_initial")

        pending = manager.get_pending_migrations()

        assert len(pending) == 1
        assert pending[0].name == "0002_second"

    async def test_create_tables_from_entities(self, manager, introspector):
        """엔티티로부터 테이블 생성"""

        @Entity(table_name="entity_users")
        class EntityUser:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)

        manager.create_tables_from_entities(EntityUser)

        assert "entity_users" in introspector.get_tables()


# =============================================================================
# MigrationGenerator Tests
# =============================================================================


class TestMigrationGenerator:
    """MigrationGenerator 테스트"""

    @pytest.fixture
    def generator(self, session_factory, tmp_path):
        """MigrationGenerator"""
        return MigrationGenerator(session_factory, tmp_path / "migrations")

    async def test_make_migrations_new_table(self, generator, session_factory):
        """새 테이블 마이그레이션 생성"""

        @Entity(table_name="gen_users")
        class GenUser:
            id = PrimaryKey[int](auto_increment=True)
            name = StringColumn(max_length=100)

        migration = generator.make_migrations(GenUser, name="0001_create_users")

        assert migration is not None
        assert migration.name == "0001_create_users"
        assert len(migration.operations) > 0

        # CreateTable 연산 확인
        create_ops = [op for op in migration.operations if isinstance(op, CreateTable)]
        assert len(create_ops) == 1
        assert create_ops[0].table_name == "gen_users"

    async def test_make_migrations_no_changes(self, generator, session_factory):
        """변경사항 없으면 None 반환"""

        @Entity(table_name="existing_table")
        class ExistingTable:
            id = PrimaryKey[int](auto_increment=True)

        # 먼저 테이블 생성
        with session_factory.session() as session:
            session._connection.execute(
                "CREATE TABLE existing_table (id INTEGER PRIMARY KEY)"
            )
            session._connection.commit()

        migration = generator.make_migrations(ExistingTable)

        # 변경사항 없으므로 None
        assert migration is None

    async def test_make_migrations_add_column(self, generator, session_factory):
        """컬럼 추가 마이그레이션 생성"""
        # 기존 테이블 생성
        with session_factory.session() as session:
            session._connection.execute(
                "CREATE TABLE add_col_users (id INTEGER PRIMARY KEY)"
            )
            session._connection.commit()

        # 새 컬럼이 있는 모델
        @Entity(table_name="add_col_users")
        class AddColUser:
            id = PrimaryKey[int](auto_increment=True)
            email = StringColumn(max_length=255)

        migration = generator.make_migrations(AddColUser, name="0002_add_email")

        assert migration is not None
        add_column_ops = [
            op for op in migration.operations if isinstance(op, AddColumn)
        ]
        assert len(add_column_ops) == 1
        assert add_column_ops[0].column_name == "email"

    async def test_migrations_dir_created(self, session_factory, tmp_path):
        """마이그레이션 디렉토리 자동 생성"""
        migrations_dir = tmp_path / "new_migrations"
        generator = MigrationGenerator(session_factory, migrations_dir)

        assert migrations_dir.exists()


# =============================================================================
# Integration Tests
# =============================================================================


class TestMigrationIntegration:
    """마이그레이션 통합 테스트"""

    async def test_full_migration_lifecycle(self, session_factory):
        """전체 마이그레이션 라이프사이클"""
        registry = MigrationRegistry()
        manager = MigrationManager(session_factory, registry)

        # 1. 초기 마이그레이션
        initial = Migration(
            name="0001_initial",
            operations=[
                CreateTable(
                    "lifecycle_users",
                    [
                        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                        ("name", "VARCHAR(100) NOT NULL"),
                    ],
                ),
            ],
        )
        registry.register(initial)

        # 2. 컬럼 추가 마이그레이션
        add_email = Migration(
            name="0002_add_email",
            dependencies=["0001_initial"],
            operations=[
                AddColumn("lifecycle_users", "email", "VARCHAR(255)"),
            ],
        )
        registry.register(add_email)

        # 3. 인덱스 추가 마이그레이션
        add_index = Migration(
            name="0003_add_email_index",
            dependencies=["0002_add_email"],
            operations=[
                CreateIndex("lifecycle_users", "idx_email", ["email"], unique=True),
            ],
        )
        registry.register(add_index)

        # 마이그레이션 적용
        applied = manager.migrate()
        assert len(applied) == 3

        # 상태 확인
        status = manager.status()
        assert status["total"] == 3
        assert len(status["applied"]) == 3
        assert len(status["pending"]) == 0

        # 스키마 확인
        with session_factory.session() as session:
            introspector = SchemaIntrospector(session._connection)
            info = introspector.get_table_info("lifecycle_users")

            assert "id" in info.columns
            assert "name" in info.columns
            assert "email" in info.columns
            assert "idx_email" in info.indexes

        # 롤백
        rolled_back = manager.rollback(steps=1)
        assert "0003_add_email_index" in rolled_back

        # 인덱스 제거 확인
        with session_factory.session() as session:
            introspector = SchemaIntrospector(session._connection)
            info = introspector.get_table_info("lifecycle_users")
            assert "idx_email" not in info.indexes

    async def test_complex_migration_with_run_python(self, session_factory):
        """RunPython을 포함한 복잡한 마이그레이션"""
        registry = MigrationRegistry()
        manager = MigrationManager(session_factory, registry)

        def seed_data(schema: SchemaEditor):
            schema.execute("INSERT INTO python_users (name) VALUES ('admin')")
            schema.execute("INSERT INTO python_users (name) VALUES ('user1')")

        def remove_seed_data(schema: SchemaEditor):
            schema.execute("DELETE FROM python_users WHERE name IN ('admin', 'user1')")

        migration = Migration(
            name="0001_with_seed",
            operations=[
                CreateTable(
                    "python_users",
                    [
                        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                        ("name", "VARCHAR(100)"),
                    ],
                ),
                RunPython(seed_data, remove_seed_data),
            ],
        )
        registry.register(migration)

        manager.migrate()

        # 데이터 확인
        with session_factory.session() as session:
            result = session._connection.execute("SELECT * FROM python_users")
            rows = list(result.fetchall())
            assert len(rows) == 2
            names = {row["name"] for row in rows}
            assert "admin" in names
            assert "user1" in names
