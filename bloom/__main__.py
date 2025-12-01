"""Bloom CLI

사용 예시:
    # 태스크 워커
    bloom task --worker
    bloom task -w --concurrency 4

    # 테스트
    bloom tests
    bloom tests -v -x

    # 개발 서버
    bloom server
    bloom server --port 3000

    # DB 관리
    bloom db makemigrations
    bloom db migrate

    # 프로젝트 생성
    bloom startproject myproject
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

import click

# bloom 패키지가 설치되지 않은 경우를 위해 경로 추가
# __main__.py가 bloom/ 안에 있으므로 상위 디렉토리를 추가
_bloom_parent = Path(__file__).parent.parent
if str(_bloom_parent) not in sys.path:
    sys.path.insert(0, str(_bloom_parent))


def import_from_string(import_string: str) -> Any:
    """
    문자열로부터 객체 임포트

    Args:
        import_string: "module:attribute" 형식의 문자열

    Returns:
        임포트된 객체

    Raises:
        ImportError: 모듈이나 속성을 찾을 수 없는 경우
    """
    if ":" not in import_string:
        raise ImportError(
            f"Invalid import string '{import_string}'. "
            "Expected format: 'module:attribute' (e.g., 'main:app.queue')"
        )

    module_path, attr_path = import_string.split(":", 1)

    # 현재 디렉토리를 sys.path에 추가 (uvicorn과 동일한 동작)
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ImportError(f"Could not import module '{module_path}': {e}") from e

    obj = module
    for attr_name in attr_path.split("."):
        try:
            obj = getattr(obj, attr_name)
        except AttributeError as e:
            raise ImportError(
                f"Could not find attribute '{attr_name}' in '{obj}': {e}"
            ) from e

    return obj


# =============================================================================
# Main CLI Group
# =============================================================================


@click.group()
@click.version_option(version="0.1.0", prog_name="bloom")
def cli():
    """Bloom Framework CLI

    \b
    Examples:
        bloom server
        bloom server --port 3000
        bloom task --worker
        bloom task -w --concurrency 4
        bloom tests
        bloom tests -v -x
        bloom db makemigrations
        bloom db migrate
        bloom startproject myproject
    """
    pass


# =============================================================================
# server command
# =============================================================================


@cli.command()
@click.option(
    "-a",
    "--application",
    type=str,
    default=None,
    help="Application path (default: 'application:application')",
)
@click.option(
    "-h",
    "--host",
    type=str,
    default="127.0.0.1",
    help="Host to bind (default: 127.0.0.1)",
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=8000,
    help="Port to bind (default: 8000)",
)
@click.option(
    "--reload/--no-reload",
    default=True,
    help="Enable auto-reload (default: True)",
)
def server(application: str | None, host: str, port: int, reload: bool):
    """Start development server

    \b
    Runs the ASGI application using uvicorn.
    Default: application:application.asgi

    \b
    Examples:
        bloom server
        bloom server --port 3000
        bloom server --host 0.0.0.0 --port 8080
        bloom server --application=main:app --no-reload
        bloom server --application=backend/application:app
    """
    import subprocess

    # 현재 디렉토리
    cwd = os.getcwd()

    # 기본값: application:application
    app_path = application or "application:application"

    # 경로 구분자 변환: backend/application:app -> backend.application:app
    if "/" in app_path:
        module_part, attr_part = (
            app_path.split(":", 1) if ":" in app_path else (app_path, "")
        )
        module_part = module_part.replace("/", ".")
        app_path = f"{module_part}:{attr_part}" if attr_part else module_part

    # ASGI 앱 경로 생성
    asgi_path = f"{app_path}.asgi"

    click.echo(f"[Bloom] Starting server at http://{host}:{port}")
    click.echo(f"[Bloom] Application: {asgi_path}")
    if reload:
        click.echo("[Bloom] Auto-reload enabled")
    click.echo()

    # 환경변수 설정 (PYTHONPATH에 현재 디렉토리 추가)
    env = os.environ.copy()
    python_path = env.get("PYTHONPATH", "")
    if cwd not in python_path.split(os.pathsep):
        env["PYTHONPATH"] = f"{cwd}{os.pathsep}{python_path}" if python_path else cwd

    # uvicorn 명령어 구성
    cmd = [
        sys.executable, "-m", "uvicorn",
        asgi_path,
        "--host", host,
        "--port", str(port),
    ]
    if reload:
        cmd.extend(["--reload", "--reload-dir", cwd])

    # subprocess로 실행 (환경변수 전달)
    try:
        subprocess.run(cmd, env=env, cwd=cwd)
    except FileNotFoundError:
        raise click.ClickException(
            "uvicorn is required for the server command.\n"
            "Install it with: pip install uvicorn[standard]"
        )
    except KeyboardInterrupt:
        pass


# =============================================================================
# startproject command
# =============================================================================


@cli.command()
@click.argument("path", default=".")
@click.option(
    "-n",
    "--name",
    type=str,
    default=None,
    help="Project name (default: directory name)",
)
def startproject(path: str, name: str | None):
    """Create a new Bloom project

    \b
    Creates a new project with the standard Bloom structure:
      - application.py
      - settings/
          - __init__.py
          - database.py
          - middleware.py
          - task.py
      - pyproject.toml
      - README.md

    \b
    Examples:
        bloom startproject myproject
        bloom startproject . --name myapp
        bloom startproject /path/to/project
    """
    import shutil
    from importlib import resources

    target_path = Path(path).resolve()

    # 프로젝트 이름 결정
    project_name = name or target_path.name
    if project_name == ".":
        project_name = Path.cwd().name

    click.echo(f"[Bloom] Creating project '{project_name}' at {target_path}")

    # 대상 디렉토리 생성
    target_path.mkdir(parents=True, exist_ok=True)

    # 기존 파일 확인
    if (target_path / "application.py").exists():
        raise click.ClickException(
            f"application.py already exists in {target_path}. "
            "Use a different path or remove existing files."
        )

    # 템플릿 디렉토리 경로
    try:
        template_ref = resources.files("bloom.templates.project")
        with resources.as_file(template_ref) as template_dir:
            _copy_template(template_dir, target_path, project_name)
    except Exception as e:
        raise click.ClickException(f"Failed to copy template: {e}")

    click.echo()
    click.echo(f"[Bloom] Project '{project_name}' created successfully!")
    click.echo()
    click.echo("Next steps:")
    click.echo(f"  cd {path}")
    click.echo("  uv sync")
    click.echo("  uvicorn application:application.asgi --reload")


def _copy_template(template_dir: Path, target_path: Path, project_name: str):
    """템플릿 디렉토리를 복사하고 변수를 치환합니다."""
    import shutil

    for src_file in template_dir.rglob("*"):
        if src_file.is_dir():
            continue

        # 상대 경로 계산
        rel_path = src_file.relative_to(template_dir)
        dest_file = target_path / rel_path

        # 디렉토리 생성
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        if src_file.suffix == ".tmpl":
            # .tmpl 파일: 변수 치환 후 확장자 제거
            content = src_file.read_text(encoding="utf-8")
            content = content.replace("{{project_name}}", project_name)
            content = content.replace("{{ project_name }}", project_name)

            # .tmpl 확장자 제거
            final_dest = dest_file.with_suffix("")
            final_dest.write_text(content, encoding="utf-8")
            click.echo(f"  Created: {final_dest.relative_to(target_path)}")
        else:
            # 일반 파일: 그대로 복사
            shutil.copy2(src_file, dest_file)
            click.echo(f"  Created: {dest_file.relative_to(target_path)}")


# =============================================================================
# db command group (from bloom.db.cli)
# =============================================================================

# DB CLI 그룹을 메인 CLI에 추가
from bloom.db.cli import db as db_cli

cli.add_command(db_cli)


# =============================================================================
# task command (from bloom.task.cli)
# =============================================================================

from bloom.task.cli import task as task_cli

cli.add_command(task_cli)


# =============================================================================
# tests command (from bloom.tests.cli)
# =============================================================================

from bloom.tests.cli import tests as tests_cli

cli.add_command(tests_cli)


# =============================================================================
# Entry Point
# =============================================================================


def main():
    """CLI 엔트리 포인트"""
    cli()


if __name__ == "__main__":
    main()
