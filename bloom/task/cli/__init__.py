"""bloom.task.cli - Task Queue CLI

bloom queue 명령어를 제공합니다.

Usage:
    bloom queue --app=myapp.tasks:task_app worker [--concurrency=4] [--queues=default,high]
    bloom queue --app=myapp.tasks:task_app inspect active
    bloom queue --app=myapp.tasks:task_app inspect scheduled
    bloom queue --app=myapp.tasks:task_app purge [--queue=default]
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

import click

if TYPE_CHECKING:
    from ..app import TaskApp


# =============================================================================
# Helper Functions
# =============================================================================


def load_task_app(app_path: str) -> "TaskApp":
    """TaskApp 인스턴스 로드

    Args:
        app_path: "module.path:variable" 형식 (예: "myapp.tasks:task_app")

    Returns:
        TaskApp 인스턴스
    """
    from ..app import TaskApp

    if ":" not in app_path:
        raise click.ClickException(
            f"Invalid app path: {app_path}\n"
            "Expected format: 'module.path:variable' (e.g., 'myapp.tasks:task_app')"
        )

    module_path, var_name = app_path.rsplit(":", 1)

    # 파일 경로인 경우 모듈 경로로 변환
    if "/" in module_path or module_path.endswith(".py"):
        module_path = module_path.replace("/", ".").replace(".py", "")

    try:
        # 현재 디렉토리를 sys.path에 추가
        cwd = str(Path.cwd())
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        module = importlib.import_module(module_path)
        app = getattr(module, var_name, None)

        if app is None:
            raise click.ClickException(
                f"Variable '{var_name}' not found in module '{module_path}'"
            )

        if not isinstance(app, TaskApp):
            raise click.ClickException(
                f"'{var_name}' is not a TaskApp instance, got {type(app).__name__}"
            )

        return app

    except ImportError as e:
        raise click.ClickException(f"Could not import module '{module_path}': {e}")


# =============================================================================
# CLI Group
# =============================================================================


@click.group("queue")
@click.option(
    "--app",
    "-A",
    "app_path",
    type=str,
    required=True,
    help="TaskApp path (e.g., 'myapp.tasks:task_app')",
)
@click.pass_context
def queue_cli(ctx: click.Context, app_path: str) -> None:
    """Bloom Task Queue CLI

    분산 태스크 큐를 관리합니다.

    Examples:
        # 워커 시작
        bloom queue -A myapp.tasks:task_app worker

        # 동시성 4로 워커 시작
        bloom queue -A myapp.tasks:task_app worker -c 4

        # 특정 큐만 처리
        bloom queue -A myapp.tasks:task_app worker -Q high,default

        # 큐 상태 확인
        bloom queue -A myapp.tasks:task_app inspect active

        # 큐 비우기
        bloom queue -A myapp.tasks:task_app purge -Q default
    """
    ctx.ensure_object(dict)
    ctx.obj["app_path"] = app_path


# =============================================================================
# Worker Command
# =============================================================================


@queue_cli.command("worker")
@click.option(
    "--concurrency",
    "-c",
    type=int,
    default=1,
    help="Number of concurrent workers (default: 1)",
)
@click.option(
    "--queues",
    "-Q",
    type=str,
    default="default",
    help="Comma-separated list of queues to consume (default: 'default')",
)
@click.option(
    "--prefetch",
    "-p",
    type=int,
    default=1,
    help="Prefetch count (default: 1)",
)
@click.option(
    "--loglevel",
    "-l",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    default="INFO",
    help="Log level (default: INFO)",
)
@click.option(
    "--logfile",
    "-f",
    type=click.Path(),
    default=None,
    help="Log file path",
)
@click.pass_context
def worker_cmd(
    ctx: click.Context,
    concurrency: int,
    queues: str,
    prefetch: int,
    loglevel: str,
    logfile: str | None,
) -> None:
    """Start a task worker

    Examples:
        bloom queue -A myapp:task_app worker
        bloom queue -A myapp:task_app worker -c 4 -Q high,default
    """
    import logging

    from ..worker import Worker, WorkerConfig

    # 로깅 설정
    log_handlers: list[logging.Handler] = [logging.StreamHandler()]
    if logfile:
        log_handlers.append(logging.FileHandler(logfile))

    logging.basicConfig(
        level=getattr(logging, loglevel),
        format="[%(asctime)s: %(levelname)s/%(name)s] %(message)s",
        handlers=log_handlers,
    )

    # TaskApp 로드
    app_path = ctx.obj["app_path"]
    click.echo(f"Loading TaskApp from '{app_path}'...")

    task_app = load_task_app(app_path)

    # 큐 목록 파싱
    queue_list = [q.strip() for q in queues.split(",") if q.strip()]

    click.echo(f"\n-------------- Bloom Task Queue v0.1.0 ---------------")
    click.echo(f"--- ** ----------- {task_app.name} ----------- ** ----")
    click.echo(f"")
    click.echo(f"Configuration:")
    click.echo(f"  . app:        {app_path}")
    click.echo(f"  . concurrency: {concurrency}")
    click.echo(f"  . queues:     {', '.join(queue_list)}")
    click.echo(f"  . prefetch:   {prefetch}")
    click.echo(f"")
    click.echo(f"Tasks:")
    for task_name in task_app.registry.get_all():
        click.echo(f"  . {task_name}")
    click.echo(f"")
    click.echo(f"[INFO] Connected to broker")
    click.echo(f"[INFO] Starting {concurrency} worker(s)...")
    click.echo(f"")

    # 워커 설정
    config = WorkerConfig(
        concurrency=concurrency,
        queues=queue_list,
        prefetch_count=prefetch,
    )

    # 워커 실행
    worker = Worker(task_app, config=config)

    try:
        asyncio.run(_run_worker(worker))
    except KeyboardInterrupt:
        click.echo("\nWorker stopped.")


async def _run_worker(worker: Any) -> None:
    """워커 실행 (비동기)"""
    await worker.start()


# =============================================================================
# Inspect Command
# =============================================================================


@queue_cli.group("inspect")
@click.pass_context
def inspect_cmd(ctx: click.Context) -> None:
    """Inspect workers and queues"""
    pass


@inspect_cmd.command("active")
@click.pass_context
def inspect_active(ctx: click.Context) -> None:
    """List active tasks"""
    app_path = ctx.obj["app_path"]
    task_app = load_task_app(app_path)

    click.echo("Active tasks:")
    click.echo("  (Not implemented - requires backend support)")


@inspect_cmd.command("scheduled")
@click.pass_context
def inspect_scheduled(ctx: click.Context) -> None:
    """List scheduled tasks"""
    app_path = ctx.obj["app_path"]
    task_app = load_task_app(app_path)

    click.echo("Scheduled tasks:")
    click.echo("  (Not implemented - requires backend support)")


@inspect_cmd.command("stats")
@click.pass_context
def inspect_stats(ctx: click.Context) -> None:
    """Show worker stats"""
    app_path = ctx.obj["app_path"]
    task_app = load_task_app(app_path)

    click.echo("Worker stats:")
    click.echo("  (Not implemented - requires monitoring support)")


@inspect_cmd.command("registered")
@click.pass_context
def inspect_registered(ctx: click.Context) -> None:
    """List registered tasks"""
    app_path = ctx.obj["app_path"]
    task_app = load_task_app(app_path)

    click.echo("Registered tasks:")
    for name, task in task_app.registry.get_all().items():
        click.echo(f"  {name}")
        click.echo(f"    queue: {task.queue}")
        click.echo(f"    retry: {task.retry}")
        click.echo(f"    timeout: {task.timeout}")


# =============================================================================
# Purge Command
# =============================================================================


@queue_cli.command("purge")
@click.option(
    "--queue",
    "-Q",
    type=str,
    default="default",
    help="Queue to purge (default: 'default')",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation",
)
@click.pass_context
def purge_cmd(ctx: click.Context, queue: str, force: bool) -> None:
    """Purge a queue (remove all messages)

    Examples:
        bloom queue -A myapp:task_app purge -Q default
        bloom queue -A myapp:task_app purge -Q high -f
    """
    app_path = ctx.obj["app_path"]
    task_app = load_task_app(app_path)

    if not force:
        if not click.confirm(f"Are you sure you want to purge queue '{queue}'?"):
            click.echo("Aborted.")
            return

    async def do_purge() -> int:
        if task_app.broker:
            await task_app.broker.connect()
            count = await task_app.broker.purge_queue(queue)
            await task_app.broker.disconnect()
            return count
        return 0

    count = asyncio.run(do_purge())
    click.echo(f"Purged {count} messages from queue '{queue}'")


# =============================================================================
# Send Command (for testing)
# =============================================================================


@queue_cli.command("call")
@click.argument("task_name")
@click.option(
    "--args",
    "-a",
    type=str,
    default="",
    help="Task arguments (JSON format)",
)
@click.option(
    "--kwargs",
    "-k",
    type=str,
    default="{}",
    help="Task keyword arguments (JSON format)",
)
@click.option(
    "--countdown",
    "-c",
    type=float,
    default=None,
    help="Delay in seconds",
)
@click.option(
    "--queue",
    "-Q",
    type=str,
    default=None,
    help="Target queue",
)
@click.pass_context
def call_cmd(
    ctx: click.Context,
    task_name: str,
    args: str,
    kwargs: str,
    countdown: float | None,
    queue: str | None,
) -> None:
    """Call a task by name

    Examples:
        bloom queue -A myapp:task_app call myapp.tasks.send_email -a '["user@example.com"]'
        bloom queue -A myapp:task_app call myapp.tasks.process -k '{"data": "test"}' -c 10
    """
    import json

    app_path = ctx.obj["app_path"]
    task_app = load_task_app(app_path)

    # 인자 파싱
    try:
        task_args = tuple(json.loads(args)) if args else ()
    except json.JSONDecodeError:
        raise click.ClickException(f"Invalid JSON for args: {args}")

    try:
        task_kwargs = json.loads(kwargs)
    except json.JSONDecodeError:
        raise click.ClickException(f"Invalid JSON for kwargs: {kwargs}")

    async def send_task() -> str:
        if task_app.broker:
            await task_app.broker.connect()

        result = await task_app.send_task(
            task_name,
            args=task_args,
            kwargs=task_kwargs,
            countdown=countdown,
            queue=queue,
        )

        if task_app.broker:
            await task_app.broker.disconnect()

        return result.task_id

    task_id = asyncio.run(send_task())
    click.echo(f"Task sent: {task_name}")
    click.echo(f"Task ID: {task_id}")


# =============================================================================
# Result Command
# =============================================================================


@queue_cli.command("result")
@click.argument("task_id")
@click.option(
    "--wait",
    "-w",
    is_flag=True,
    help="Wait for result",
)
@click.option(
    "--timeout",
    "-t",
    type=float,
    default=10.0,
    help="Wait timeout in seconds (default: 10)",
)
@click.pass_context
def result_cmd(
    ctx: click.Context,
    task_id: str,
    wait: bool,
    timeout: float,
) -> None:
    """Get task result

    Examples:
        bloom queue -A myapp:task_app result abc123
        bloom queue -A myapp:task_app result abc123 --wait -t 30
    """
    import json

    app_path = ctx.obj["app_path"]
    task_app = load_task_app(app_path)

    async def get_result() -> Any:
        if task_app.backend:
            await task_app.backend.connect()

            if wait:
                result = await task_app.backend.wait_for_result(
                    task_id, timeout=timeout
                )
            else:
                result = await task_app.backend.get_result(task_id)

            await task_app.backend.disconnect()
            return result
        return None

    result = asyncio.run(get_result())

    if result is None:
        click.echo(f"No result found for task {task_id}")
    else:
        click.echo(f"Task ID: {result.task_id}")
        click.echo(f"Status: {result.status.value}")
        if result.is_successful():
            click.echo(f"Result: {json.dumps(result.result, default=str)}")
        elif result.is_failed():
            click.echo(f"Error: {result.error}")
            if result.traceback:
                click.echo(f"Traceback:\n{result.traceback}")
