"""bloom CLI - 메인 엔트리포인트

bloom 명령줄 인터페이스를 제공합니다.

Usage:
    bloom startproject myproject
    bloom startapp users
    bloom server
    bloom db makemigrations
    bloom db migrate
    bloom queue worker
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click


def get_template_dir() -> Path:
    """템플릿 디렉토리 경로"""
    return Path(__file__).parent / "templates"


@click.group()
@click.version_option(version="0.1.0", prog_name="bloom")
def main() -> None:
    """Bloom Framework CLI

    Spring-inspired Python DI container framework with ASGI web layer.

    Commands:
        startproject  Create a new project with basic structure
        startapp      Create a new app with boilerplate code
        server        Run development server
        db            Database management (migrations, etc.)
        queue         Task queue management (workers, etc.)
    """
    pass


@main.command()
@click.argument("path", default=".")
def startproject(path: str) -> None:
    """Create a new project with basic structure.

    Creates a new project directory with the following structure:

    \b
    {path}/
    ├── app.py           # Application entry point
    └── settings/        # Configuration module
        ├── __init__.py
        └── database.py  # Database configuration

    Examples:
        bloom startproject myproject     # Create 'myproject' directory
        bloom startproject .             # Initialize in current directory
    """
    template_dir = get_template_dir() / "project"

    if not template_dir.exists():
        click.echo(f"Error: Template directory not found: {template_dir}", err=True)
        raise SystemExit(1)

    # 프로젝트 디렉토리 결정
    if path == ".":
        project_dir = Path.cwd()
        project_name = project_dir.name
    else:
        project_dir = Path(path)
        project_name = project_dir.name

        if project_dir.exists():
            # 디렉토리가 이미 존재하면 비어있는지 확인
            if any(project_dir.iterdir()):
                click.echo(f"Error: Directory '{path}' is not empty", err=True)
                raise SystemExit(1)
        else:
            project_dir.mkdir(parents=True)

    # 프로젝트 이름 정규화
    project_name = project_name.replace("-", "_").replace(" ", "_")

    # 템플릿 변수
    template_vars = {
        "project_name": project_name,
    }

    click.echo(f"Creating project '{project_name}' in {project_dir}")

    # app.py 생성
    app_template = template_dir / "app.py.template"
    if app_template.exists():
        content = app_template.read_text(encoding="utf-8")
        for key, value in template_vars.items():
            content = content.replace(f"{{{key}}}", value)
        content = content.replace("{{", "{").replace("}}", "}")

        app_path = project_dir / "app.py"
        app_path.write_text(content, encoding="utf-8")
        click.echo(f"  Created: {app_path}")

    # settings 디렉토리 생성
    settings_dir = project_dir / "settings"
    settings_dir.mkdir(exist_ok=True)

    # settings 템플릿 처리
    settings_template_dir = template_dir / "settings"
    if settings_template_dir.exists():
        for template_file in settings_template_dir.glob("*.template"):
            output_name = template_file.stem  # .template 제거
            output_path = settings_dir / output_name

            content = template_file.read_text(encoding="utf-8")
            for key, value in template_vars.items():
                content = content.replace(f"{{{key}}}", value)
            content = content.replace("{{", "{").replace("}}", "}")

            output_path.write_text(content, encoding="utf-8")
            click.echo(f"  Created: {output_path}")

    click.echo(f"\nProject '{project_name}' created successfully!")
    click.echo(f"\nNext steps:")
    click.echo(f"  cd {path}")
    click.echo(f"  bloom startapp users          # Create your first app")
    click.echo(f"  bloom db makemigrations       # Create migrations")
    click.echo(f"  bloom db migrate              # Apply migrations")
    click.echo(f"  bloom server                  # Run development server")


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
    migrations_init.write_text(
        f'"""Migrations for {app_name} app"""\n', encoding="utf-8"
    )
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

        # 이스케이프된 중괄호 처리: {{ -> {, }} -> }
        content = content.replace("{{", "{").replace("}}", "}")

        # 파일 저장
        output_path.write_text(content, encoding="utf-8")
        click.echo(f"  Created: {output_path}")

    click.echo(f"\nApp '{app_name}' created successfully!")
    click.echo(f"\nNext steps:")
    click.echo(f"  1. Edit {app_name}/entity.py to define your models")
    click.echo(f"  2. Run 'bloom db makemigrations' to create migrations")
    click.echo(f"  3. Run 'bloom db migrate' to apply migrations")


@main.command()
@click.option(
    "--host",
    "-h",
    default="127.0.0.1",
    help="Host to bind (default: 127.0.0.1)",
)
@click.option(
    "--port",
    "-p",
    default=8000,
    type=int,
    help="Port to bind (default: 8000)",
)
@click.option(
    "--reload",
    "-r",
    is_flag=True,
    default=True,
    help="Enable auto-reload (default: True)",
)
@click.option(
    "--application",
    "-A",
    default="app:application",
    help="Application path (default: app:application)",
)
def server(host: str, port: int, reload: bool, application: str) -> None:
    """Run development server.

    Starts uvicorn with the specified application.

    Examples:
        bloom server                              # Run with defaults
        bloom server --port 8080                  # Custom port
        bloom server -A myapp:app                 # Custom application
        bloom server --no-reload                  # Disable auto-reload
    """
    # application path에서 asgi 경로 추출
    if ":" in application:
        module_path, var_name = application.rsplit(":", 1)
        asgi_path = f"{module_path}:{var_name}.asgi"
    else:
        asgi_path = f"{application}:application.asgi"

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        asgi_path,
        "--host",
        host,
        "--port",
        str(port),
    ]

    if reload:
        cmd.append("--reload")

    click.echo(f"Starting development server at http://{host}:{port}")
    click.echo(f"Using application: {application}")
    click.echo("Press Ctrl+C to stop.\n")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        click.echo("\nServer stopped.")
    except FileNotFoundError:
        click.echo("Error: uvicorn not found. Install it with: pip install uvicorn", err=True)
        raise SystemExit(1)


# Database CLI
from bloom.db.cli import db

main.add_command(db, name="db")


# Task Queue CLI
try:
    from bloom.task.cli import queue_cli

    main.add_command(queue_cli, name="queue")
except ImportError:
    pass  # task 모듈이 아직 준비되지 않은 경우


if __name__ == "__main__":
    main()
