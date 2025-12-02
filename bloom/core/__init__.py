"""bloom.core 패키지 - Lazy import"""

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


def __getattr__(name: str):
    """Lazy import"""
    # Manager
    if name in ("ContainerManager", "get_current_manager", "set_current_manager", "try_get_current_manager"):
        from .manager import ContainerManager, get_current_manager, set_current_manager, try_get_current_manager
        return locals()[name]
    
    # Container
    if name in ("Element", "Container", "ComponentContainer", "FactoryContainer", "HandlerContainer"):
        from .container import Element, Container, ComponentContainer, FactoryContainer, HandlerContainer
        return locals()[name]
    
    # Decorators
    if name in ("Component", "Factory", "Handler", "PostConstruct", "PreDestroy", "Order", "Scope"):
        from .decorators import Component, Factory, Handler, PostConstruct, PreDestroy, Order, Scope
        return locals()[name]
    
    # Scope enum
    if name == "ScopeEnum":
        from .container.element import Scope as ScopeEnum
        return ScopeEnum
    if name == "PrototypeMode":
        from .container.element import PrototypeMode
        return PrototypeMode
    
    # Exceptions
    if name in (
        "BloomException", "ContainerException", "CircularDependencyError", 
        "AmbiguousProviderError", "AmbiguousInstanceError", "HttpException",
        "BadRequestError", "UnauthorizedError", "ForbiddenError", "NotFoundError",
        "MethodNotAllowedError", "ValidationError", "ParameterBindingError",
        "MissingParameterError", "TypeConversionError", "InternalServerError",
        "ServiceUnavailableError", "OAuth2Error", "InvalidGrantError",
        "InvalidClientError", "InvalidTokenError", "OAuth2RequestError",
        "SystemException", "ConfigurationError", "InvalidScopeError",
    ):
        from . import exceptions
        return getattr(exceptions, name)
    
    # Lifecycle
    if name == "LifecycleManager":
        from .lifecycle import LifecycleManager
        return LifecycleManager
    
    # Lazy
    if name in ("Lazy", "LazyFieldProxy", "is_lazy_wrapper_type", "get_lazy_inner_type"):
        from .lazy import Lazy, LazyFieldProxy, is_lazy_wrapper_type, get_lazy_inner_type
        return locals()[name]
    
    # Request context
    if name in ("RequestContext", "RequestContextManager", "get_current_request", "try_get_current_request", "request_scope"):
        from .request_context import RequestContext, RequestContextManager, get_current_request, try_get_current_request, request_scope
        return locals()[name]
    
    # Abstract
    if name in ("AbstractRegistry", "AbstractManager"):
        from .abstract import AbstractRegistry, AbstractManager
        return locals()[name]
    
    # Orchestrator
    if name == "ContainerOrchestrator":
        from .orchestrator import ContainerOrchestrator
        return ContainerOrchestrator
    
    # Protocols
    if name in ("Serializable", "AutoCloseable"):
        from .protocols import Serializable, AutoCloseable
        return locals()[name]
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
