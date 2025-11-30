"""Bloom CLI

사용 예시:
    # 워커 실행 (기본: application:application.queue)
    bloom worker
    bloom worker --concurrency 4
    bloom worker --application=main:app.queue -c 8

    # DB 관리
    bloom db makemigrations
    bloom db migrate
    bloom db showmigrations

    # Python -m 으로 실행
    python -m bloom worker
    python -m bloom db makemigrations
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
        bloom worker
        bloom worker --application=main:app
        bloom db makemigrations
        bloom db migrate
        bloom startproject myproject
    """
    pass


# =============================================================================
# worker command
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
    "-c",
    "--concurrency",
    type=int,
    default=4,
    help="Number of concurrent workers (default: 4)",
)
def worker(application: str | None, concurrency: int):
    """Start a task worker

    \b
    Runs the QueueApplication from the specified application module.
    Automatically finds .queue attribute if Application is specified.
    Default: application:application

    \b
    Examples:
        bloom worker
        bloom worker --concurrency 8
        bloom worker --application=main:app
        bloom worker -a examples.task_example_app:app -c 4
    """
    from bloom.log import configure_logging
    from bloom.task.queue_app import QueueApplication
    from bloom import Application

    # 기본값: application:application
    app_path = application or "application:application"

    click.echo(f"[Bloom] Importing {app_path}")

    # 앱 임포트
    try:
        obj = import_from_string(app_path)
    except ImportError as e:
        if application:
            # 명시적으로 지정한 경우 에러
            raise click.ClickException(str(e))
        else:
            # 기본값 사용 시 더 친절한 에러 메시지
            raise click.ClickException(
                f"Could not import default application.\n\n"
                f"Make sure you have 'application.py' with:\n"
                f"  from bloom import Application\n"
                f"  application = Application('myapp')\n"
                f"  # application.queue is your QueueApplication\n\n"
                f"Or specify explicitly:\n"
                f"  bloom worker --application=mymodule:app"
            )

    # Application인 경우 .queue 자동 접근
    if isinstance(obj, Application):
        click.echo(f"[Bloom] Found Application, accessing .queue")
        queue_app = obj.queue
    elif isinstance(obj, QueueApplication):
        queue_app = obj
    else:
        raise click.ClickException(
            f"Expected Application or QueueApplication, got {type(obj).__name__}"
        )

    # 로깅 설정 (bloom.logging 모듈 사용)
    configure_logging(level="INFO")

    # concurrency 설정
    queue_app._concurrency = concurrency

    # 워커 실행
    queue_app.run_sync()


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
    """
    try:
        import uvicorn
    except ImportError:
        raise click.ClickException(
            "uvicorn is required for the server command.\n"
            "Install it with: pip install uvicorn[standard]"
        )

    # 기본값: application:application
    app_path = application or "application:application"

    # ASGI 앱 경로 생성
    asgi_path = f"{app_path}.asgi"

    click.echo(f"[Bloom] Starting server at http://{host}:{port}")
    click.echo(f"[Bloom] Application: {asgi_path}")
    if reload:
        click.echo("[Bloom] Auto-reload enabled")
    click.echo()

    uvicorn.run(
        asgi_path,
        host=host,
        port=port,
        reload=reload,
    )


# =============================================================================
# test command
# =============================================================================


@cli.command()
@click.argument("paths", nargs=-1)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "-x",
    "--exitfirst",
    is_flag=True,
    help="Exit on first failure",
)
@click.option(
    "-k",
    type=str,
    default=None,
    help="Run tests matching expression",
)
@click.option(
    "--cov",
    type=str,
    default=None,
    help="Coverage target (e.g., --cov=src)",
)
def test(
    paths: tuple[str, ...],
    verbose: bool,
    exitfirst: bool,
    k: str | None,
    cov: str | None,
):
    """Run tests with pytest

    \b
    Runs pytest with common options.
    Default: runs all tests in tests/ directory.

    \b
    Examples:
        bloom test
        bloom test tests/test_api.py
        bloom test -v -x
        bloom test -k "test_user"
        bloom test --cov=src
    """
    try:
        import pytest
    except ImportError:
        raise click.ClickException(
            "pytest is required for the test command.\n"
            "Install it with: pip install pytest"
        )

    # pytest 인자 구성
    args = list(paths) if paths else ["tests/"]

    if verbose:
        args.append("-v")
    if exitfirst:
        args.append("-x")
    if k:
        args.extend(["-k", k])
    if cov:
        try:
            import pytest_cov

            args.extend([f"--cov={cov}"])
        except ImportError:
            click.echo("[Bloom] Warning: pytest-cov not installed, skipping coverage")

    click.echo(f"[Bloom] Running: pytest {' '.join(args)}")
    click.echo()

    # pytest 실행
    exit_code = pytest.main(args)
    raise SystemExit(exit_code)


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
# Entry Point
# =============================================================================


def main():
    """CLI 엔트리 포인트"""
    cli()


if __name__ == "__main__":
    main()
