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
    Factory,
    Handler,
    PostConstruct,
    PreDestroy,
    Order,
    Scope,
)
from .container.element import Scope as ScopeEnum, PrototypeMode
from .exceptions import (
    # Base
    BloomException,
    # Container
    ContainerException,
    CircularDependencyError,
    AmbiguousProviderError,
    AmbiguousInstanceError,
    # HTTP - Base
    HttpException,
    # HTTP - 4xx
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    MethodNotAllowedError,
    ValidationError,
    ParameterBindingError,
    MissingParameterError,
    TypeConversionError,
    # HTTP - 5xx
    InternalServerError,
    ServiceUnavailableError,
    # HTTP - OAuth2
    OAuth2Error,
    InvalidGrantError,
    InvalidClientError,
    InvalidTokenError,
    OAuth2RequestError,
    # System
    SystemException,
    ConfigurationError,
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
    # Lifecycle
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
