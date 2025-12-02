"""Script Registry - 스크립트 자동 발견 및 관리

프로젝트의 scripts/ 디렉토리에서 @script 데코레이터가 붙은
함수들을 자동으로 발견하여 CLI에 등록합니다.

스캔 경로:
  - scripts/          (프로젝트 루트)
  - */scripts/        (앱별 스크립트)
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from .decorator import get_registered_scripts, clear_registry

if TYPE_CHECKING:
    from bloom.application import Application


class ScriptRegistry:
    """스크립트 자동 발견 및 관리 클래스"""

    def __init__(self, base_dir: Path | None = None):
        """
        Args:
            base_dir: 기본 디렉토리 (기본값: cwd)
        """
        self._base_dir = base_dir or Path.cwd()
        self._discovered = False

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _get_script_dirs(self) -> list[Path]:
        """스크립트 디렉토리 목록 반환
        
        Returns:
            스캔할 디렉토리 목록:
              - scripts/       (루트)
              - */scripts/     (앱별)
        """
        script_dirs: list[Path] = []
        
        # 1. 루트 scripts/ 디렉토리
        root_scripts = self._base_dir / "scripts"
        if root_scripts.exists() and root_scripts.is_dir():
            script_dirs.append(root_scripts)
        
        # 2. */scripts/ 패턴 (앱별 스크립트)
        for subdir in self._base_dir.iterdir():
            if not subdir.is_dir():
                continue
            # 숨김 디렉토리, __pycache__ 등 제외
            if subdir.name.startswith((".", "_")):
                continue
            # 특수 디렉토리 제외
            if subdir.name in ("venv", "env", "node_modules", ".git"):
                continue
            
            app_scripts = subdir / "scripts"
            if app_scripts.exists() and app_scripts.is_dir():
                script_dirs.append(app_scripts)
        
        return script_dirs

    def discover(self) -> dict[str, click.Command]:
        """scripts/ 디렉토리들에서 스크립트 자동 발견

        Returns:
            발견된 스크립트들의 딕셔너리 {name: Command}
        """
        script_dirs = self._get_script_dirs()
        
        if not script_dirs:
            return {}

        # 레지스트리 초기화 (중복 방지)
        clear_registry()

        # base_dir을 sys.path에 추가
        base_dir_str = str(self._base_dir)
        if base_dir_str not in sys.path:
            sys.path.insert(0, base_dir_str)

        # 각 scripts 디렉토리 스캔
        for scripts_dir in script_dirs:
            self._scan_scripts_dir(scripts_dir)

        self._discovered = True
        return get_registered_scripts()

    def _scan_scripts_dir(self, scripts_dir: Path) -> None:
        """하나의 scripts 디렉토리 스캔"""
        # 모듈 경로 계산 (base_dir 기준 상대 경로)
        try:
            rel_path = scripts_dir.relative_to(self._base_dir)
            # users/scripts -> users.scripts
            module_prefix = ".".join(rel_path.parts)
        except ValueError:
            module_prefix = "scripts"

        # 모든 .py 파일 스캔
        for script_file in scripts_dir.glob("*.py"):
            if script_file.name.startswith("_"):
                continue

            self._import_script_module(script_file, module_prefix)

    def _import_script_module(self, script_file: Path, module_prefix: str) -> None:
        """스크립트 파일을 모듈로 임포트
        
        Args:
            script_file: 스크립트 파일 경로
            module_prefix: 모듈 경로 접두사 (예: "scripts", "users.scripts")
        """
        module_name = f"{module_prefix}.{script_file.stem}"

        try:
            # 이미 임포트된 경우 리로드
            if module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, script_file)
            if spec is None or spec.loader is None:
                return

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        except Exception as e:
            click.echo(
                click.style(
                    f"Warning: Failed to load script '{script_file.name}': {e}",
                    fg="yellow",
                ),
                err=True,
            )

    def get_commands(self) -> dict[str, click.Command]:
        """발견된 스크립트 명령어들 반환"""
        if not self._discovered:
            self.discover()
        return get_registered_scripts()

    def list_scripts(self) -> list[str]:
        """사용 가능한 스크립트 이름 목록"""
        return list(self.get_commands().keys())


def create_script_group(app: "Application | None" = None) -> click.Group:
    """스크립트 실행을 위한 Click Group 생성

    Args:
        app: Bloom Application 인스턴스 (컨테이너 접근용)

    Returns:
        scripts/ 디렉토리의 스크립트들이 등록된 Click Group
    """
    registry = ScriptRegistry()
    scripts = registry.discover()

    @click.group(invoke_without_command=True)
    @click.pass_context
    def run(ctx: click.Context) -> None:
        """커스텀 스크립트 실행

        \b
        프로젝트의 scripts/ 디렉토리에 정의된 스크립트를 실행합니다.

        \b
        Examples:
            bloom run seed_data --count 100
            bloom run cleanup --days 30
            bloom run --help
        """
        if ctx.invoked_subcommand is None:
            # 서브커맨드 없이 호출된 경우 사용 가능한 스크립트 목록 표시
            if not scripts:
                click.echo("No scripts found in scripts/ directory.")
                click.echo()
                click.echo("Create a script file like scripts/my_script.py:")
                click.echo()
                click.echo("  from bloom.scripts import script")
                click.echo("  import click")
                click.echo()
                click.echo("  @script")
                click.echo('  @click.option("--name", default="World")')
                click.echo("  def my_script(name: str, app):")
                click.echo('      click.echo(f"Hello, {name}!")')
            else:
                click.echo("Available scripts:")
                for name, cmd in scripts.items():
                    help_text = cmd.help or ""
                    first_line = help_text.split("\n")[0] if help_text else ""
                    click.echo(f"  {name:20} {first_line}")
                click.echo()
                click.echo("Run 'bloom run <script> --help' for more info.")

    # 발견된 스크립트들을 그룹에 등록
    for name, cmd in scripts.items():
        # app 주입을 위한 래퍼 생성
        run.add_command(_wrap_command_with_app(cmd, app), name=name)

    return run


def _wrap_command_with_app(
    cmd: click.Command, app: "Application | None"
) -> click.Command:
    """스크립트 명령어에 app 인자를 주입하는 래퍼 생성"""
    original_callback = cmd.callback
    original_func = getattr(cmd, "_original_func", None)

    if original_callback is None:
        return cmd

    @functools.wraps(original_callback)
    def wrapper(**kwargs: Any) -> Any:
        # app 주입
        if original_func is not None:
            # 원본 함수가 'app' 파라미터를 받는지 확인
            import inspect

            sig = inspect.signature(original_func)
            if "app" in sig.parameters:
                kwargs["app"] = app
        return original_callback(**kwargs)

    # 새 Command 생성 (기존 파라미터 유지)
    new_cmd = click.Command(
        name=cmd.name,
        callback=wrapper,
        params=cmd.params,
        help=cmd.help,
    )
    return new_cmd


import functools
from typing import Any
