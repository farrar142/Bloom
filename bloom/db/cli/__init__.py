"""Bloom DB CLI - Django-style database management commands

Usage:
    bloom db --application=myapp.module:app makemigrations [--name NAME] [--empty]
    bloom db --application=myapp.module:app migrate [--target TARGET]
    bloom db --application=myapp.module:app showmigrations
    bloom db --application=myapp.module:app sqlmigrate MIGRATION
    bloom db --application=myapp.module:app shell

Examples:
    # 앱 기반 마이그레이션 생성
    bloom db --application=examples.orm_example:app makemigrations --name create_users

    # 마이그레이션 적용
    bloom db --application=examples.orm_example:app migrate

    # 특정 마이그레이션까지 적용
    bloom db --application=examples.orm_example:app migrate --target 0003_add_email

    # 마이그레이션 상태 확인
    bloom db --application=examples.orm_example:app showmigrations

    # SQL 미리보기
    bloom db --application=examples.orm_example:app sqlmigrate 0001_create_users
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from .context import DBContext

if TYPE_CHECKING:
    from bloom.application import Application


# =============================================================================
# CLI Configuration
# =============================================================================


def find_project_root() -> Path:
    """프로젝트 루트 찾기 (pyproject.toml 위치)"""
    current = Path.cwd()

    for parent in [current] + list(current.parents):
        if (parent / "pyproject.toml").exists():
            return parent

    return current


def load_config() -> dict[str, Any]:
    """pyproject.toml에서 설정 로드"""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

    root = find_project_root()
    pyproject = root / "pyproject.toml"

    if pyproject.exists():
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
            return data.get("tool", {}).get("bloom", {}).get("db", {})

    return {}


pass_context = click.make_pass_decorator(DBContext, ensure=True)


# =============================================================================
# Application Loading
# =============================================================================


def load_application(app_path: str) -> tuple["Application", Any]:
    """
    Application 인스턴스 로드

    Args:
        app_path: "module.path:variable" 형식 (예: "examples.orm_example:app")

    Returns:
        (Application 인스턴스, 모듈) 튜플
    """
    if ":" not in app_path:
        raise click.ClickException(
            f"Invalid application path: {app_path}\n"
            "Expected format: 'module.path:variable' (e.g., 'examples.orm_example:app')"
        )

    module_path, var_name = app_path.rsplit(":", 1)

    # 파일 경로인 경우 모듈 경로로 변환
    if "/" in module_path or module_path.endswith(".py"):
        # examples/orm_example.py -> examples.orm_example
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

        from bloom.application import Application

        if not isinstance(app, Application):
            raise click.ClickException(
                f"'{var_name}' is not an Application instance, got {type(app).__name__}"
            )

        return app, module

    except ImportError as e:
        raise ImportError(f"Could not import module '{module_path}': {e}")


# =============================================================================
# Main CLI Group
# =============================================================================


@click.group()
@click.option(
    "--application",
    "-a",
    type=str,
    default=None,
    help="Application path (e.g., 'examples.orm_example:app')",
)
@click.option(
    "--migrations-dir",
    "-m",
    type=click.Path(path_type=Path),
    default=None,
    help="Migrations directory path",
)
@click.option(
    "--entities",
    "-e",
    type=str,
    default=None,
    help="Entities module path (e.g., 'myapp.entities') - fallback if no --application",
)
@click.option(
    "--database",
    "-d",
    type=str,
    default=None,
    help="Database URL (e.g., 'sqlite:///db.sqlite3') - fallback if no --application",
)
@click.pass_context
def db(
    ctx: click.Context,
    application: str | None,
    migrations_dir: Path | None,
    entities: str | None,
    database: str | None,
):
    """Bloom DB - Database management commands

    \b
    Application-based usage (recommended):
        bloom db --application=myapp.module:app makemigrations

    \b
    Module-based usage (legacy):
        bloom db --entities=myapp.entities makemigrations
    """
    # 설정 로드
    config = load_config()

    # Application 로드 (기본값: application:application)
    app: Application | None = None
    app_module: Any = None
    app_path = application or config.get("application", "application:application")

    try:
        app, app_module = load_application(app_path)
        # ready_async() 호출하여 DI 초기화
        if not app._is_ready:
            import asyncio
            click.echo(f"Initializing application: {app.name}")
            asyncio.run(app.ready_async())
        click.echo(f"Using application: {app.name}")
    except (ImportError, AttributeError, click.ClickException) as e:
        # application 모듈을 찾을 수 없는 경우
        if application:
            # 명시적으로 지정한 경우 에러
            raise click.ClickException(f"Failed to load application '{app_path}': {e}")

        # 기본값 사용 시, --entities가 있으면 fallback
        if entities:
            click.echo(f"Note: Using --entities mode (no application found)")
        else:
            # --entities도 없으면 친절한 에러 메시지
            raise click.ClickException(
                f"Could not import default application.\n\n"
                f"Make sure you have 'application.py' with:\n\n"
                f"  from bloom import Application\n"
                f"  from bloom.db import SessionFactory, SQLiteDialect\n"
                f"  from bloom.core import Component, Factory\n\n"
                f"  application = Application('myapp')\n\n"
                f"  @Component\n"
                f"  class DatabaseConfig:\n"
                f"      @Factory\n"
                f"      def session_factory(self) -> SessionFactory:\n"
                f"          return SessionFactory('db.sqlite3', SQLiteDialect())\n\n"
                f"Or specify explicitly:\n"
                f"  bloom db --application=mymodule:app makemigrations\n\n"
                f"Or use legacy mode:\n"
                f"  bloom db --entities=myapp.entities --database=sqlite:///db.sqlite3 makemigrations"
            )

    # 옵션 우선, 없으면 설정 파일, 없으면 기본값
    mig_dir = migrations_dir or Path(config.get("migrations_dir", "migrations"))
    ent_module = entities or config.get("entities_module")
    db_url = database or config.get("database_url", "sqlite:///db.sqlite3")

    ctx.obj = DBContext(
        migrations_dir=mig_dir,
        application=app,
        application_module=app_module,
        entities_module=ent_module,
        database_url=db_url,
    )


# =============================================================================
# Register Commands
# =============================================================================

# 명령어 등록은 하위 모듈에서 수행
from .commands import makemigrations, migrate, show, utils  # noqa: E402, F401


# =============================================================================
# Entry Point
# =============================================================================


def main():
    """CLI 엔트리 포인트"""
    db()


if __name__ == "__main__":
    main()
