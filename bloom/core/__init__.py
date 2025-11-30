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
from .exceptions import (
    BloomException,
    CircularDependencyError,
    AmbiguousProviderError,
)
from .lifecycle import LifecycleManager
from .lazy import (
    Lazy,
    LazyWrapper,
    LazyProxy,
    LazyComponent,
    is_lazy_component,
    is_lazy_wrapper_type,
    get_lazy_inner_type,
)
from .abstract import (
    AbstractRegistry,
    AbstractManager,
)
from .orchestrator import ContainerOrchestrator

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
    # Exceptions
    "BloomException",
    "CircularDependencyError",
    "AmbiguousProviderError",
    "LifecycleManager",
    "Lazy",
    "LazyWrapper",
    "LazyProxy",
    "LazyComponent",
    "is_lazy_component",
    "is_lazy_wrapper_type",
    "get_lazy_inner_type",
    # Abstract patterns
    "AbstractRegistry",
    "AbstractManager",
    # Orchestrator
    "ContainerOrchestrator",
]
