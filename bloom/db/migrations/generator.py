"""Migration Generator - Auto-generate migrations from entity changes"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
import os

from .operations import (
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    CreateIndex,
    DropIndex,
)
from .schema import SchemaIntrospector, SchemaDiff
from .base import Migration

if TYPE_CHECKING:
    from ..session import SessionFactory
    from ..entity import EntityMeta


class MigrationGenerator:
    """마이그레이션 자동 생성

    Django의 makemigrations와 유사합니다.

    Examples:
        generator = MigrationGenerator(session_factory, "migrations/")

        # 변경사항 감지 및 마이그레이션 생성
        migration = generator.make_migrations(User, Post)

        # 파일로 저장
        generator.write_migration(migration)
    """

    def __init__(self, session_factory: SessionFactory, migrations_dir: str | Path):
        self._session_factory = session_factory
        self._migrations_dir = Path(migrations_dir)
        self._migrations_dir.mkdir(parents=True, exist_ok=True)

    def make_migrations(
        self, *entity_classes: type, name: str | None = None
    ) -> Migration | None:
        """엔티티 변경사항으로 마이그레이션 생성

        Args:
            entity_classes: 엔티티 클래스들
            name: 마이그레이션 이름 (선택)

        Returns:
            Migration 또는 None (변경사항 없으면)
        """
        from ..entity import get_entity_meta

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

            # 마이그레이션 이름 생성 (항상 넘버링 포함)
            base_name = name or self._generate_migration_name(operations)
            migration_name = self._add_number_prefix(base_name)

            return Migration(
                name=migration_name,
                dependencies=self._get_latest_migration(),
                operations=operations,
            )

    def _diff_to_operations(self, diff: SchemaDiff, metas: list[EntityMeta]) -> list:
        """차이점을 연산으로 변환"""
        operations = []

        # 테이블 생성
        meta_map = {m.table_name: m for m in metas}
        for table_name in diff.tables_to_create:
            meta = meta_map.get(table_name)
            if meta:
                columns = [
                    (name, col.get_column_definition())
                    for name, col in meta.columns.items()
                ]

                # FK 제약조건
                constraints = []
                from ..columns import ForeignKey

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

    def _get_next_number(self) -> int:
        """다음 마이그레이션 번호 계산"""
        import re
        existing = list(self._migrations_dir.glob("*.py"))
        existing = [f for f in existing if f.name != "__init__.py"]
        
        # 기존 마이그레이션에서 가장 큰 번호 찾기
        max_num = 0
        for f in existing:
            match = re.match(r"^(\d{4})_", f.stem)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)
        
        return max_num + 1

    def _add_number_prefix(self, name: str) -> str:
        """이름에 넘버링 추가 (이미 있으면 그대로)"""
        import re
        # 이미 넘버링이 있으면 그대로 반환
        if re.match(r"^\d{4}_", name):
            return name
        
        next_num = self._get_next_number()
        return f"{next_num:04d}_{name}"

    def _generate_migration_name(self, operations: list) -> str:
        """마이그레이션 이름 생성"""
        # 연산 요약
        if operations:
            first_op = operations[0]
            if isinstance(first_op, CreateTable):
                suffix = f"create_{first_op.table_name}"
            elif isinstance(first_op, DropTable):
                suffix = f"drop_{first_op.table_name}"
            elif isinstance(first_op, AddColumn):
                suffix = f"add_{first_op.column_name}_to_{first_op.table_name}"
            else:
                suffix = "auto"
        else:
            suffix = "auto"

        return suffix

    def _get_latest_migration(self) -> list[str]:
        """최신 마이그레이션 의존성"""
        files = sorted(self._migrations_dir.glob("*.py"))
        files = [f for f in files if f.name != "__init__.py"]
        if files:
            # 파일명에서 마이그레이션 이름 추출
            last_file = files[-1]
            return [last_file.stem]
        return []

    def write_migration(self, migration: Migration) -> Path:
        """마이그레이션을 파일로 저장"""
        file_path = self._migrations_dir / f"{migration.name}.py"

        code = self._generate_migration_code(migration)
        file_path.write_text(code)

        return file_path

    def _generate_migration_code(self, migration: Migration) -> str:
        """마이그레이션 Python 코드 생성"""
        lines = [
            '"""',
            f"Migration: {migration.name}",
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
            "",
            "",
        ]

        # 연산 생성
        ops_code = []
        for op in migration.operations:
            ops_code.append(self._operation_to_code(op))

        ops_str = ",\n        ".join(ops_code)
        deps_str = str(migration.dependencies)

        lines.extend(
            [
                f"migration = Migration(",
                f'    name="{migration.name}",',
                f"    dependencies={deps_str},",
                f"    operations=[",
                f"        {ops_str}",
                f"    ],",
                f")",
            ]
        )

        return "\n".join(lines)

    def _operation_to_code(self, op) -> str:
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

        elif isinstance(op, DropTable):
            return f'DropTable("{op.table_name}")'

        elif isinstance(op, AddColumn):
            return f'AddColumn("{op.table_name}", "{op.column_name}", "{op.column_definition}")'

        elif isinstance(op, DropColumn):
            return f'DropColumn("{op.table_name}", "{op.column_name}")'

        elif isinstance(op, CreateIndex):
            cols = ", ".join(f'"{c}"' for c in op.columns)
            return f'CreateIndex("{op.table_name}", "{op.index_name}", [{cols}], unique={op.unique})'

        elif isinstance(op, DropIndex):
            return f'DropIndex("{op.index_name}")'

        return repr(op)
