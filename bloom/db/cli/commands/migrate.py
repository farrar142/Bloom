"""migrate and resetdb commands - Apply migrations and reset database"""

from __future__ import annotations

import click

from bloom.db.cli import db, pass_context
from bloom.db.cli.context import DBContext


@db.command()
@click.option("--target", "-t", type=str, default=None, help="Target migration name (or 'zero' to rollback all)")
@click.option("--fake", is_flag=True, help="Mark migrations as run without executing")
@pass_context
def migrate(ctx: DBContext, target: str | None, fake: bool):
    """Apply or rollback migrations to the database
    
    \b
    Examples:
        # 모든 마이그레이션 적용
        bloom db migrate
        
        # 특정 마이그레이션까지만 적용
        bloom db migrate --target 0002_add_email
        
        # 특정 마이그레이션까지 롤백 (해당 마이그레이션은 유지)
        bloom db migrate --target 0001_initial
        
        # 모든 마이그레이션 롤백
        bloom db migrate --target zero
    """
    from bloom.db.migrations import MigrationManager, MigrationRegistry

    try:
        session_factory = ctx.get_session_factory()
    except Exception as e:
        click.echo(f"Error: Could not connect to database: {e}")
        return

    # 레지스트리에 마이그레이션 로드
    registry = MigrationRegistry()
    registry.load_from_directory(ctx.migrations_dir)

    manager = MigrationManager(session_factory, registry)
    
    # 현재 적용된 마이그레이션 확인
    applied = manager.get_applied_migrations()
    all_migrations = registry.get_all()
    all_names = [m.name for m in all_migrations]
    
    # zero 처리: 모든 마이그레이션 롤백
    if target == "zero":
        if not applied:
            click.echo("No migrations to rollback.")
            return
            
        click.echo("Rolling back all migrations...")
        rolled_back = _rollback_all(manager, registry, fake)
        if rolled_back:
            click.echo(f"\n✓ Rolled back {len(rolled_back)} migration(s).")
        return
    
    # target이 이미 적용된 마이그레이션보다 이전이면 롤백
    if target and target in applied:
        # target 이후의 마이그레이션이 있으면 롤백
        target_idx = all_names.index(target) if target in all_names else -1
        applied_after_target = [
            name for name in applied 
            if name in all_names and all_names.index(name) > target_idx
        ]
        
        if applied_after_target:
            click.echo(f"Rolling back to {target}...")
            click.echo(f"Migrations to rollback: {len(applied_after_target)}")
            for name in sorted(applied_after_target, reverse=True):
                click.echo(f"  - {name}")
            
            if fake:
                click.echo("\n[Fake] Marking migrations as rolled back...")
                _fake_rollback(manager, applied_after_target)
            else:
                click.echo("\nRolling back...")
                rolled_back = manager.rollback_to(target)
                for name in rolled_back:
                    click.echo(f"  Rolled back: {name}")
            
            click.echo("\nDone.")
            return
        else:
            click.echo(f"Already at migration {target}. Nothing to do.")
            return

    # 순방향 마이그레이션
    click.echo("Applying migrations...")
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


def _rollback_all(manager: "MigrationManager", registry: "MigrationRegistry", fake: bool) -> list[str]:
    """모든 마이그레이션 롤백"""
    from bloom.db.migrations import MigrationManager
    
    rolled_back: list[str] = []
    
    with manager._session_factory.session() as session:
        connection = session._connection
        
        # 최근 적용된 순서로 조회
        result = connection.execute(
            f"SELECT name FROM {manager.MIGRATION_TABLE} ORDER BY id DESC"
        )
        to_rollback = [row["name"] for row in result.fetchall()]
        
        if fake:
            click.echo("[Fake] Marking migrations as rolled back...")
            for name in to_rollback:
                connection.execute(
                    f"DELETE FROM {manager.MIGRATION_TABLE} WHERE name = :name",
                    {"name": name},
                )
                connection.commit()
                click.echo(f"  Faked rollback: {name}")
                rolled_back.append(name)
        else:
            from bloom.db.migrations.schema import SchemaEditor
            schema = SchemaEditor(connection)
            
            for name in to_rollback:
                migration = registry.get(name)
                if migration is None:
                    click.echo(f"  Warning: Migration {name} not found in registry, skipping rollback logic")
                else:
                    click.echo(f"  Rolling back: {name}")
                    migration.rollback(schema)
                
                connection.execute(
                    f"DELETE FROM {manager.MIGRATION_TABLE} WHERE name = :name",
                    {"name": name},
                )
                connection.commit()
                rolled_back.append(name)
    
    return rolled_back


