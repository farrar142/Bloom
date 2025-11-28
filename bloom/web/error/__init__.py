"""
에러 처리 모듈

ErrorHandler 데코레이터, ErrorHandlerContainer, Manager-Registry-Entry 패턴을 제공합니다.
ErrorHandlerMiddleware는 bloom.web.builtin.middleware에서 import하세요.
"""

from .container import ErrorHandlerContainer, ErrorHandler
from .entry import ErrorHandlerEntry
from .manager import ErrorHandlerManager
from .registry import ErrorHandlerRegistry


# ErrorHandlerMiddleware는 순환 import 방지를 위해 지연 import
def __getattr__(name: str):
    if name == "ErrorHandlerMiddleware":
        from ..builtin.middleware import ErrorHandlerMiddleware

        return ErrorHandlerMiddleware
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ErrorHandler",
    "ErrorHandlerContainer",
    "ErrorHandlerEntry",
    "ErrorHandlerManager",
    "ErrorHandlerMiddleware",
    "ErrorHandlerRegistry",
]
