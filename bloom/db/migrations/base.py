"""Migration base classes - Migration, MigrationManager, MigrationRegistry"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from datetime import datetime
from pathlib import Path
import importlib.util
import os

from .operations import Operation
from .schema import SchemaEditor, SchemaIntrospector

if TYPE_CHECKING:
    from ..session import SessionFactory
    from ..backends.base import Connection
    from ..entity import EntityMeta


# =============================================================================
# Migration Class
# =============================================================================


@dataclass
class Migration:
    """마이그레이션 정의

    Django 스타일의 마이그레이션 클래스입니다.

    Examples:
        class Migration_0001_initial(Migration):
            def __init__(self):
                super().__init__(
                    name="0001_initial",
                    dependencies=[],
                    operations=[
                        CreateTable("users", [
                            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                            ("name", "VARCHAR(100) NOT NULL"),
                        ]),
                    ]
                )
    """

    name: str
    dependencies: list[str] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)

    def apply(self, schema: SchemaEditor) -> None:
        """순방향 마이그레이션 실행"""
        for op in self.operations:
            op.forward(schema)

    def rollback(self, schema: SchemaEditor) -> None:
        """역방향 마이그레이션 (롤백)"""
        for op in reversed(self.operations):
            op.backward(schema)

    def describe(self) -> str:
        """마이그레이션 설명"""
        ops = "\n".join(f"  - {op.describe()}" for op in self.operations)
        return f"Migration {self.name}:\n{ops}"


# =============================================================================
# Migration Registry
# =============================================================================


class MigrationRegistry:
    """마이그레이션 레지스트리

    마이그레이션들을 등록하고 관리합니다.
    """

    def __init__(self) -> None:
        self._migrations: dict[str, Migration] = {}
        self._order: list[str] = []

    def register(self, migration: Migration) -> None:
        """마이그레이션 등록"""
        if migration.name in self._migrations:
            raise ValueError(f"Migration {migration.name} already registered")
        self._migrations[migration.name] = migration
        self._order.append(migration.name)

    def get(self, name: str) -> Migration | None:
        """마이그레이션 조회"""
        return self._migrations.get(name)

    def get_all(self) -> list[Migration]:
        """모든 마이그레이션 반환 (의존성 순서)"""
        return [self._migrations[name] for name in self._order]

    def get_pending(self, applied: set[str]) -> list[Migration]:
        """미적용 마이그레이션 반환"""
        return [m for m in self.get_all() if m.name not in applied]

    def load_from_directory(self, directory: str | Path) -> None:
        """디렉토리에서 마이그레이션 로드"""
        directory = Path(directory)
        if not directory.exists():
            return

        migration_files = sorted(directory.glob("*.py"))
        for file_path in migration_files:
            if file_path.name.startswith("_"):
                continue

            # 모듈 로드
            spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Migration 클래스 찾기
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    # 이미 Migration 인스턴스인 경우
                    if isinstance(attr, Migration):
                        self.register(attr)
                    # Migration을 상속받은 클래스인 경우 (Migration 자체는 제외)
                    elif (
                        isinstance(attr, type)
                        and issubclass(attr, Migration)
                        and attr is not Migration
                    ):
                        # 클래스에서 name과 operations가 정의되어 있으면 인스턴스화
                        if hasattr(attr, "name") and hasattr(attr, "operations"):
                            migration = Migration(
                                name=attr.name,
                                dependencies=getattr(attr, "dependencies", []),
                                operations=attr.operations,
                            )
                            self.register(migration)


# =============================================================================
# Migration Manager
# =============================================================================


class MigrationManager:
    """마이그레이션 매니저

    마이그레이션 적용, 롤백, 상태 관리를 담당합니다.

    Examples:
        manager = MigrationManager(session_factory)

        # 마이그레이션 적용
        manager.migrate()

        # 특정 버전까지 롤백
        manager.rollback_to("0001_initial")

        # 상태 확인
        applied = manager.get_applied_migrations()
    """

    MIGRATION_TABLE = "_bloom_migrations"

    def __init__(
        self, session_factory: SessionFactory, registry: MigrationRegistry | None = None
    ):
        self._session_factory = session_factory
        self._registry = registry or MigrationRegistry()

    @property
    def registry(self) -> MigrationRegistry:
        return self._registry

    def _ensure_migration_table(self, connection: Connection) -> None:
        """마이그레이션 기록 테이블 생성"""
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.MIGRATION_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()

    def get_applied_migrations(self) -> set[str]:
        """적용된 마이그레이션 목록"""
        with self._session_factory.session() as session:
            self._ensure_migration_table(session._connection)

            result = session._connection.execute(
                f"SELECT name FROM {self.MIGRATION_TABLE}"
            )
            return {row["name"] for row in result.fetchall()}

    def get_pending_migrations(self) -> list[Migration]:
        """미적용 마이그레이션 목록"""
        applied = self.get_applied_migrations()
        return self._registry.get_pending(applied)

    def migrate(self, target: str | None = None) -> list[str]:
        """마이그레이션 적용

        Args:
            target: 적용할 마이그레이션 이름 (None이면 모두 적용)

        Returns:
            적용된 마이그레이션 이름 목록
        """
        applied_names: list[str] = []

        with self._session_factory.session() as session:
            connection = session._connection
            self._ensure_migration_table(connection)

            schema = SchemaEditor(connection)
            pending = self.get_pending_migrations()

            for migration in pending:
                # 의존성 확인
                applied_set = self.get_applied_migrations()
                for dep in migration.dependencies:
                    if dep not in applied_set:
                        raise ValueError(
                            f"Migration {migration.name} depends on {dep} which is not applied"
                        )

                # 마이그레이션 적용
                print(f"Applying migration: {migration.name}")
                migration.apply(schema)

                # 기록
                connection.execute(
                    f"INSERT INTO {self.MIGRATION_TABLE} (name) VALUES (:name)",
                    {"name": migration.name},
                )
                connection.commit()
                applied_names.append(migration.name)

                if target and migration.name == target:
                    break

        return applied_names

    def rollback(self, steps: int = 1) -> list[str]:
        """마이그레이션 롤백

        Args:
            steps: 롤백할 단계 수

        Returns:
            롤백된 마이그레이션 이름 목록
        """
        rolled_back: list[str] = []

        with self._session_factory.session() as session:
            connection = session._connection
            schema = SchemaEditor(connection)

            # 최근 적용된 순서로 조회
            result = connection.execute(
                f"SELECT name FROM {self.MIGRATION_TABLE} ORDER BY id DESC LIMIT :steps",
                {"steps": steps},
            )
            to_rollback = [row["name"] for row in result.fetchall()]

            for name in to_rollback:
                migration = self._registry.get(name)
                if migration is None:
                    print(f"Warning: Migration {name} not found in registry")
                    continue

                print(f"Rolling back: {name}")
                migration.rollback(schema)

                connection.execute(
                    f"DELETE FROM {self.MIGRATION_TABLE} WHERE name = :name",
                    {"name": name},
                )
                connection.commit()
                rolled_back.append(name)

        return rolled_back

    def rollback_to(self, target: str) -> list[str]:
        """특정 마이그레이션까지 롤백

        Args:
            target: 롤백 목표 마이그레이션 (이 마이그레이션은 유지)

        Returns:
            롤백된 마이그레이션 이름 목록
        """
        rolled_back: list[str] = []

        with self._session_factory.session() as session:
            connection = session._connection
            schema = SchemaEditor(connection)

            # target 이후 적용된 마이그레이션들
            result = connection.execute(
                f"""
                SELECT name FROM {self.MIGRATION_TABLE}
                WHERE id > (SELECT id FROM {self.MIGRATION_TABLE} WHERE name = :target)
                ORDER BY id DESC
                """,
                {"target": target},
            )
            to_rollback = [row["name"] for row in result.fetchall()]

            for name in to_rollback:
                migration = self._registry.get(name)
                if migration:
                    print(f"Rolling back: {name}")
                    migration.rollback(schema)

                connection.execute(
                    f"DELETE FROM {self.MIGRATION_TABLE} WHERE name = :name",
                    {"name": name},
                )
                connection.commit()
                rolled_back.append(name)

        return rolled_back

    def status(self) -> dict[str, Any]:
        """마이그레이션 상태"""
        applied = self.get_applied_migrations()
        all_migrations = self._registry.get_all()

        return {
            "applied": sorted(applied),
            "pending": [m.name for m in all_migrations if m.name not in applied],
            "total": len(all_migrations),
        }

    def create_tables_from_entities(self, *entity_classes: type) -> None:
        """엔티티 클래스로부터 테이블 생성 (개발용)"""
        from ..entity import get_entity_meta

        with self._session_factory.session() as session:
            connection = session._connection
            dialect = connection.dialect

            for entity_cls in entity_classes:
                meta = get_entity_meta(entity_cls)
                if meta:
                    sql = dialect.create_table_sql(meta)
                    connection.execute(sql)
            connection.commit()

    def diff_schema(self, *entity_classes: type) -> Any:
        """엔티티와 DB 스키마 차이 확인"""
        from ..entity import get_entity_meta

        with self._session_factory.session() as session:
            introspector = SchemaIntrospector(session._connection)
            metas = [
                get_entity_meta(cls) for cls in entity_classes if get_entity_meta(cls)
            ]
            return introspector.compare_with_models([m for m in metas if m])
