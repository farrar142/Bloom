"""추상 패턴 클래스들

Manager → Registry 패턴을 추상화합니다.
GroupRegistry → EntryGroup 패턴도 지원합니다.
"""

from .group import EntryGroup
from .group_registry import GroupRegistry
from .registry import AbstractRegistry
from .manager import AbstractManager
from .proxyable import ProxyableDescriptor

__all__ = [
    "EntryGroup",
    "GroupRegistry",
    "AbstractRegistry",
    "AbstractManager",
    "ProxyableDescriptor",
]
