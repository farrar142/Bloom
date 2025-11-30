"""Bloom Framework 로깅 모듈"""

import logging
import sys
from typing import Literal, TextIO

from bloom.log.graph import generate_dependency_graph

# Bloom 프레임워크 메인 로거
logger = logging.getLogger("bloom")

# 로그 레벨 타입
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# 기본 포맷터
DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    level: LogLevel | int = "INFO",
    format: str = DEFAULT_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
    stream: TextIO | None = None,
) -> None:
    """
    Bloom 프레임워크 로깅 설정

    Args:
        level: 로그 레벨 ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL" 또는 int)
        format: 로그 포맷 문자열
        date_format: 날짜 포맷 문자열
        stream: 출력 스트림 (기본값: stderr)

    Example:
        >>> from bloom.log import configure_logging
        >>> configure_logging(level="DEBUG")
    """
    if stream is None:
        stream = sys.stderr

    # 문자열 레벨을 int로 변환
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # 핸들러 설정
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)

    # 포맷터 설정
    formatter = logging.Formatter(format, datefmt=date_format)
    handler.setFormatter(formatter)

    # 기존 핸들러 제거 후 새 핸들러 추가
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False  # root 로거로 전파 방지 (중복 출력 방지)


def get_logger(name: str) -> logging.Logger:
    """
    Bloom 하위 로거 생성

    Args:
        name: 로거 이름 (bloom.{name} 형태로 생성됨)

    Returns:
        logging.Logger: 하위 로거

    Example:
        >>> from bloom.log import get_logger
        >>> log = get_logger("web")  # bloom.web 로거
        >>> log.info("Server started")
    """
    if name.startswith("bloom."):
        return logging.getLogger(name)
    return logging.getLogger(f"bloom.{name}")


# 기본 로거 설정 (WARNING 이상만 출력)
if not logger.handlers:
    _default_handler = logging.StreamHandler(sys.stderr)
    _default_handler.setFormatter(
        logging.Formatter(DEFAULT_FORMAT, datefmt=DEFAULT_DATE_FORMAT)
    )
    logger.addHandler(_default_handler)
    logger.setLevel(logging.WARNING)

# 편의를 위한 로거 메서드 노출
debug = logger.debug
info = logger.info
warning = logger.warning
error = logger.error
critical = logger.critical
exception = logger.exception


__all__ = [
    "logger",
    "get_logger",
    "configure_logging",
    "LogLevel",
    "debug",
    "info",
    "warning",
    "error",
    "critical",
    "exception",
    "generate_dependency_graph",
]
