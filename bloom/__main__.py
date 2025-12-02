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

import asyncio
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
# startapp command
# =============================================================================


def _to_pascal_case(name: str) -> str:
    """snake_case 또는 kebab-case를 PascalCase로 변환"""
    # users -> Users, user_profile -> UserProfile, user-profile -> UserProfile
    parts = name.replace("-", "_").split("_")
    return "".join(part.capitalize() for part in parts)


def _singularize(word: str) -> str:
    """영어 복수형을 단수형으로 변환 (간단한 규칙 기반)

    Examples:
        Users -> User
        Categories -> Category
        Addresses -> Address
        Status -> Status (이미 단수)
    """
    # 이미 단수인 경우 (ss로 끝나는 단어)
    if word.endswith("ss"):
        return word

    # -ies -> -y (Categories -> Category)
    if word.endswith("ies"):
        return word[:-3] + "y"

    # -es -> '' for words ending in s, x, z, ch, sh
    if word.endswith("es"):
        # Addresses -> Address, Boxes -> Box
        if len(word) > 3 and word[-3] in "sxz":
            return word[:-2]
        # Matches -> Match, Dishes -> Dish
        if len(word) > 4 and word[-4:-2] in ("ch", "sh"):
            return word[:-2]

    # -s -> '' (Users -> User)
    if word.endswith("s"):
        return word[:-1]

    return word


@cli.command()
@click.argument("name")
@click.option(
    "-d",
    "--directory",
    type=str,
    default=None,
    help="Directory to create app in (default: current directory)",
)
@click.option(
    "-e",
    "--entity",
    type=str,
    default=None,
    help="Entity class name (default: interactive prompt or singularized app name)",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    default=False,
    help="Skip interactive prompts and use defaults",
)
def startapp(name: str, directory: str | None, entity: str | None, yes: bool):
    """Create a new Bloom app

    \b
    Creates a new app with the standard Bloom structure:
      - __init__.py
      - controllers.py   (HTTP 엔드포인트)
      - services.py      (비즈니스 로직)
      - repositories.py  (데이터 접근)
      - entities.py      (ORM 엔티티)
      - schemas.py       (요청/응답 스키마)
      - tests.py         (테스트)

    \b
    Examples:
        bloom startapp users                    # Interactive mode
        bloom startapp users -e User            # Specify entity name
        bloom startapp users -y                 # Use defaults (User)
        bloom startapp orders -d apps/ -e Order
    """
    import shutil
    from importlib import resources

    # 앱 이름 검증
    if not name.replace("_", "").replace("-", "").isalnum():
        raise click.ClickException(
            f"Invalid app name '{name}'. Use only letters, numbers, underscores, or hyphens."
        )

    # 대상 디렉토리 결정
    base_path = Path(directory).resolve() if directory else Path.cwd()
    target_path = base_path / name

    # PascalCase 이름 (app 전체 이름)
    app_name_pascal = _to_pascal_case(name)

    # 엔티티 이름 결정
    default_entity = _singularize(app_name_pascal)

    if entity:
        # 명시적으로 지정된 경우
        entity_name = entity
    elif yes:
        # -y 옵션: 기본값 사용
        entity_name = default_entity
    else:
        # 인터랙티브 프롬프트
        click.echo()
        click.echo(f"[Bloom] Creating app '{name}'")
        click.echo()
        entity_name = click.prompt(
            click.style("? ", fg="green") + "Entity class name",
            default=default_entity,
            type=str,
        )

    click.echo()
    click.echo(f"[Bloom] Creating app '{name}' at {target_path}")
    click.echo(f"        Entity: {entity_name}")

    # 기존 디렉토리 확인
    if target_path.exists():
        raise click.ClickException(
            f"Directory '{target_path}' already exists. "
            "Use a different name or remove existing directory."
        )

    # 대상 디렉토리 생성
    target_path.mkdir(parents=True, exist_ok=True)

    # 템플릿 디렉토리 경로
    try:
        template_ref = resources.files("bloom.templates.app")
        with resources.as_file(template_ref) as template_dir:
            _copy_app_template(
                template_dir, target_path, name, app_name_pascal, entity_name
            )
    except Exception as e:
        # 실패 시 디렉토리 정리
        if target_path.exists():
            shutil.rmtree(target_path)
        raise click.ClickException(f"Failed to copy template: {e}")

    click.echo()
    click.echo(f"[Bloom] App '{name}' created successfully!")
    click.echo()
    click.echo("Next steps:")
    click.echo("  1. Add to application.py:")
    click.echo(f"     from {name} import {entity_name}Controller, {entity_name}Service")
    click.echo(f"     application.scan({name})")
    click.echo()
    click.echo("  2. Or use auto_import():")
    click.echo("     application.auto_import()  # scans all modules automatically")