def _fake_rollback(manager: "MigrationManager", migrations: list[str]) -> None:
    """마이그레이션 롤백 표시만 (실제 롤백 없음)"""
    with manager._session_factory.session() as session:
        for name in migrations:
            session._connection.execute(
                f"DELETE FROM {manager.MIGRATION_TABLE} WHERE name = :name",
                {"name": name},
            )
            session._connection.commit()
            click.echo(f"  Faked rollback: {name}")


@db.command()
@click.argument("steps", type=int, default=1)
@click.option("--fake", is_flag=True, help="Mark migrations as rolled back without executing")
@pass_context
def rollback(ctx: DBContext, steps: int, fake: bool):
    """Roll back the last N migrations (default: 1)
    
    \b
    Examples:
        # 마지막 마이그레이션 롤백
        bloom db rollback
        
        # 마지막 3개 마이그레이션 롤백
        bloom db rollback 3
    """
    from bloom.db.migrations import MigrationManager, MigrationRegistry

    try:
        session_factory = ctx.get_session_factory()
    except Exception as e:
        click.echo(f"Error: Could not connect to database: {e}")
        return

    registry = MigrationRegistry()
    registry.load_from_directory(ctx.migrations_dir)

    manager = MigrationManager(session_factory, registry)
    
    # 현재 적용된 마이그레이션 확인
    applied = manager.get_applied_migrations()
    
    if not applied:
        click.echo("No migrations to rollback.")
        return
    
    if steps > len(applied):
        steps = len(applied)
    
    click.echo(f"Rolling back {steps} migration(s)...")
    
    if fake:
        click.echo("\n[Fake] Marking migrations as rolled back...")
        # 최근 적용된 순서로 가져오기
        with session_factory.session() as session:
            connection = session._connection
            result = connection.execute(
                f"SELECT name FROM {manager.MIGRATION_TABLE} ORDER BY id DESC LIMIT :steps",
                {"steps": steps},
            )
            to_rollback = [row["name"] for row in result.fetchall()]
            
            for name in to_rollback:
                connection.execute(
                    f"DELETE FROM {manager.MIGRATION_TABLE} WHERE name = :name",
                    {"name": name},
                )
                connection.commit()
                click.echo(f"  Faked rollback: {name}")
    else:
        try:
            rolled_back = manager.rollback(steps)
            for name in rolled_back:
                click.echo(f"  Rolled back: {name}")
        except Exception as e:
            click.echo(f"  Error: {e}")
            return

    click.echo("\nDone.")


@db.command()
@pass_context
def status(ctx: DBContext):
    """Show the current migration status
    
    \b
    Examples:
        bloom db status
    """
    from bloom.db.migrations import MigrationManager, MigrationRegistry

    try:
        session_factory = ctx.get_session_factory()
    except Exception as e:
        click.echo(f"Error: Could not connect to database: {e}")
        return

    registry = MigrationRegistry()
    registry.load_from_directory(ctx.migrations_dir)

    manager = MigrationManager(session_factory, registry)
    
    applied = manager.get_applied_migrations()
    pending = manager.get_pending_migrations()
    all_migrations = registry.get_all()
    
    click.echo("Migration Status")
    click.echo("=" * 50)
    
    if not all_migrations:
        click.echo("No migrations found.")
        return
    
    click.echo(f"\nTotal migrations: {len(all_migrations)}")
    click.echo(f"Applied: {len(applied)}")
    click.echo(f"Pending: {len(pending)}")
    
    if applied:
        click.echo("\n✓ Applied migrations:")
        for name in applied:
            click.echo(f"    [✓] {name}")
    
    if pending:
        click.echo("\n⏳ Pending migrations:")
        for m in pending:
            click.echo(f"    [ ] {m.name}")


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
