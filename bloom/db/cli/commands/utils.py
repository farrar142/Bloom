"""shell and init commands - Interactive shell and configuration"""

from __future__ import annotations

import code

import click

from bloom.db.cli import db, pass_context, find_project_root
from bloom.db.cli.context import DBContext


@db.command()
@pass_context
def shell(ctx: DBContext):
    """Open interactive database shell"""
    try:
        session_factory = ctx.get_session_factory()
    except Exception as e:
        click.echo(f"Error: Could not connect to database: {e}")
        return

    # 유용한 객체들 준비
    namespace = {
        "session_factory": session_factory,
        "ctx": ctx,
    }

    # 엔티티 클래스 추가
    for entity in ctx.entity_classes:
        namespace[entity.__name__] = entity

    # 세션 생성
    with session_factory.session() as session:
        namespace["session"] = session

        banner = f"""
Bloom DB Shell
==============
Database: {ctx.database_url}
Entities: {[e.__name__ for e in ctx.entity_classes]}

Available objects:
  session - Active database session
  session_factory - Session factory

Entity classes are available by name.

Example:
  users = session.query(User).all()
"""
        code.interact(banner=banner, local=namespace)


@db.command()
@click.option("--force", is_flag=True, help="Overwrite existing config")
@pass_context
def init(ctx: DBContext, force: bool):
    """Initialize database configuration in pyproject.toml"""
    root = find_project_root()
    pyproject = root / "pyproject.toml"

    if not pyproject.exists():
        click.echo("Error: pyproject.toml not found")
        click.echo("Run this command from your project root.")
        return

    # 설정 추가
    config_section = """
[tool.bloom.db]
migrations_dir = "migrations"
entities_module = "app.models"
database_url = "sqlite:///db.sqlite3"
"""

    # 기존 설정 확인
    content = pyproject.read_text()
    if "[tool.bloom.db]" in content and not force:
        click.echo("Configuration already exists. Use --force to overwrite.")
        return

    if "[tool.bloom.db]" in content:
        click.echo("Warning: Overwriting existing configuration")
        # TODO: 실제로는 더 정교한 처리 필요
    else:
        content += config_section

    pyproject.write_text(content)
    click.echo(f"Added Bloom DB configuration to {pyproject}")
    click.echo("\nPlease update the configuration:")
    click.echo("  entities_module = your actual module path")
    click.echo("  database_url = your database connection string")