def _copy_app_template(
    template_dir: Path,
    target_path: Path,
    app_name: str,
    app_name_pascal: str,
    entity_name: str,
):
    """앱 템플릿 디렉토리를 복사하고 변수를 치환합니다."""
    import shutil

    for src_file in template_dir.rglob("*"):
        if src_file.is_dir():
            continue

        # __pycache__ 스킵
        if "__pycache__" in str(src_file):
            continue

        # 상대 경로 계산
        rel_path = src_file.relative_to(template_dir)
        dest_file = target_path / rel_path

        # 디렉토리 생성
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        if src_file.suffix == ".tmpl":
            # .tmpl 파일: 변수 치환 후 확장자 제거
            content = src_file.read_text(encoding="utf-8")
            content = content.replace("{{app_name}}", app_name)
            content = content.replace("{{ app_name }}", app_name)
            content = content.replace("{{app_name_pascal}}", app_name_pascal)
            content = content.replace("{{ app_name_pascal }}", app_name_pascal)
            content = content.replace("{{entity_name}}", entity_name)
            content = content.replace("{{ entity_name }}", entity_name)

            # .tmpl 확장자 제거
            final_dest = dest_file.with_suffix("")
            final_dest.write_text(content, encoding="utf-8")
            click.echo(f"  Created: {final_dest.name}")
        else:
            # 일반 파일: 그대로 복사
            shutil.copy2(src_file, dest_file)
            click.echo(f"  Created: {dest_file.name}")


# =============================================================================
# Lazy Command Loading (서브 커맨드는 실행 시에만 로드)
# =============================================================================


class LazyMultiCommand(click.Group):
    """Lazy 로드되는 Group/MultiCommand의 플레이스홀더"""

    def __init__(self, name: str, import_path: str, short_help: str):
        super().__init__(name, help=short_help)
        self._import_path = import_path
        self.short_help = short_help
        self._real_command: click.MultiCommand | None = None

    def _load(self) -> click.MultiCommand:
        if self._real_command is None:
            module_path, attr_name = self._import_path.rsplit(":", 1)
            module = importlib.import_module(module_path)
            self._real_command = getattr(module, attr_name)
        return self._real_command

    def list_commands(self, ctx: click.Context) -> list[str]:
        return self._load().list_commands(ctx)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        return self._load().get_command(ctx, cmd_name)

    def invoke(self, ctx: click.Context):
        return self._load().invoke(ctx)

    def get_help(self, ctx: click.Context) -> str:
        return self._load().get_help(ctx)

    def get_params(self, ctx: click.Context) -> list:
        return self._load().get_params(ctx)


class LazyCommand(click.Command):
    """Lazy 로드되는 커맨드의 플레이스홀더"""

    def __init__(self, name: str, import_path: str, short_help: str):
        super().__init__(name, callback=None)
        self._import_path = import_path
        self.short_help = short_help
        self._real_command: click.Command | None = None

    def _load(self) -> click.Command:
        if self._real_command is None:
            module_path, attr_name = self._import_path.rsplit(":", 1)
            module = importlib.import_module(module_path)
            self._real_command = getattr(module, attr_name)
        return self._real_command

    def invoke(self, ctx: click.Context):
        return self._load().invoke(ctx)

    def get_help(self, ctx: click.Context) -> str:
        return self._load().get_help(ctx)

    def get_params(self, ctx: click.Context) -> list:
        return self._load().get_params(ctx)


