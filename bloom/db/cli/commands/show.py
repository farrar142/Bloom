"""showmigrations and sqlmigrate commands - View migration status and SQL"""

from __future__ import annotations

import importlib.util

import click

from bloom.db.cli import db, pass_context
from bloom.db.cli.context import DBContext


@db.command()
@pass_context
def showmigrations(ctx: DBContext):
    """Show all migrations and their status"""
    from bloom.db.migrations import MigrationManager, MigrationRegistry

    try:
        session_factory = ctx.get_session_factory()
        registry = MigrationRegistry()
        registry.load_from_directory(ctx.migrations_dir)
        manager = MigrationManager(session_factory, registry)
        applied = manager.get_applied_migrations()
    except Exception:
        applied = set()

    # 마이그레이션 파일 목록
    files = sorted(ctx.migrations_dir.glob("*.py"))
    files = [f for f in files if f.name != "__init__.py"]

    if not files:
        click.echo("No migrations found.")
        return

    click.echo("Migrations:")
    for f in files:
        name = f.stem
        status = "[X]" if name in applied else "[ ]"
        click.echo(f"  {status} {name}")


@db.command()
@click.argument("migration_name")
@pass_context
def sqlmigrate(ctx: DBContext, migration_name: str):
    """Show SQL for a migration"""
    from bloom.db.dialect import SQLiteDialect

    # 마이그레이션 파일 찾기
    file_path = ctx.migrations_dir / f"{migration_name}.py"
    if not file_path.exists():
        # 부분 매칭 시도
        matches = list(ctx.migrations_dir.glob(f"*{migration_name}*.py"))
        if len(matches) == 1:
            file_path = matches[0]
        elif len(matches) > 1:
            click.echo(f"Multiple migrations match '{migration_name}':")
            for m in matches:
                click.echo(f"  - {m.stem}")
            return
        else:
            click.echo(f"Migration not found: {migration_name}")
            return

    # 마이그레이션 로드
    try:
        spec = importlib.util.spec_from_file_location("migration", file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            migration = getattr(module, "migration", None)

            if migration is None:
                click.echo(f"No 'migration' object found in {file_path}")
                return
    except Exception as e:
        click.echo(f"Error loading migration: {e}")
        return

    # SQL 생성
    dialect = SQLiteDialect()
    click.echo(f"-- SQL for migration: {migration.name}")
    click.echo("-- " + "=" * 60)

    for op in migration.operations:
        sql = op.to_sql(dialect)
        click.echo(f"\n-- {op}")
        click.echo(sql + ";")
