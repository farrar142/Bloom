"""bloom.core 패키지"""

from .manager import (
    ContainerManager,
    AmbiguousInstanceError,
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
    Factory,
    Handler,
    PostConstruct,
    PreDestroy,
    Order,
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
    "AmbiguousInstanceError",
    "get_current_manager",
    "set_current_manager",
    "try_get_current_manager",
    "Element",
    "Container",
    "ComponentContainer",
    "FactoryContainer",
    "HandlerContainer",
    "Component",
    "Factory",
    "Handler",
    "PostConstruct",
    "PreDestroy",
    "Order",
    "LifecycleManager",
    "Lazy",
    "LazyProxy",
    "is_lazy_component",
    # Abstract patterns
    "Entry",
    "AbstractRegistry",
    "AbstractManager",
]
