"""migrate and resetdb commands - Apply migrations and reset database"""

from __future__ import annotations

import click

from bloom.db.cli import db, pass_context
from bloom.db.cli.context import DBContext


@db.command()
@click.option("--target", "-t", type=str, default=None, help="Target migration name")
@click.option("--fake", is_flag=True, help="Mark migrations as run without executing")
@pass_context
def migrate(ctx: DBContext, target: str | None, fake: bool):
    """Apply migrations to the database"""
    from bloom.db.migrations import MigrationManager, MigrationRegistry

    click.echo("Applying migrations...")

    try:
        session_factory = ctx.get_session_factory()
    except Exception as e:
        click.echo(f"Error: Could not connect to database: {e}")
        return

    # 레지스트리에 마이그레이션 로드
    registry = MigrationRegistry()
    registry.load_from_directory(ctx.migrations_dir)

    manager = MigrationManager(session_factory, registry)

    # 적용할 마이그레이션 확인
    pending = manager.get_pending_migrations()

    if not pending:
        click.echo("No migrations to apply.")
        return

    if target:
        # 특정 마이그레이션까지만
        pending = [m for m in pending if m.name <= target]

    click.echo(f"Migrations to apply: {len(pending)}")
    for m in pending:
        click.echo(f"  - {m.name}")

    if fake:
        click.echo("\n[Fake] Marking migrations as applied...")
        with session_factory.session() as session:
            manager._ensure_migration_table(session._connection)
            for m in pending:
                session._connection.execute(
                    f"INSERT INTO {manager.MIGRATION_TABLE} (name) VALUES (:name)",
                    {"name": m.name},
                )
                session._connection.commit()
                click.echo(f"  Faked: {m.name}")
    else:
        click.echo("\nApplying...")
        try:
            applied = manager.migrate(target=target)
            for name in applied:
                click.echo(f"  Applied: {name}")
        except Exception as e:
            click.echo(f"  Error: {e}")
            return

    click.echo("\nDone.")


@db.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option(
    "--keep-migrations",
    is_flag=True,
    help="Keep migration history table (only drop entity tables)",
)
@pass_context
def resetdb(ctx: DBContext, yes: bool, keep_migrations: bool):
    """Reset database to initial state (drop all tables)

    \b
    WARNING: This will permanently delete all data!

    \b
    Examples:
        # 모든 테이블 삭제 (확인 프롬프트)
        bloom db --application=myapp:app resetdb

        # 확인 없이 삭제
        bloom db --application=myapp:app resetdb --yes

        # 마이그레이션 히스토리는 유지
        bloom db --application=myapp:app resetdb --keep-migrations
    """
    from bloom.db.entity import get_entity_meta

    # 확인 프롬프트
    if not yes:
        click.echo("⚠️  WARNING: This will permanently delete ALL data!")
        click.echo("")

        # 삭제될 테이블 목록 표시
        entities = ctx.entity_classes
        if entities:
            click.echo("Tables to be dropped:")
            for entity in entities:
                meta = get_entity_meta(entity)
                if meta:
                    click.echo(f"  - {meta.table_name}")

        if not keep_migrations:
            from bloom.db.migrations import MigrationManager

            click.echo(f"  - {MigrationManager.MIGRATION_TABLE} (migration history)")

        click.echo("")
        if not click.confirm("Are you sure you want to continue?"):
            click.echo("Aborted.")
            return

    try:
        session_factory = ctx.get_session_factory()
    except Exception as e:
        click.echo(f"Error: Could not connect to database: {e}")
        return

    click.echo("Resetting database...")

    with session_factory.session() as session:
        conn = session._connection

        # SQLite에서 외래키 제약 임시 비활성화
        try:
            conn.execute("PRAGMA foreign_keys = OFF")
        except Exception:
            pass  # SQLite가 아닌 경우 무시

        # 엔티티 테이블 삭제
        entities = ctx.entity_classes
        dropped_tables: list[str] = []

        for entity in entities:
            meta = get_entity_meta(entity)
            if meta:
                table_name = meta.table_name
                try:
                    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                    dropped_tables.append(table_name)
                    click.echo(f"  Dropped: {table_name}")
                except Exception as e:
                    click.echo(f"  Error dropping {table_name}: {e}")

        # 마이그레이션 히스토리 테이블 삭제
        if not keep_migrations:
            from bloom.db.migrations import MigrationManager

            migration_table = MigrationManager.MIGRATION_TABLE
            try:
                conn.execute(f"DROP TABLE IF EXISTS {migration_table}")
                click.echo(f"  Dropped: {migration_table}")
            except Exception as e:
                click.echo(f"  Error dropping {migration_table}: {e}")

        # 외래키 제약 다시 활성화
        try:
            conn.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass

        conn.commit()

    click.echo(f"\n✓ Database reset complete. Dropped {len(dropped_tables)} tables.")

    if not keep_migrations:
        click.echo("\nTo recreate tables, run:")
        click.echo("  bloom db migrate")
