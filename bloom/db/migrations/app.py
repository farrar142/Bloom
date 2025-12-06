"""App-based Migration System - 앱별 마이그레이션 생성 및 의존성 관리"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING
import re

from .base import Migration, MigrationRegistry, MigrationManager
from .generator import MigrationGenerator
from .operations import Operation, CreateTable
from .schema import SchemaIntrospector, SchemaDiff, SchemaEditor

if TYPE_CHECKING:
    from ..session import SessionFactory
    from ..entity import EntityMeta


# =============================================================================
# App Migration - 앱별 마이그레이션
# =============================================================================


@dataclass
class AppMigration(Migration):
    """앱별 마이그레이션

    기본 Migration에 앱 이름을 추가합니다.
    """

    app_name: str = ""

    def get_full_name(self) -> str:
        """앱:마이그레이션명 형태의 전체 이름"""
        return f"{self.app_name}:{self.name}"


# =============================================================================
# App Dependency Graph - 앱 간 의존성 그래프
# =============================================================================


class AppDependencyGraph:
    """앱 간 의존성 그래프

    토폴로지 정렬로 앱 적용 순서를 결정합니다.
    """

    def __init__(self) -> None:
        self._dependencies: dict[str, set[str]] = {}
        self._apps: set[str] = set()

    def add_app(self, app_name: str) -> None:
        """앱 추가"""
        self._apps.add(app_name)
        if app_name not in self._dependencies:
            self._dependencies[app_name] = set()

    def add_dependency(self, app_name: str, depends_on: str) -> None:
        """앱 의존성 추가

        Args:
            app_name: 앱 이름
            depends_on: 의존하는 앱 이름
        """
        self.add_app(app_name)
        self.add_app(depends_on)
        self._dependencies[app_name].add(depends_on)

    def get_dependencies(self, app_name: str) -> set[str]:
        """앱의 의존성 목록"""
        return self._dependencies.get(app_name, set()).copy()

    def get_all_apps(self) -> set[str]:
        """모든 앱 목록"""
        return self._apps.copy()

    def topological_sort(self) -> list[str]:
        """토폴로지 정렬 - 의존성 순서대로 앱 반환

        Returns:
            의존성 순서대로 정렬된 앱 목록

        Raises:
            ValueError: 순환 의존성 발견 시
        """
        # Kahn's algorithm
        in_degree: dict[str, int] = {app: 0 for app in self._apps}
        for app, deps in self._dependencies.items():
            for dep in deps:
                if app in in_degree:
                    pass  # in_degree는 이미 0으로 초기화

        # 각 앱의 in-degree 계산
        for app, deps in self._dependencies.items():
            for _ in deps:
                pass  # deps를 가리키는 앱의 in_degree 증가하지 않음

        # 역방향 그래프 관점에서 in_degree 계산
        for app in self._apps:
            for other_app, deps in self._dependencies.items():
                if app in deps:
                    in_degree[other_app] += 1

        # in_degree가 0인 앱들로 시작
        queue = [app for app, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            # 알파벳 순으로 정렬하여 일관성 보장
            queue.sort()
            current = queue.pop(0)
            result.append(current)

            # current에 의존하는 앱들의 in_degree 감소
            for app in self._apps:
                if current in self._dependencies.get(app, set()):
                    in_degree[app] -= 1
                    if in_degree[app] == 0:
                        queue.append(app)

        if len(result) != len(self._apps):
            # 순환 의존성 발견
            remaining = self._apps - set(result)
            raise ValueError(f"Circular dependency detected among: {remaining}")

        return result


# =============================================================================
# App Dependency Analyzer - 앱 의존성 분석기
# =============================================================================


class AppDependencyAnalyzer:
    """앱 의존성 분석기

    엔티티의 ForeignKey를 분석하여 앱 간 의존성을 파악합니다.
    """

    def get_entity_app(self, entity_class: type) -> str:
        """엔티티의 앱 이름 가져오기"""
        return getattr(entity_class, "__app__", "default")

    def get_entity_dependencies(self, entity_class: type) -> dict[str, list[type]]:
        """엔티티의 앱 의존성 분석

        ForeignKey가 참조하는 다른 앱의 엔티티를 찾습니다.

        Returns:
            {앱이름: [의존하는 엔티티 클래스들]}
        """
        from ..columns import ForeignKey

        dependencies: dict[str, list[type]] = {}
        my_app = self.get_entity_app(entity_class)

        # 컬럼에서 ForeignKey 찾기
        columns = getattr(entity_class, "__bloom_columns__", {})
        for col_name, col in columns.items():
            if isinstance(col, ForeignKey):
                # 참조 대상 클래스 가져오기
                ref_class = self._resolve_reference(col, entity_class)
                if ref_class:
                    ref_app = self.get_entity_app(ref_class)
                    if ref_app != my_app:
                        if ref_app not in dependencies:
                            dependencies[ref_app] = []
                        dependencies[ref_app].append(ref_class)

        return dependencies

    def _resolve_reference(self, fk, owner_class: type) -> type | None:
        """ForeignKey 참조 대상 클래스 resolve"""
        ref = fk.references
        if isinstance(ref, type):
            return ref
        if isinstance(ref, str):
            # 문자열 참조 resolve
            import sys

            if "." in ref:
                # module.ClassName
                import importlib

                module_path, class_name = ref.rsplit(".", 1)
                try:
                    module = importlib.import_module(module_path)
                    return getattr(module, class_name, None)
                except ImportError:
                    return None
            else:
                # 같은 모듈 내
                module = sys.modules.get(owner_class.__module__)
                if module:
                    return getattr(module, ref, None)
        return None

    def build_dependency_graph(self, entity_classes: list[type]) -> AppDependencyGraph:
        """엔티티들로부터 앱 의존성 그래프 생성"""
        graph = AppDependencyGraph()

        # 모든 앱 추가
        for entity_class in entity_classes:
            app = self.get_entity_app(entity_class)
            graph.add_app(app)

        # 의존성 추가
        for entity_class in entity_classes:
            my_app = self.get_entity_app(entity_class)
            deps = self.get_entity_dependencies(entity_class)
            for dep_app in deps:
                graph.add_dependency(my_app, dep_app)

        return graph


# =============================================================================
# App Migration Generator - 앱별 마이그레이션 생성기
# =============================================================================


class AppMigrationGenerator:
    """앱별 마이그레이션 생성기

    각 앱의 마이그레이션을 별도 디렉토리에 관리합니다.
    Django 스타일로 {app}/migrations/ 구조를 사용합니다.

    Examples:
        generator = AppMigrationGenerator(
            session_factory=sf,
            project_root="."  # 프로젝트 루트 디렉토리
        )

        # accounts 앱 마이그레이션 생성
        migration = generator.make_app_migrations(
            app_name="accounts",
            entity_classes=[User, Profile]
        )

        # 파일로 저장 -> accounts/migrations/0001_xxx.py
        generator.write_migration(migration)
    """

    def __init__(
        self,
        session_factory: "SessionFactory|None" = None,
        project_root: str | Path = ".",
    ):
        self._session_factory = session_factory
        self._project_root = Path(project_root)
        self._analyzer = AppDependencyAnalyzer()

    def get_app_migrations_dir(self, app_name: str) -> Path:
        """앱의 마이그레이션 디렉토리 가져오기 (없으면 생성)

        Django 스타일: {project_root}/{app}/migrations/
        """
        app_dir = self._project_root / app_name / "migrations"
        app_dir.mkdir(parents=True, exist_ok=True)

        # __init__.py 생성
        init_file = app_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text(f'"""Migrations for {app_name} app"""\n')

        return app_dir

    def make_app_migrations(
        self,
        app_name: str,
        entity_classes: list[type],
        name: str | None = None,
    ) -> AppMigration | None:
        """앱별 마이그레이션 생성

        Args:
            app_name: 앱 이름
            entity_classes: 해당 앱의 엔티티 클래스들
            name: 마이그레이션 이름 (선택)

        Returns:
            AppMigration 또는 None (변경사항 없으면)
        """
        from ..entity import get_entity_meta

        if not self._session_factory:
            raise ValueError("session_factory is required for making migrations")

        # 현재 스키마와 모델 비교
        with self._session_factory.session() as session:
            introspector = SchemaIntrospector(session._connection)

            metas: list[EntityMeta] = []
            for cls in entity_classes:
                meta = get_entity_meta(cls)
                if meta:
                    metas.append(meta)

            diff = introspector.compare_with_models(metas)

            if not diff.has_changes:
                return None

            # 연산 생성
            operations = self._diff_to_operations(diff, metas)

            if not operations:
                return None

            # 마이그레이션 이름 생성
            base_name = name or self._generate_migration_name(operations)
            migration_name = self._add_number_prefix(app_name, base_name)

            # 의존성 계산
            dependencies = self._calculate_dependencies(app_name, entity_classes)

            return AppMigration(
                name=migration_name,
                app_name=app_name,
                dependencies=dependencies,
                operations=operations,
            )

    def _diff_to_operations(
        self, diff: SchemaDiff, metas: list["EntityMeta"]
    ) -> list[Operation]:
        """차이점을 연산으로 변환"""
        from .operations import (
            CreateTable,
            DropTable,
            AddColumn,
            DropColumn,
            CreateIndex,
            DropIndex,
        )
        from ..columns import ForeignKey

        operations = []

        # 테이블 생성
        meta_map = {m.table_name: m for m in metas}
        for table_name in diff.tables_to_create:
            meta = meta_map.get(table_name)
            if meta:
                columns = [
                    (col.db_name, col.get_column_definition())
                    for name, col in meta.columns.items()
                ]

                # FK 제약조건
                constraints = []
                for col in meta.columns.values():
                    if isinstance(col, ForeignKey):
                        constraints.append(col.get_constraint_definition())

                operations.append(CreateTable(table_name, columns, constraints))

        # 테이블 삭제
        for table_name in diff.tables_to_drop:
            operations.append(DropTable(table_name))

        # 컬럼 추가
        for table_name, col_name, col_def in diff.columns_to_add:
            operations.append(AddColumn(table_name, col_name, col_def))

        # 컬럼 삭제
        for table_name, col_name in diff.columns_to_drop:
            operations.append(DropColumn(table_name, col_name))

        # 인덱스 생성
        for table_name, index_name, columns in diff.indexes_to_create:
            operations.append(CreateIndex(table_name, index_name, columns))

        # 인덱스 삭제
        for index_name in diff.indexes_to_drop:
            operations.append(DropIndex(index_name))

        return operations

    def _generate_migration_name(self, operations: list[Operation]) -> str:
        """마이그레이션 이름 생성"""
        if operations:
            first_op = operations[0]
            if isinstance(first_op, CreateTable):
                return f"create_{first_op.table_name}"
        return "auto"

    def _get_next_number(self, app_name: str) -> int:
        """앱별 다음 마이그레이션 번호"""
        app_dir = self.get_app_migrations_dir(app_name)
        existing = list(app_dir.glob("*.py"))
        existing = [f for f in existing if f.name != "__init__.py"]

        max_num = 0
        for f in existing:
            match = re.match(r"^(\d{4})_", f.stem)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)

        return max_num + 1

    def _add_number_prefix(self, app_name: str, name: str) -> str:
        """이름에 넘버링 추가"""
        if re.match(r"^\d{4}_", name):
            return name

        next_num = self._get_next_number(app_name)
        return f"{next_num:04d}_{name}"

    def _calculate_dependencies(
        self, app_name: str, entity_classes: list[type]
    ) -> list[str]:
        """마이그레이션 의존성 계산

        1. 같은 앱의 이전 마이그레이션
        2. 다른 앱의 최신 마이그레이션 (FK 참조 시)
        """
        dependencies = []

        # 같은 앱의 이전 마이그레이션
        app_dir = self.get_app_migrations_dir(app_name)
        existing = sorted(app_dir.glob("*.py"))
        existing = [f for f in existing if f.name != "__init__.py"]
        if existing:
            last = existing[-1]
            dependencies.append(f"{app_name}:{last.stem}")

        # 다른 앱 의존성
        for entity_class in entity_classes:
            entity_deps = self._analyzer.get_entity_dependencies(entity_class)
            for dep_app in entity_deps:
                if dep_app != app_name:
                    # 해당 앱의 최신 마이그레이션
                    dep_app_dir = self.get_app_migrations_dir(dep_app)
                    dep_existing = sorted(dep_app_dir.glob("*.py"))
                    dep_existing = [f for f in dep_existing if f.name != "__init__.py"]
                    if dep_existing:
                        dep_last = dep_existing[-1]
                        dep_ref = f"{dep_app}:{dep_last.stem}"
                        if dep_ref not in dependencies:
                            dependencies.append(dep_ref)

        return dependencies

    def write_migration(self, migration: AppMigration) -> Path:
        """마이그레이션을 파일로 저장"""
        app_dir = self.get_app_migrations_dir(migration.app_name)
        file_path = app_dir / f"{migration.name}.py"

        code = self._generate_migration_code(migration)
        file_path.write_text(code)

        return file_path

    def _generate_migration_code(self, migration: AppMigration) -> str:
        """마이그레이션 Python 코드 생성"""
        lines = [
            '"""',
            f"Migration: {migration.name}",
            f"App: {migration.app_name}",
            f"Created: {migration.created_at.isoformat()}",
            '"""',
            "",
            "from bloom.db.migrations import (",
            "    Migration,",
            "    CreateTable,",
            "    DropTable,",
            "    AddColumn,",
            "    DropColumn,",
            "    AlterColumn,",
            "    CreateIndex,",
            "    DropIndex,",
            ")",
            "from bloom.db.migrations.app import AppMigration",
            "",
            "",
        ]

        # 연산 생성
        ops_code = []
        for op in migration.operations:
            ops_code.append(self._operation_to_code(op))

        ops_str = ",\n        ".join(ops_code) if ops_code else ""
        deps_str = str(migration.dependencies)

        lines.extend(
            [
                f"migration = AppMigration(",
                f'    name="{migration.name}",',
                f'    app_name="{migration.app_name}",',
                f"    dependencies={deps_str},",
                f"    operations=[",
                f"        {ops_str}" if ops_str else "",
                f"    ],",
                f")",
            ]
        )

        return "\n".join(lines)

    def _operation_to_code(self, op: Operation) -> str:
        """연산을 코드 문자열로 변환"""
        if isinstance(op, CreateTable):
            cols = ",\n            ".join(
                f'("{name}", "{defn}")' for name, defn in op.columns
            )
            constraints = ",\n            ".join(f'"{c}"' for c in op.constraints)
            return f"""CreateTable(
            "{op.table_name}",
            columns=[
            {cols}
            ],
            constraints=[{constraints}]
        )"""

        elif hasattr(op, "table_name"):
            # 기본 처리
            return repr(op)

        return repr(op)


