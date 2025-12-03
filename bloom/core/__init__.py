"""
bloom.core - DI Container Core Module

Spring-like 의존성 주입 컨테이너.

사용 예:
    from bloom.core import (
        Component,
        Factory,
        Configuration,
        Service,
        Repository,
        Handler,
        Value,
        Scope,
        PostConstruct,
        PreDestroy,
        AutoClosable,
        ContainerManager,
    )

    @Component
    class UserRepository:
        pass

    @Component
    class UserService:
        repo: UserRepository  # 자동 주입 (Lazy)

    @Configuration
    class AppConfig:
        @Factory
        def redis_client(self) -> RedisClient:
            return RedisClient()
"""

from typing import TYPE_CHECKING

__all__ = [
    # Scope
    "Scope",
    # Lifecycle
    "PostConstruct",
    "PreDestroy",
    "AutoClosable",
    "LifecycleManager",
    # Container
    "Container",
    "DependencyInfo",
    "FactoryInfo",
    # Manager
    "ContainerManager",
    "get_container_manager",
    "set_container_manager",
    "reset_container_manager",
    # Decorators
    "Component",
    "Configuration",
    "Factory",
    "Service",
    "Repository",
    "Handler",
    "Value",
    "Primary",
    "Lazy",
    "Order",
    "RequestScope",
    "CallScope",
    "Singleton",
    # Proxy
    "LazyProxy",
    "MethodProxy",
    "MethodHooks",
    # Scanner
    "Scanner",
    "scan_modules",
    "discover_components",
    # Resolver
    "DependencyResolver",
    "DependencyGraph",
    # Scope Manager
    "ScopeManager",
    # AOP
    "aop",
    # Exceptions
    "BloomException",
    "ContainerException",
    "ComponentNotFoundError",
    "DuplicateComponentError",
    "CircularDependencyError",
    "DependencyResolutionError",
    "ScopeError",
    "RequestScopeError",
    "CallScopeError",
    "LifecycleError",
    "ConfigurationError",
    "ValueNotFoundError",
]


def __getattr__(name: str):
    """Lazy import"""

    # Scope
    if name == "Scope":
        from .scope import Scope

        return Scope

    # Lifecycle
    if name == "PostConstruct":
        from .lifecycle import PostConstruct

        return PostConstruct

    if name == "PreDestroy":
        from .lifecycle import PreDestroy

        return PreDestroy

    if name == "AutoClosable":
        from .lifecycle import AutoClosable

        return AutoClosable

    if name == "LifecycleManager":
        from .lifecycle import LifecycleManager

        return LifecycleManager

    # Container
    if name == "Container":
        from .container import Container

        return Container

    if name == "DependencyInfo":
        from .container import DependencyInfo

        return DependencyInfo

    if name == "FactoryInfo":
        from .container import FactoryInfo

        return FactoryInfo

    # Manager
    if name == "ContainerManager":
        from .manager import ContainerManager

        return ContainerManager

    if name == "get_container_manager":
        from .manager import get_container_manager

        return get_container_manager

    if name == "set_container_manager":
        from .manager import set_container_manager

        return set_container_manager

    if name == "reset_container_manager":
        from .manager import reset_container_manager

        return reset_container_manager

    # Decorators
    if name == "Component":
        from .decorators import Component

        return Component

    if name == "Configuration":
        from .decorators import Configuration

        return Configuration

    if name == "Factory":
        from .decorators import Factory

        return Factory

    if name == "Service":
        from .decorators import Service

        return Service

    if name == "Repository":
        from .decorators import Repository

        return Repository

    if name == "Handler":
        from .decorators import Handler

        return Handler

    if name == "Value":
        from .decorators import Value

        return Value

    if name == "Primary":
        from .decorators import Primary

        return Primary

    if name == "Lazy":
        from .decorators import Lazy

        return Lazy

    if name == "Order":
        from .decorators import Order

        return Order

    if name == "RequestScope":
        from .decorators import RequestScope

        return RequestScope

    if name == "CallScope":
        from .decorators import CallScope

        return CallScope

    if name == "Singleton":
        from .decorators import Singleton

        return Singleton

    # Proxy
    if name == "LazyProxy":
        from .proxy import LazyProxy

        return LazyProxy

    if name == "MethodProxy":
        from .proxy import MethodProxy

        return MethodProxy

    if name == "MethodHooks":
        from .proxy import MethodHooks

        return MethodHooks

    # Scanner
    if name == "Scanner":
        from .scanner import Scanner

        return Scanner

    if name == "scan_modules":
        from .scanner import scan_modules

        return scan_modules

    if name == "discover_components":
        from .scanner import discover_components

        return discover_components

    # Resolver
    if name == "DependencyResolver":
        from .resolver import DependencyResolver

        return DependencyResolver

    if name == "DependencyGraph":
        from .resolver import DependencyGraph

        return DependencyGraph

    # Scope Manager
    if name == "ScopeManager":
        from .scope_manager import ScopeManager

        return ScopeManager

    # AOP
    if name == "aop":
        from . import aop

        return aop

    # Exceptions
    if name in (
        "BloomException",
        "ContainerException",
        "ComponentNotFoundError",
        "DuplicateComponentError",
        "CircularDependencyError",
        "DependencyResolutionError",
        "ScopeError",
        "RequestScopeError",
        "CallScopeError",
        "LifecycleError",
        "ConfigurationError",
        "ValueNotFoundError",
    ):
        from . import exceptions

        return getattr(exceptions, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# TYPE_CHECKING용 (IDE 지원)
if TYPE_CHECKING:
    from .scope import Scope
    from .lifecycle import PostConstruct, PreDestroy, AutoClosable, LifecycleManager
    from .container import Container, DependencyInfo, FactoryInfo
    from .manager import (
        ContainerManager,
        get_container_manager,
        set_container_manager,
        reset_container_manager,
    )
    from .decorators import (
        Component,
        Configuration,
        Factory,
        Service,
        Repository,
        Handler,
        Value,
        Primary,
        Lazy,
        Order,
        RequestScope,
        CallScope,
        Singleton,
    )
    from .proxy import LazyProxy, MethodProxy, MethodHooks
    from .scanner import Scanner, scan_modules, discover_components
    from .resolver import DependencyResolver, DependencyGraph
    from .scope_manager import ScopeManager
    from . import aop
    from .exceptions import (
        BloomException,
        ContainerException,
        ComponentNotFoundError,
        DuplicateComponentError,
        CircularDependencyError,
        DependencyResolutionError,
        ScopeError,
        RequestScopeError,
        CallScopeError,
        LifecycleError,
        ConfigurationError,
        ValueNotFoundError,
    )
