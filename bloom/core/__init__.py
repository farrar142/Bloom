"""bloom.core 패키지"""

# Manager
from .manager import (
    ContainerManager,
    get_current_manager,
    set_current_manager,
    try_get_current_manager,
)

# Container
from .container import (
    Element,
    Container,
    ComponentContainer,
    FactoryContainer,
    HandlerContainer,
)

# Decorators
from .decorators import (
    Component,
    Decorator,
    Factory,
    Handler,
    PostConstruct,
    PreDestroy,
    Order,
    Scope,
)

# Scope enum
from .container.element import Scope as ScopeEnum
from .container.element import PrototypeMode

# Exceptions
from .exceptions import (
    BloomException,
    ContainerException,
    CircularDependencyError,
    AmbiguousProviderError,
    AmbiguousInstanceError,
    HttpException,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    MethodNotAllowedError,
    ValidationError,
    ParameterBindingError,
    MissingParameterError,
    TypeConversionError,
    InternalServerError,
    ServiceUnavailableError,
    OAuth2Error,
    InvalidGrantError,
    InvalidClientError,
    InvalidTokenError,
    OAuth2RequestError,
    SystemException,
    ConfigurationError,
    InvalidScopeError,
)

# Lifecycle
from .lifecycle import LifecycleManager

# Lazy
from .lazy import Lazy, LazyFieldProxy, is_lazy_wrapper_type, get_lazy_inner_type

# Request context
from .request_context import (
    RequestContext,
    RequestContextManager,
    get_current_request,
    try_get_current_request,
    request_scope,
)

# Abstract
from .abstract import AbstractRegistry, AbstractManager

# Orchestrator
from .orchestrator import ContainerOrchestrator

# Protocols
from .protocols import Serializable, AutoCloseable

__all__ = [
    "ContainerManager",
    "get_current_manager",
    "set_current_manager",
    "try_get_current_manager",
    "AutoCloseable",
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
    # Exceptions - Base
    "BloomException",
    # Exceptions - Container
    "ContainerException",
    "CircularDependencyError",
    "AmbiguousProviderError",
    "AmbiguousInstanceError",
    # Exceptions - HTTP Base
    "HttpException",
    # Exceptions - HTTP 4xx
    "BadRequestError",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "MethodNotAllowedError",
    "ValidationError",
    "ParameterBindingError",
    "MissingParameterError",
    "TypeConversionError",
    # Exceptions - HTTP 5xx
    "InternalServerError",
    "ServiceUnavailableError",
    # Exceptions - OAuth2
    "OAuth2Error",
    "InvalidGrantError",
    "InvalidClientError",
    "InvalidTokenError",
    "OAuth2RequestError",
    # Exceptions - System
    "SystemException",
    "ConfigurationError",
    "InvalidScopeError",
    # Lifecycle
    "LifecycleManager",
    "Lazy",
    "LazyFieldProxy",
    "is_lazy_wrapper_type",
    "get_lazy_inner_type",
    # Request scope
    "RequestContext",
    "RequestContextManager",
    "get_current_request",
    "try_get_current_request",
    "request_scope",
    # Abstract patterns
    "AbstractRegistry",
    "AbstractManager",
    # Orchestrator
    "ContainerOrchestrator",
    # Protocols
    "Serializable",
]