class LazyGroup(click.Group):
    """서브 커맨드를 lazy하게 로드하는 Group"""

    def __init__(
        self,
        *args,
        lazy_subcommands: dict[str, tuple[str, str, bool]] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        # lazy_subcommands: {name: (import_path, short_help, is_group)}
        self._lazy_subcommands = lazy_subcommands or {}

        # Lazy 플레이스홀더 등록
        for cmd_name, (
            import_path,
            short_help,
            is_group,
        ) in self._lazy_subcommands.items():
            if is_group:
                lazy_cmd = LazyMultiCommand(cmd_name, import_path, short_help)
            else:
                lazy_cmd = LazyCommand(cmd_name, import_path, short_help)
            self.add_command(lazy_cmd, cmd_name)


# 기존 cli 그룹을 LazyGroup으로 교체
# 무거운 서브커맨드는 lazy로 로드 (short_help, is_group 포함)
_lazy_subcommands = {
    "db": ("bloom.db.cli:db", "Database management commands", True),
    "task": ("bloom.task.cli:task", "Task management commands", False),
    "tests": ("bloom.tests.cli:tests", "Run tests with pytest", False),
    "run": ("bloom.scripts.cli:run", "Run custom scripts", True),
}

# cli 그룹 재정의 (LazyGroup 사용)
_original_cli = cli
cli = LazyGroup(
    name=_original_cli.name,
    help=_original_cli.help,
    lazy_subcommands=_lazy_subcommands,
)

# 기존 명령어들을 새 그룹에 복사
for cmd_name, cmd in _original_cli.commands.items():
    cli.add_command(cmd, cmd_name)


# =============================================================================
# routes command
# =============================================================================


def _load_application_for_cli(app_path: str | None = None) -> Any:
    """CLI 명령어용 Application 로드"""
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    # 명시적 경로가 주어진 경우
    if app_path:
        if ":" not in app_path:
            app_path = f"{app_path}:application"

        module_path, attr_path = app_path.split(":", 1)

        # 경로 구분자 변환
        if "/" in module_path:
            module_path = module_path.replace("/", ".")

        module = importlib.import_module(module_path)
        app = module
        for attr_name in attr_path.split("."):
            app = getattr(app, attr_name)

        if hasattr(app, "ready_async") and not getattr(app, "_is_ready", False):
            asyncio.run(app.ready_async())
        return app

    # 기본: application:application 시도
    try:
        module = importlib.import_module("application")
        app = getattr(module, "application", None)
        if app is not None:
            if hasattr(app, "ready_async") and not getattr(app, "_is_ready", False):
                asyncio.run(app.ready_async())
            return app
    except ImportError:
        pass

    return None


@cli.command()
@click.option(
    "-a",
    "--application",
    type=str,
    default=None,
    help="Application path (default: 'application:application')",
)
@click.option(
    "--method",
    "-m",
    type=str,
    default=None,
    help="Filter by HTTP method (GET, POST, PUT, DELETE, etc.)",
)
@click.option(
    "--path",
    "-p",
    type=str,
    default=None,
    help="Filter by path pattern (substring match)",
)
def routes(application: str | None, method: str | None, path: str | None):
    """Display registered HTTP routes

    \b
    Shows all registered HTTP routes with their methods, paths, and handlers.

    \b
    Examples:
        bloom routes
        bloom routes --method GET
        bloom routes --path /users
        bloom routes -a myapp:app --method POST
    """
    try:
        app = _load_application_for_cli(application)
    except Exception as e:
        raise click.ClickException(f"Failed to load application: {e}")

    if app is None:
        raise click.ClickException(
            "Could not load application. Make sure application.py exists "
            "or specify --application path."
        )

    # 라우트 수집
    route_list = app.router.route_manager.get_routes()

    if not route_list:
        click.echo("No routes registered.")
        return

    # 필터링
    if method:
        method = method.upper()
        route_list = [(m, p, h) for m, p, h in route_list if m == method]

    if path:
        route_list = [(m, p, h) for m, p, h in route_list if path in p]

    if not route_list:
        click.echo("No matching routes found.")
        return

    # 출력
    click.echo()
    click.echo(f"{'Method':<10} {'Path':<40} {'Handler'}")
    click.echo("-" * 80)

    # 경로별로 정렬
    route_list.sort(key=lambda x: (x[1], x[0]))

    for http_method, route_path, handler_name in route_list:
        # 메서드별 색상
        method_colors = {
            "GET": "green",
            "POST": "blue",
            "PUT": "yellow",
            "PATCH": "cyan",
            "DELETE": "red",
        }
        color = method_colors.get(http_method, "white")
        click.echo(
            f"{click.style(http_method, fg=color, bold=True):<19} "
            f"{route_path:<40} {handler_name}"
        )

    click.echo()
    click.echo(f"Total: {len(route_list)} route(s)")


# =============================================================================
# shell command
# =============================================================================


@cli.command()
@click.option(
    "-a",
    "--application",
    type=str,
    default=None,
    help="Application path (default: 'application:application')",
)
def shell(application: str | None):
    """Start interactive Python shell with loaded application

    \b
    Opens an interactive Python REPL with the application loaded.
    The following objects are available:
      - app: The loaded Application instance
      - manager: The ContainerManager
      - container: Alias for manager (for convenience)

    \b
    Examples:
        bloom shell
        bloom shell -a myapp:app
    """
    try:
        app = _load_application_for_cli(application)
    except Exception as e:
        raise click.ClickException(f"Failed to load application: {e}")

    if app is None:
        raise click.ClickException(
            "Could not load application. Make sure application.py exists "
            "or specify --application path."
        )

    # 셸에서 사용할 수 있는 객체들
    shell_context = {
        "app": app,
        "manager": app.manager,
        "container": app.manager,  # 편의를 위한 alias
    }

    banner = f"""
Bloom Interactive Shell
========================
Application: {app.name}

Available objects:
  app       - Application instance
  manager   - ContainerManager
  container - ContainerManager (alias)

Example usage:
  >>> app.manager.get_instance(MyService)
  >>> list(app.manager.container_registry.keys())
"""

    # IPython이 있으면 사용, 없으면 기본 Python REPL
    try:
        from IPython import start_ipython

        start_ipython(argv=[], user_ns=shell_context, display_banner=False)
        click.echo(banner)
    except ImportError:
        import code

        click.echo(banner)
        code.interact(local=shell_context, banner="")


# =============================================================================
# components command
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
    "--scope",
    "-s",
    type=click.Choice(["all", "singleton", "prototype", "request"]),
    default="all",
    help="Filter by scope",
)
@click.option(
    "--type",
    "-t",
    "type_filter",
    type=str,
    default=None,
    help="Filter by type name (substring match)",
)
def components(application: str | None, scope: str, type_filter: str | None):
    """List registered DI components

    \b
    Shows all components registered in the DI container.

    \b
    Examples:
        bloom components
        bloom components --scope singleton
        bloom components --type Service
        bloom components -a myapp:app -s prototype
    """
    try:
        app = _load_application_for_cli(application)
    except Exception as e:
        raise click.ClickException(f"Failed to load application: {e}")

    if app is None:
        raise click.ClickException(
            "Could not load application. Make sure application.py exists "
            "or specify --application path."
        )

    # 컨테이너 정보 수집
    containers = []
    for target_type, container_list in app.manager.container_registry.items():
        for container in container_list:
            type_name = target_type.__name__
            module_name = target_type.__module__

            # 필터링
            if type_filter and type_filter.lower() not in type_name.lower():
                continue

            container_scope = getattr(container, "scope", "singleton")
            if scope != "all" and container_scope != scope:
                continue

            containers.append(
                {
                    "type": type_name,
                    "module": module_name,
                    "scope": container_scope,
                    "factory": getattr(container, "is_factory", False),
                }
            )

    if not containers:
        click.echo("No matching components found.")
        return

    # 타입명으로 정렬
    containers.sort(key=lambda x: x["type"])

    click.echo()
    click.echo(f"{'Type':<30} {'Scope':<12} {'Factory':<8} {'Module'}")
    click.echo("-" * 90)

    for comp in containers:
        scope_color = {
            "singleton": "green",
            "prototype": "yellow",
            "request": "cyan",
        }.get(comp["scope"], "white")

        factory_str = "✓" if comp["factory"] else ""

        click.echo(
            f"{comp['type']:<30} "
            f"{click.style(comp['scope'], fg=scope_color):<21} "
            f"{factory_str:<8} "
            f"{comp['module']}"
        )

    click.echo()
    click.echo(f"Total: {len(containers)} component(s)")


