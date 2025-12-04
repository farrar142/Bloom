"""bloom.task.backends - 태스크 브로커/백엔드 구현체"""

from typing import TYPE_CHECKING
from .local import LocalBroker, LocalBackend

__all__ = ["LocalBroker", "LocalBackend", "RedisBroker", "RedisBackend"]


def __getattr__(name: str):
    """Lazy import for optional dependencies"""
    if name in ("RedisBroker", "RedisBackend"):
        from .redis import RedisBroker, RedisBackend

        if name == "RedisBroker":
            return RedisBroker
        return RedisBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    from .local import LocalBroker, LocalBackend
    from .redis import RedisBroker, RedisBackend