# =============================================================================
# App Migration Manager - 앱별 마이그레이션 매니저
# =============================================================================


class AppMigrationManager:
    """앱별 마이그레이션 매니저

    앱별 마이그레이션을 로드하고 의존성 순서대로 적용합니다.
    Django 스타일로 {app}/migrations/ 구조를 사용합니다.
    """

    MIGRATION_TABLE = "_bloom_migrations"

    def __init__(
        self,
        session_factory: "SessionFactory",
        project_root: str | Path = ".",
        app_names: list[str] | None = None,
    ):
        self._session_factory = session_factory
        self._project_root = Path(project_root)
        self._app_names = app_names  # 명시적 앱 목록 (None이면 자동 검색)
        self._analyzer = AppDependencyAnalyzer()
        self._registries: dict[str, MigrationRegistry] = {}

    def _ensure_migration_table(self, connection) -> None:
        """마이그레이션 기록 테이블 생성"""
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.MIGRATION_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name VARCHAR(100) NOT NULL,
                name VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()

    def _load_app_migrations(self, app_name: str) -> MigrationRegistry:
        """앱의 마이그레이션 로드

        Django 스타일: {project_root}/{app}/migrations/
        """
        if app_name in self._registries:
            return self._registries[app_name]

        registry = MigrationRegistry()
        app_migrations_dir = self._project_root / app_name / "migrations"

        if app_migrations_dir.exists():
            registry.load_from_directory(app_migrations_dir)

        self._registries[app_name] = registry
        return registry

    def _get_all_apps(self) -> list[str]:
        """모든 앱 목록

        명시적으로 지정되었거나, {app}/migrations/ 디렉토리가 있는 앱들 검색
        """
        if self._app_names:
            return self._app_names

        if not self._project_root.exists():
            return []

        apps = []
        for item in self._project_root.iterdir():
            if item.is_dir() and not item.name.startswith("_"):
                migrations_dir = item / "migrations"
                if migrations_dir.exists() and migrations_dir.is_dir():
                    apps.append(item.name)
        return apps

    def get_applied_migrations(self, app_name: str | None = None) -> set[str]:
        """적용된 마이그레이션 목록"""
        with self._session_factory.session() as session:
            self._ensure_migration_table(session._connection)

            if app_name:
                result = session._connection.execute(
                    f"SELECT name FROM {self.MIGRATION_TABLE} WHERE app_name = :app",
                    {"app": app_name},
                )
            else:
                result = session._connection.execute(
                    f"SELECT name FROM {self.MIGRATION_TABLE}"
                )
            return {row["name"] for row in result.fetchall()}

    def migrate_app(self, app_name: str, target: str | None = None) -> list[str]:
        """특정 앱의 마이그레이션 적용"""
        applied_names: list[str] = []
        registry = self._load_app_migrations(app_name)

        with self._session_factory.session() as session:
            connection = session._connection
            self._ensure_migration_table(connection)

            schema = SchemaEditor(connection)
            applied_set = self.get_applied_migrations(app_name)
            pending = registry.get_pending(applied_set)

            for migration in pending:
                # 의존성 확인
                self._check_dependencies(migration)

                # 마이그레이션 적용
                print(f"Applying {app_name}: {migration.name}")
                migration.apply(schema)

                # 기록
                connection.execute(
                    f"INSERT INTO {self.MIGRATION_TABLE} (app_name, name) VALUES (:app, :name)",
                    {"app": app_name, "name": migration.name},
                )
                connection.commit()
                applied_names.append(f"{app_name}:{migration.name}")

                if target and migration.name == target:
                    break

        return applied_names

    def migrate_all(self) -> list[str]:
        """모든 앱의 마이그레이션을 의존성 순서대로 적용"""
        applied_names: list[str] = []
        apps = self._get_all_apps()

        if not apps:
            return applied_names

        # 앱 의존성 그래프 빌드 (마이그레이션 파일의 dependencies 사용)
        graph = self._build_app_dependency_graph(apps)

        # 토폴로지 정렬로 앱 순서 결정
        try:
            sorted_apps = graph.topological_sort()
        except ValueError:
            # 순환 의존성 - 알파벳 순 fallback
            sorted_apps = sorted(apps)

        # 순서대로 적용
        for app_name in sorted_apps:
            app_applied = self.migrate_app(app_name)
            applied_names.extend(app_applied)

        return applied_names

    def _build_app_dependency_graph(self, apps: list[str]) -> AppDependencyGraph:
        """마이그레이션 파일에서 앱 의존성 그래프 빌드"""
        graph = AppDependencyGraph()

        for app in apps:
            graph.add_app(app)
            registry = self._load_app_migrations(app)

            for migration in registry.get_all():
                for dep in migration.dependencies:
                    # "app:migration" 형식에서 앱 추출
                    if ":" in dep:
                        dep_app = dep.split(":")[0]
                        if dep_app != app:
                            graph.add_dependency(app, dep_app)

        return graph

    def _check_dependencies(self, migration: Migration) -> None:
        """마이그레이션 의존성 확인"""
        all_applied = self.get_applied_migrations()

        for dep in migration.dependencies:
            if ":" in dep:
                # "app:migration" 형식
                dep_app, dep_name = dep.split(":", 1)
                if dep_name not in all_applied:
                    # 해당 앱의 마이그레이션이 적용되었는지 확인
                    app_applied = self.get_applied_migrations(dep_app)
                    if dep_name not in app_applied:
                        raise ValueError(
                            f"Dependency not satisfied: {dep} "
                            f"(required by {migration.name})"
                        )
            else:
                if dep not in all_applied:
                    raise ValueError(
                        f"Dependency not satisfied: {dep} "
                        f"(required by {migration.name})"
                    )

    def rollback_app(
        self,
        app_name: str,
        steps: int = 1,
        check_dependencies: bool = False,
    ) -> list[str]:
        """앱의 마이그레이션 롤백"""
        if check_dependencies:
            self._check_rollback_dependencies(app_name)

        rolled_back: list[str] = []
        registry = self._load_app_migrations(app_name)

        with self._session_factory.session() as session:
            connection = session._connection
            schema = SchemaEditor(connection)

            # 최근 적용된 순서로 조회
            result = connection.execute(
                f"""
                SELECT name FROM {self.MIGRATION_TABLE}
                WHERE app_name = :app
                ORDER BY id DESC LIMIT :steps
                """,
                {"app": app_name, "steps": steps},
            )
            to_rollback = [row["name"] for row in result.fetchall()]

            for name in to_rollback:
                migration = registry.get(name)
                if migration is None:
                    print(f"Warning: Migration {name} not found in registry")
                    continue

                print(f"Rolling back {app_name}: {name}")
                migration.rollback(schema)

                connection.execute(
                    f"DELETE FROM {self.MIGRATION_TABLE} WHERE name = :name",
                    {"name": name},
                )
                connection.commit()
                rolled_back.append(f"{app_name}:{name}")

        return rolled_back

    def _check_rollback_dependencies(self, app_name: str) -> None:
        """롤백 시 다른 앱이 의존하는지 확인"""
        apps = self._get_all_apps()

        for other_app in apps:
            if other_app == app_name:
                continue

            registry = self._load_app_migrations(other_app)
            applied = self.get_applied_migrations(other_app)

            for migration in registry.get_all():
                if migration.name not in applied:
                    continue

                for dep in migration.dependencies:
                    if ":" in dep and dep.startswith(f"{app_name}:"):
                        raise ValueError(
                            f"Cannot rollback {app_name}: {other_app} depends on it "
                            f"(migration {migration.name} requires {dep})"
                        )

    def status(self) -> dict[str, dict[str, Any]]:
        """앱별 마이그레이션 상태"""
        result = {}
        apps = self._get_all_apps()

        for app in apps:
            registry = self._load_app_migrations(app)
            applied = self.get_applied_migrations(app)
            all_migrations = registry.get_all()

            result[app] = {
                "applied": sorted(
                    [m.name for m in all_migrations if m.name in applied]
                ),
                "pending": [m.name for m in all_migrations if m.name not in applied],
                "total": len(all_migrations),
            }

        return result