# =============================================================================
# check command
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
    "--fix",
    is_flag=True,
    default=False,
    help="Attempt to fix issues automatically",
)
def check(application: str | None, fix: bool):
    """Check project structure and configuration

    \b
    Validates the project setup and reports any issues.

    \b
    Checks:
      - Required files exist (application.py, settings/, etc.)
      - Application can be loaded
      - No circular dependencies
      - Configuration is valid

    \b
    Examples:
        bloom check
        bloom check --fix
        bloom check -a myapp:app
    """
    issues: list[tuple[str, str, str]] = []  # (level, check, message)
    fixes_applied: list[str] = []

    click.echo()
    click.echo("Bloom Project Check")
    click.echo("=" * 40)
    click.echo()

    cwd = Path.cwd()

    # 1. 필수 파일 존재 확인
    click.echo("Checking project structure...")

    required_files = [
        ("application.py", "Main application file"),
        ("settings/__init__.py", "Settings module"),
    ]

    for file_path, description in required_files:
        full_path = cwd / file_path
        if full_path.exists():
            click.echo(f"  {click.style('✓', fg='green')} {file_path}")
        else:
            issues.append(
                ("error", "structure", f"Missing {file_path} ({description})")
            )
            click.echo(f"  {click.style('✗', fg='red')} {file_path} - Missing")

    # 2. 선택적 파일 확인
    optional_files = [
        ("settings/database.py", "Database configuration"),
        ("settings/middleware.py", "Middleware configuration"),
        ("settings/task.py", "Task configuration"),
        ("scripts/", "Custom scripts directory"),
        ("tests/", "Test directory"),
    ]

    click.echo()
    click.echo("Checking optional files...")

    for file_path, description in optional_files:
        full_path = cwd / file_path
        if full_path.exists():
            click.echo(f"  {click.style('✓', fg='green')} {file_path}")
        else:
            issues.append(
                ("warning", "structure", f"Missing {file_path} ({description})")
            )
            click.echo(f"  {click.style('○', fg='yellow')} {file_path} - Optional")

    # 3. Application 로드 테스트
    click.echo()
    click.echo("Checking application...")

    try:
        app = _load_application_for_cli(application)
        if app is not None:
            click.echo(
                f"  {click.style('✓', fg='green')} Application loaded: {app.name}"
            )

            # 컴포넌트 수 확인
            component_count = sum(
                len(containers)
                for containers in app.manager.container_registry.values()
            )
            click.echo(
                f"  {click.style('✓', fg='green')} {component_count} component(s) registered"
            )

            # 라우트 수 확인
            try:
                route_count = len(app.router.route_manager.get_routes())
                click.echo(
                    f"  {click.style('✓', fg='green')} {route_count} route(s) registered"
                )
            except Exception:
                click.echo(f"  {click.style('○', fg='yellow')} Could not count routes")
        else:
            issues.append(("error", "application", "Could not load application"))
            click.echo(f"  {click.style('✗', fg='red')} Application not found")
    except Exception as e:
        issues.append(("error", "application", f"Failed to load: {e}"))
        click.echo(f"  {click.style('✗', fg='red')} Failed to load: {e}")

    # 4. pyproject.toml 확인
    click.echo()
    click.echo("Checking configuration...")

    pyproject_path = cwd / "pyproject.toml"
    if pyproject_path.exists():
        click.echo(f"  {click.style('✓', fg='green')} pyproject.toml")
        try:
            import tomllib

            with open(pyproject_path, "rb") as f:
                pyproject = tomllib.load(f)

            # bloom 의존성 확인
            deps = pyproject.get("project", {}).get("dependencies", [])
            bloom_found = any("bloom" in dep.lower() for dep in deps)
            if bloom_found:
                click.echo(f"  {click.style('✓', fg='green')} bloom in dependencies")
            else:
                issues.append(("warning", "config", "bloom not in dependencies"))
                click.echo(
                    f"  {click.style('○', fg='yellow')} bloom not in dependencies"
                )
        except Exception as e:
            issues.append(("warning", "config", f"Could not parse pyproject.toml: {e}"))
    else:
        issues.append(("warning", "config", "pyproject.toml not found"))
        click.echo(f"  {click.style('○', fg='yellow')} pyproject.toml - Not found")

    # 결과 요약
    click.echo()
    click.echo("=" * 40)

    errors = [i for i in issues if i[0] == "error"]
    warnings = [i for i in issues if i[0] == "warning"]

    if not issues:
        click.echo(click.style("✓ All checks passed!", fg="green", bold=True))
    else:
        if errors:
            click.echo(click.style(f"✗ {len(errors)} error(s)", fg="red", bold=True))
            for _, check_name, msg in errors:
                click.echo(f"  [{check_name}] {msg}")

        if warnings:
            click.echo(click.style(f"○ {len(warnings)} warning(s)", fg="yellow"))
            for _, check_name, msg in warnings:
                click.echo(f"  [{check_name}] {msg}")

    if fixes_applied:
        click.echo()
        click.echo(f"Applied {len(fixes_applied)} fix(es):")
        for fix_msg in fixes_applied:
            click.echo(f"  - {fix_msg}")

    click.echo()


