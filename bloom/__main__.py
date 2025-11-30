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
        bloom worker
        bloom worker --application=main:app.queue
        bloom db makemigrations
        bloom db migrate
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
    from bloom.logging import configure_logging
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
