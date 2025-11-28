"""추상 패턴 클래스들

Manager → Registry → Entry 패턴을 추상화합니다.
"""

from .entry import Entry
from .registry import AbstractRegistry
from .manager import AbstractManager

__all__ = [
    "Entry",
    "AbstractRegistry",
    "AbstractManager",
]
