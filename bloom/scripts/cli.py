"""Scripts CLI - 커스텀 스크립트 실행 명령어

bloom run <script> 형태로 프로젝트의 scripts/ 디렉토리에 있는
커스텀 스크립트를 실행합니다.
"""

from __future__ import annotations

import functools
import importlib
import inspect
import os
import sys
from pathlib import Path
from typing import Any, TYPE_CHECKING

import click

from .decorator import get_registered_scripts, clear_registry

if TYPE_CHECKING:
    from bloom.application import Application


def _load_application(app_path: str | None = None) -> "Application | None":
    """프로젝트의 Application 로드 시도
    
    Args:
        app_path: 앱 경로 (예: "application:application", "main:app")
    """
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    # 명시적 경로가 주어진 경우
    if app_path:
        try:
            if ":" not in app_path:
                app_path = f"{app_path}:application"
            
            module_path, attr_path = app_path.split(":", 1)
            
            # 경로 구분자 변환: backend/application -> backend.application
            if "/" in module_path:
                module_path = module_path.replace("/", ".")
            
            module = importlib.import_module(module_path)
            app = module
            for attr_name in attr_path.split("."):
                app = getattr(app, attr_name)
            
            if app is not None:
                if hasattr(app, "ready") and not getattr(app, "_is_ready", False):
                    app.ready()
                return app
        except (ImportError, AttributeError) as e:
            click.echo(f"Warning: Failed to load application '{app_path}': {e}", err=True)
            return None

    # 기본: application:application 시도
    try:
        module = importlib.import_module("application")
        app = getattr(module, "application", None)
        if app is not None:
            # ready() 호출하여 초기화
            if hasattr(app, "ready") and not getattr(app, "_is_ready", False):
                app.ready()
            return app
    except ImportError:
        pass

    return None


def _discover_scripts() -> dict[str, click.Command]:
    """scripts/ 디렉토리에서 스크립트 발견"""
    from .registry import ScriptRegistry

    registry = ScriptRegistry()
    return registry.discover()


def _inject_dependencies(instance: Any, app: "Application | None") -> None:
    """클래스 인스턴스에 DI 주입 수행"""
    if app is None:
        return

    import typing
    from bloom.core.lazy import is_lazy_wrapper_type, get_lazy_inner_type

    # 타입 힌트에서 필드 추출
    hints = (
        typing.get_type_hints(type(instance))
        if hasattr(type(instance), "__annotations__")
        else {}
    )

    for field_name, field_type in hints.items():
        # 이미 값이 있으면 스킵
        if (
            hasattr(instance, field_name)
            and getattr(instance, field_name, None) is not None
        ):
            continue

        # name, handle 등 예약어 스킵
        if field_name in ("name", "handle"):
            continue

        # 기본 타입 스킵
        if field_type in (str, int, float, bool, None, type(None)):
            continue

        # Lazy[T] 타입 처리
        actual_type = field_type
        if is_lazy_wrapper_type(field_type):
            inner = get_lazy_inner_type(field_type)
            if inner is not None:
                actual_type = inner

        try:
            # DI 컨테이너에서 의존성 획득
            dependency = app.manager.get_instance(actual_type)
            if dependency is not None:
                setattr(instance, field_name, dependency)
        except Exception:
            # 의존성을 찾을 수 없으면 스킵
            pass


def _wrap_command_with_app(
    cmd: click.Command, app: "Application | None"
) -> click.Command:
    """스크립트 명령어에 app 인자를 주입하는 래퍼 생성"""
    original_callback = cmd.callback
    original_func = getattr(cmd, "_original_func", None)
    is_class_script = getattr(cmd, "_is_class_script", False)
    script_class = getattr(cmd, "_script_class", None)

    if original_callback is None:
        return cmd

    if is_class_script and script_class is not None:
        # 클래스 기반 스크립트: 인스턴스 생성 후 DI 주입
        def class_wrapper(**kwargs: Any) -> Any:
            # 인스턴스 생성
            instance = script_class()
            # DI 주입
            _inject_dependencies(instance, app)
            # handle 메서드 호출
            return instance.handle(**kwargs)

        new_cmd = click.Command(
            name=cmd.name,
            callback=class_wrapper,
            params=cmd.params,
            help=cmd.help,
        )
        return new_cmd
    else:
        # 함수 기반 스크립트: app 인자 주입
        @functools.wraps(original_callback)
        def wrapper(**kwargs: Any) -> Any:
            if original_func is not None:
                sig = inspect.signature(original_func)
                if "app" in sig.parameters:
                    kwargs["app"] = app
            return original_callback(**kwargs)

        new_cmd = click.Command(
            name=cmd.name,
            callback=wrapper,
            params=cmd.params,
            help=cmd.help,
        )
        return new_cmd


