"""makemigrations command - Generate migrations from model changes"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from bloom.db.cli import db, pass_context
from bloom.db.cli.context import DBContext


@db.command()
@click.option("--name", "-n", type=str, default=None, help="Migration name")
@click.option("--empty", is_flag=True, help="Create empty migration")
@click.option("--dry-run", is_flag=True, help="Show what would be generated")
@pass_context
def makemigrations(
    ctx: DBContext,
    name: str | None,
    empty: bool,
    dry_run: bool,
):
    """Generate new migrations based on model changes"""
    from bloom.db.migrations import MigrationGenerator, Migration

    click.echo("Checking for model changes...")

    # 마이그레이션 디렉토리 생성
    ctx.migrations_dir.mkdir(parents=True, exist_ok=True)

    if empty:
        # 빈 마이그레이션 생성
        migration = Migration(
            name=name or "empty",
            dependencies=_get_latest_migration(ctx.migrations_dir),
            operations=[],
        )
        click.echo(f"Created empty migration: {migration.name}")
    else:
        # 엔티티 변경사항으로 마이그레이션 생성
        entities = ctx.entity_classes

        if not entities:
            click.echo("No entity classes found. Use --entities to specify module.")
            click.echo("Example: bloom db makemigrations --entities myapp.entities")
            return

        click.echo(f"Found {len(entities)} entities: {[e.__name__ for e in entities]}")

        try:
            session_factory = ctx.get_session_factory()
            generator = MigrationGenerator(session_factory, ctx.migrations_dir)

            migration = generator.make_migrations(*entities, name=name)

            if migration is None:
                click.echo("No changes detected.")
                return

        except Exception as e:
            # DB 연결 실패 시 모델 기반으로만 생성
            click.echo(f"Note: Could not connect to database ({e})")
            click.echo("Generating migration from models only...")

            migration = _make_migration_from_models(entities, ctx.migrations_dir, name)

    if migration is None:
        click.echo("No changes detected.")
        return

    if dry_run:
        click.echo("\n[Dry Run] Would create migration:")
        click.echo(f"  Name: {migration.name}")
        click.echo(f"  Operations: {len(migration.operations)}")
        for op in migration.operations:
            click.echo(f"    - {op}")
        return

    # 파일 저장
    file_path = _write_migration(migration, ctx.migrations_dir)
    click.echo(f"\nCreated migration: {file_path}")
    click.echo(f"  Operations: {len(migration.operations)}")
    for op in migration.operations:
        click.echo(f"    - {op}")


def _get_latest_migration(migrations_dir: Path) -> list[str]:
    """최신 마이그레이션 의존성"""
    files = sorted(migrations_dir.glob("*.py"))
    files = [f for f in files if f.name != "__init__.py"]
    if files:
        return [files[-1].stem]
    return []


def _make_migration_from_models(
    entities: list[type], migrations_dir: Path, name: str | None
) -> Any:
    """DB 연결 없이 모델에서 마이그레이션 생성"""
    from bloom.db.entity import get_entity_meta
    from bloom.db.migrations import Migration
    from bloom.db.migrations.operations import CreateTable
    from bloom.db.columns import ForeignKey, ManyToOne, OneToMany

    # 기존 마이그레이션에서 이미 생성된 테이블 목록 수집
    existing_tables = _get_existing_tables_from_migrations(migrations_dir)

    operations = []

    for entity_cls in entities:
        meta = get_entity_meta(entity_cls)
        if meta is None:
            continue

        # 이미 마이그레이션에 존재하는 테이블은 스킵
        if meta.table_name in existing_tables:
            continue

        columns = []
        for col_name, col in meta.columns.items():
            # 관계 필드는 제외 (ManyToOne, OneToMany)
            if isinstance(col, (ManyToOne, OneToMany)):
                continue
            # Column 계열만 추가
            if hasattr(col, "get_column_definition"):
                columns.append((col_name, col.get_column_definition()))

        constraints = []
        for col in meta.columns.values():
            if isinstance(col, ForeignKey):
                constraints.append(col.get_constraint_definition())

        operations.append(CreateTable(meta.table_name, columns, constraints))

    if not operations:
        return None

    # 마이그레이션 이름 생성
    existing = list(migrations_dir.glob("*.py"))
    existing = [f for f in existing if f.name != "__init__.py"]
    next_num = len(existing) + 1

    if name:
        migration_name = f"{next_num:04d}_{name}"
    else:
        first_table = operations[0].table_name if operations else "auto"
        migration_name = f"{next_num:04d}_create_{first_table}"

    return Migration(
        name=migration_name,
        dependencies=_get_latest_migration(migrations_dir),
        operations=operations,
    )


def _get_existing_tables_from_migrations(migrations_dir: Path) -> set[str]:
    """기존 마이그레이션 파일에서 생성된 테이블 목록 수집"""
    import ast

    tables: set[str] = set()

    for migration_file in migrations_dir.glob("*.py"):
        if migration_file.name == "__init__.py":
            continue

        try:
            content = migration_file.read_text(encoding="utf-8")
            tree = ast.parse(content)

            # Migration 클래스 또는 migration 변수에서 operations 찾기
            for node in ast.walk(tree):
                # CreateTable('table_name', ...) 패턴 찾기
                if isinstance(node, ast.Call):
                    func = node.func
                    # CreateTable 호출 확인
                    if isinstance(func, ast.Name) and func.id == "CreateTable":
                        if node.args and isinstance(node.args[0], ast.Constant):
                            tables.add(node.args[0].value)
                    elif isinstance(func, ast.Attribute) and func.attr == "CreateTable":
                        if node.args and isinstance(node.args[0], ast.Constant):
                            tables.add(node.args[0].value)

        except Exception:
            # 파싱 실패 시 무시
            continue

    return tables


def _write_migration(migration: Any, migrations_dir: Path) -> Path:
    """마이그레이션 파일 저장"""
    from bloom.db.migrations.operations import (
        CreateTable,
        DropTable,
        AddColumn,
        DropColumn,
        CreateIndex,
        DropIndex,
    )

    file_path = migrations_dir / f"{migration.name}.py"

    # __init__.py 생성
    init_file = migrations_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Migrations package"""\n')

    # 마이그레이션 코드 생성
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
        "    CreateIndex,",
        "    DropIndex,",
        ")",
        "",
        "",
    ]

    # 연산 생성
    ops_code = []
    for op in migration.operations:
        ops_code.append(_operation_to_code(op))

    ops_str = ",\n        ".join(ops_code) if ops_code else ""
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

    file_path.write_text("\n".join(lines))
    return file_path


def _operation_to_code(op: Any) -> str:
    """연산을 코드 문자열로 변환"""
    from bloom.db.migrations.operations import (
        CreateTable,
        DropTable,
        AddColumn,
        DropColumn,
        CreateIndex,
        DropIndex,
    )

    if isinstance(op, CreateTable):
        cols = ",\n                ".join(
            f'("{name}", "{defn}")' for name, defn in op.columns
        )
        if op.constraints:
            constraints = ", ".join(f'"{c}"' for c in op.constraints)
            return f"""CreateTable(
            "{op.table_name}",
            columns=[
                {cols}
            ],
            constraints=[{constraints}],
        )"""
        else:
            return f"""CreateTable(
            "{op.table_name}",
            columns=[
                {cols}
            ],
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
