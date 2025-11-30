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
    Scope,
)
from .container.element import Scope as ScopeEnum, PrototypeMode
from .exceptions import (
    BloomException,
    CircularDependencyError,
    AmbiguousProviderError,
)
from .lifecycle import LifecycleManager
from .lazy import (
    Lazy,
    LazyFieldProxy,
    is_lazy_wrapper_type,
    get_lazy_inner_type,
)
from .request_context import (
    RequestContext,
    request_scope,
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
    "Scope",
    "ScopeEnum",
    "PrototypeMode",
    # Exceptions
    "BloomException",
    "CircularDependencyError",
    "AmbiguousProviderError",
    "LifecycleManager",
    "Lazy",
    "LazyFieldProxy",
    "is_lazy_wrapper_type",
    "get_lazy_inner_type",
    # Request scope
    "RequestContext",
    "request_scope",
    # Abstract patterns
    "AbstractRegistry",
    "AbstractManager",
    # Orchestrator
    "ContainerOrchestrator",
]
