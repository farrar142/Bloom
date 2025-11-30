"""Bloom CLI

사용 예시:
    # 워커 실행
    bloom worker main:app.queue
    bloom worker main:app.queue --concurrency 4
    bloom worker main:app.queue -c 8

    # Python -m 으로 실행
    python -m bloom worker main:app.queue
"""

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Any

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


def worker_command(args: argparse.Namespace) -> None:
    """워커 실행 명령"""
    from bloom.logging import configure_logging
    from bloom.task.queue_app import QueueApplication

    print(f"[Bloom] Importing {args.app}")

    # app.queue 임포트
    try:
        queue_app = import_from_string(args.app)
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # 로깅 설정 (bloom.logging 모듈 사용)
    configure_logging(level="INFO")

    # QueueApplication 확인
    if not isinstance(queue_app, QueueApplication):
        print(
            f"Error: Expected QueueApplication, got {type(queue_app).__name__}",
            file=sys.stderr,
        )
        sys.exit(1)

    # concurrency 설정
    queue_app._concurrency = args.concurrency

    # 워커 실행
    queue_app.run_sync()


def main() -> None:
    """CLI 메인 엔트리포인트"""
    parser = argparse.ArgumentParser(prog="bloom", description="Bloom Framework CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # worker 명령
    worker_parser = subparsers.add_parser("worker", help="Start a task worker")
    worker_parser.add_argument("app", help="Application to run (e.g., main:app.queue)")
    worker_parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=4,
        help="Number of concurrent workers (default: 4)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "worker":
        worker_command(args)


if __name__ == "__main__":
    main()
