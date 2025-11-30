"""Task CLI

사용 예시:
    bloom task --worker
    bloom task --worker --concurrency 4
    bloom task -w -a main:app -c 8
"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Any

import click


def import_from_string(import_string: str) -> Any:
    """문자열로부터 객체 임포트"""
    if ":" not in import_string:
        raise ImportError(
            f"Invalid import string '{import_string}'. "
            "Expected format: 'module:attribute' (e.g., 'main:app.queue')"
        )

    module_path, attr_path = import_string.split(":", 1)

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


@click.command("task")
@click.option(
    "-w",
    "--worker",
    is_flag=True,
    help="Start task worker",
)
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
def task(worker: bool, application: str | None, concurrency: int):
    """Task management commands

    \b
    Examples:
        bloom task --worker
        bloom task -w --concurrency 8
        bloom task -w --application=main:app
        bloom task -w -a examples.task_example_app:app -c 4
    """
    if not worker:
        # 옵션 없이 호출되면 도움말 표시
        ctx = click.get_current_context()
        click.echo(ctx.get_help())
        return

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
            raise click.ClickException(str(e))
        else:
            raise click.ClickException(
                f"Could not import default application.\n\n"
                f"Make sure you have 'application.py' with:\n"
                f"  from bloom import Application\n"
                f"  application = Application('myapp')\n"
                f"  # application.queue is your QueueApplication\n\n"
                f"Or specify explicitly:\n"
                f"  bloom task -w --application=mymodule:app"
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

    # 로깅 설정
    configure_logging(level="INFO")

    # concurrency 설정
    queue_app._concurrency = concurrency

    click.echo(f"[Bloom] Starting worker with concurrency={concurrency}")
    click.echo()

    # 워커 실행
    queue_app.run_sync()
