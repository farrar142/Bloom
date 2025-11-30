"""Tests CLI

사용 예시:
    bloom tests
    bloom tests -v -x
    bloom tests tests/test_api.py
    bloom tests --cov=src
"""

from __future__ import annotations

import click


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
    Default: runs all tests in tests/ directory.

    \b
    Examples:
        bloom tests
        bloom tests tests/test_api.py
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
    args = list(paths) if paths else ["tests/"]

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
