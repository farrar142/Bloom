"""bloom CLI - 메인 엔트리포인트

bloom 명령줄 인터페이스를 제공합니다.

Usage:
    bloom db --application=myapp:app makemigrations
    bloom queue --app=myapp.tasks:task_app worker
    bloom startapp myapp
"""

from __future__ import annotations

import os
from pathlib import Path

import click

from bloom.db.cli import db


def get_template_dir() -> Path:
    """템플릿 디렉토리 경로"""
    return Path(__file__).parent / "templates"


@click.group()
@click.version_option(version="0.1.0", prog_name="bloom")
def main() -> None:
    """Bloom Framework CLI

    Spring-inspired Python DI container framework with ASGI web layer.

    Commands:
        db        Database management (migrations, etc.)
        queue     Task queue management (workers, etc.)
        startapp  Create a new app with boilerplate code
    """
    pass


@main.command()
@click.argument("app_name")
@click.option(
    "--directory",
    "-d",
    default=".",
    help="Directory to create the app in (default: current directory)",
)
def startapp(app_name: str, directory: str) -> None:
    """Create a new app with boilerplate code.

    Creates a new app directory with the following structure (Django-style):
    
    \b
    {app_name}/
    ├── __init__.py
    ├── entity.py      # Entity definitions with __app__ attribute
    ├── repository.py  # CrudRepository implementation
    ├── service.py     # Service layer with business logic
    ├── controller.py  # REST API endpoints
    └── migrations/    # App-specific migrations (Django-style)
        └── __init__.py
    
    Example:
        bloom startapp users
        bloom startapp products --directory=myproject/apps
    """
    template_dir = get_template_dir() / "app"
    
    if not template_dir.exists():
        click.echo(f"Error: Template directory not found: {template_dir}", err=True)
        raise SystemExit(1)
    
    # 앱 디렉토리 생성
    app_dir = Path(directory) / app_name
    if app_dir.exists():
        click.echo(f"Error: Directory already exists: {app_dir}", err=True)
        raise SystemExit(1)
    
    app_dir.mkdir(parents=True)
    
    # migrations 디렉토리 생성 (Django-style: {app}/migrations/)
    migrations_dir = app_dir / "migrations"
    migrations_dir.mkdir(parents=True)
    
    # migrations/__init__.py 생성
    migrations_init = migrations_dir / "__init__.py"
    migrations_init.write_text(f'"""Migrations for {app_name} app"""\n', encoding="utf-8")
    click.echo(f"  Created: {migrations_init}")
    
    # 템플릿 변수
    # 앱 이름에서 엔티티 이름 추론: users -> User, order_items -> OrderItem
    parts = app_name.split("_")
    entity_name = "".join(p.title() for p in parts)
    if entity_name.endswith("s") and len(entity_name) > 1:
        entity_name = entity_name[:-1]  # Users -> User
    
    template_vars = {
        "app_name": app_name,
        "app_name_title": app_name.replace("_", " ").title(),
        "entity_name": entity_name,
    }
    
    # 템플릿 파일 복사
    for template_file in template_dir.glob("*.template"):
        output_name = template_file.stem  # .template 제거
        output_path = app_dir / output_name
        
        # 템플릿 내용 읽기
        content = template_file.read_text(encoding="utf-8")
        
        # 변수 치환
        for key, value in template_vars.items():
            content = content.replace(f"{{{key}}}", value)
        
        # 파일 저장
        output_path.write_text(content, encoding="utf-8")
        click.echo(f"  Created: {output_path}")
    
    click.echo(f"\nApp '{app_name}' created successfully!")
    click.echo(f"\nNext steps:")
    click.echo(f"  1. Edit {app_name}/entity.py to define your models")
    click.echo(f"  2. Run 'bloom db makemigrations' to create migrations")
    click.echo(f"  3. Run 'bloom db migrate' to apply migrations")


# Database CLI
main.add_command(db, name="db")


# Task Queue CLI
try:
    from bloom.task.cli import queue_cli

    main.add_command(queue_cli, name="queue")
except ImportError:
    pass  # task 모듈이 아직 준비되지 않은 경우


if __name__ == "__main__":
    main()
