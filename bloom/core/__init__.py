"""bloom.core 패키지"""

from .manager import (
    ContainerManager,
    get_current_manager,
    set_current_manager,
    try_get_current_manager,
)
from .container import (
    Element,
    Container,
    ComponentContainer,
    FactoryContainer,
    HandlerContainer,
)
from .decorators import (
    Component,
    Qualifier,
    Factory,
    Handler,
    PostConstruct,
    PreDestroy,
)
from .lifecycle import LifecycleManager
from .lazy import Lazy, LazyProxy, is_lazy_component
from .abstract import (
    Entry,
    AbstractRegistry,
    AbstractManager,
)

__all__ = [
    "ContainerManager",
    "get_current_manager",
    "set_current_manager",
    "try_get_current_manager",
    "Element",
    "Container",
    "ComponentContainer",
    "FactoryContainer",
    "HandlerContainer",
    "Component",
    "Qualifier",
    "Factory",
    "Handler",
    "PostConstruct",
    "PreDestroy",
    "LifecycleManager",
    "Lazy",
    "LazyProxy",
    "is_lazy_component",
    # Abstract patterns
    "Entry",
    "AbstractRegistry",
    "AbstractManager",
]