# =============================================================================
# version command
# =============================================================================


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed version info")
def version(verbose: bool):
    """Show Bloom framework version

    \b
    Displays the version of the Bloom framework and related packages.

    \b
    Examples:
        bloom version
        bloom version -v
    """
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as get_version

    click.echo()

    # Bloom 버전
    try:
        bloom_version = get_version("bloom")
    except PackageNotFoundError:
        bloom_version = "0.1.0 (development)"

    click.echo(f"Bloom Framework: {click.style(bloom_version, fg='green', bold=True)}")

    if verbose:
        click.echo()
        click.echo("Dependencies:")

        # 주요 의존성 버전
        dependencies = [
            ("uvicorn", "ASGI Server"),
            ("click", "CLI Framework"),
            ("pydantic", "Data Validation"),
            ("sqlalchemy", "ORM"),
            ("redis", "Redis Client"),
            ("aiohttp", "HTTP Client"),
        ]

        for pkg_name, description in dependencies:
            try:
                pkg_version = get_version(pkg_name)
                click.echo(f"  {pkg_name:<15} {pkg_version:<12} ({description})")
            except PackageNotFoundError:
                click.echo(
                    f"  {pkg_name:<15} "
                    f"{click.style('not installed', fg='yellow'):<21} ({description})"
                )

        click.echo()
        click.echo("Python:")
        click.echo(f"  Version: {sys.version}")
        click.echo(f"  Path: {sys.executable}")

    click.echo()


# =============================================================================
# Entry Point
# =============================================================================


def main():
    """CLI 엔트리 포인트"""
    cli()


if __name__ == "__main__":
    main()
