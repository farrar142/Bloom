"""Tests CLI

사용 예시:
    bloom tests
    bloom tests -v -x
    bloom tests tests/test_api.py
    bloom tests --cov=src
"""

from __future__ import annotations

from pathlib import Path

import click


def _get_default_test_paths() -> list[str]:
    """기본 테스트 경로 목록 반환
    
    검색 경로:
      - tests/          (프로젝트 루트 테스트)
      - */tests.py      (앱별 테스트)
      - */tests/        (앱별 테스트 디렉토리)
    """
    cwd = Path.cwd()
    paths: list[str] = []
    
    # 1. tests/ 디렉토리
    if (cwd / "tests").exists():
        paths.append("tests/")
    
    # 2. */tests.py 및 */tests/ 패턴 (앱별 테스트)
    for subdir in cwd.iterdir():
        if not subdir.is_dir():
            continue
        # 숨김/특수 디렉토리 제외
        if subdir.name.startswith((".", "_")):
            continue
        if subdir.name in ("venv", "env", "node_modules", "tests", "docs", "migrations"):
            continue
        
        # */tests.py
        if (subdir / "tests.py").exists():
            paths.append(str(subdir / "tests.py"))
        
        # */tests/ 디렉토리
        if (subdir / "tests").is_dir():
            paths.append(str(subdir / "tests"))
    
    # 아무것도 없으면 기본값
    return paths if paths else ["tests/"]


@click.command("tests")
@click.argument("paths", nargs=-1)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Verbose output",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Quiet output",
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
def tests(
    paths: tuple[str, ...],
    verbose: bool,
    quiet: bool,
    exitfirst: bool,
    k: str | None,
    cov: str | None,
):
    """Run tests with pytest

    \b
    Runs pytest with common options.
    Default: runs all tests in tests/ and */tests.py

    \b
    Examples:
        bloom tests
        bloom tests tests/test_api.py
        bloom tests users/tests.py
        bloom tests -v -x
        bloom tests -q -x
        bloom tests -k "test_user"
        bloom tests --cov=src
    """
    try:
        import pytest
    except ImportError:
        raise click.ClickException(
            "pytest is required for the tests command.\n"
            "Install it with: pip install pytest"
        )

    # pytest 인자 구성
    args = list(paths) if paths else _get_default_test_paths()

    if verbose:
        args.append("-v")
    if quiet:
        args.append("-q")
    if exitfirst:
        args.append("-x")
    if k:
        args.extend(["-k", k])
    if cov:
        try:
            import pytest_cov  # noqa: F401

            args.extend([f"--cov={cov}"])
        except ImportError:
            click.echo("[Bloom] Warning: pytest-cov not installed, skipping coverage")

    click.echo(f"[Bloom] Running: pytest {' '.join(args)}")
    click.echo()

    # pytest 실행
    exit_code = pytest.main(args)
    raise SystemExit(exit_code)