class ScriptGroup(click.Group):
    """동적으로 스크립트를 로드하는 Click Group"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # 서브커맨드 없이도 실행 가능하도록 설정
        kwargs.setdefault("invoke_without_command", True)
        super().__init__(*args, **kwargs)
        self._scripts_loaded = False
        self._app: "Application | None" = None
        self._app_path: str | None = None

    def _load_scripts(self, ctx: click.Context | None = None) -> None:
        """스크립트 로드 (지연 로딩)"""
        if self._scripts_loaded:
            return

        # Context에서 application 경로 가져오기
        app_path = None
        if ctx and ctx.parent:
            app_path = ctx.parent.params.get("application")

        # Application 로드
        self._app = _load_application(app_path)

        # 스크립트 발견
        scripts = _discover_scripts()

        # 명령어 등록
        for name, cmd in scripts.items():
            wrapped_cmd = _wrap_command_with_app(cmd, self._app)
            self.add_command(wrapped_cmd, name=name)

        self._scripts_loaded = True

    def list_commands(self, ctx: click.Context) -> list[str]:
        """사용 가능한 명령어 목록"""
        self._load_scripts(ctx)
        return super().list_commands(ctx)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """명령어 조회"""
        self._load_scripts(ctx)
        return super().get_command(ctx, cmd_name)


@click.command(cls=ScriptGroup)
@click.option(
    "-a",
    "--application",
    type=str,
    default=None,
    help="Application path (e.g., 'application:application', 'main:app')",
)
@click.pass_context
def run(ctx: click.Context, application: str | None) -> None:
    """커스텀 스크립트 실행

    \b
    프로젝트의 scripts/ 디렉토리에 정의된 스크립트를 실행합니다.

    \b
    스크립트 작성법:
        # scripts/seed_data.py
        from bloom.scripts import script
        import click

        @script
        @click.option("--count", "-c", type=int, default=10)
        def seed_data(count: int, app):
            '''테스트 데이터 시딩'''
            repo = app.container.get(UserRepository)
            for i in range(count):
                repo.save(User(name=f"User {i}"))
            click.secho(f"✓ Created {count} users", fg="green")

    \b
    스캔 경로:
        - scripts/           # 프로젝트 루트
        - */scripts/         # 앱별 스크립트 (users/scripts/, orders/scripts/ 등)

    \b
    Examples:
        bloom run                                    # 스크립트 목록
        bloom run seed_data --count 100
        bloom run -a myapp:app seed_data             # 앱 지정
        bloom run --application main:application hello
    """
    if ctx.invoked_subcommand is None:
        # 서브커맨드 없이 호출된 경우
        # 스크립트 로드
        scripts = _discover_scripts()

        if not scripts:
            click.echo("No scripts found.")
            click.echo()
            click.echo("Script directories scanned:")
            click.echo("  - scripts/        (project root)")
            click.echo("  - */scripts/      (app-specific)")
            click.echo()
            _show_example_script()
        else:
            click.echo("Available scripts:")
            click.echo()
            for name, cmd in scripts.items():
                help_text = cmd.help or ""
                first_line = help_text.split("\n")[0] if help_text else ""
                click.echo(f"  {name:20} {first_line}")
            click.echo()
            click.echo("Run 'bloom run <script> --help' for more info.")


def _show_example_script() -> None:
    """예제 스크립트 표시"""
    click.echo("Example script (scripts/hello.py):")
    click.echo()
    click.echo("  from bloom.scripts import script")
    click.echo("  import click")
    click.echo()
    click.echo("  @script")
    click.echo('  @click.option("--name", "-n", default="World")')
    click.echo("  def hello(name: str, app):")
    click.echo('      """Say hello"""')
    click.echo('      click.echo(f"Hello, {name}!")')
