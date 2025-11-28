"""추상 패턴 클래스들

Manager → Registry → Entry 패턴을 추상화합니다.
GroupRegistry → EntryGroup 패턴도 지원합니다.
"""

from .entry import Entry
from .group import EntryGroup
from .group_registry import GroupRegistry
from .registry import AbstractRegistry
from .manager import AbstractManager

__all__ = [
    "Entry",
    "EntryGroup",
    "GroupRegistry",
    "AbstractRegistry",
    "AbstractManager",
]
