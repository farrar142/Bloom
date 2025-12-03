"""bloom CLI - 메인 엔트리포인트

bloom 명령줄 인터페이스를 제공합니다.

Usage:
    bloom db --application=myapp:app makemigrations
    bloom queue --app=myapp.tasks:task_app worker
"""

from __future__ import annotations

import click

from bloom.db.cli import db


@click.group()
@click.version_option(version="0.1.0", prog_name="bloom")
def main() -> None:
    """Bloom Framework CLI

    Spring-inspired Python DI container framework with ASGI web layer.

    Commands:
        db      Database management (migrations, etc.)
        queue   Task queue management (workers, etc.)
    """
    pass


# Database CLI
main.add_command(db, name="db")


# Task Queue CLI
try:
    from bloom.core.task.cli import queue_cli

    main.add_command(queue_cli, name="queue")
except ImportError:
    pass  # task 모듈이 아직 준비되지 않은 경우


if __name__ == "__main__":
    main()
