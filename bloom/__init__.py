"""bloom - Python DI Container Framework

Usage:
    from bloom import Application, Component, Factory
    from bloom import Controller, Get, Post
"""

from typing import TYPE_CHECKING

__version__ = "0.1.0"

__all__ = [
    # Application
    "Application",
    # Core
    "ContainerManager",
    "Component",
    "Factory",
    "Handler",
    "PostConstruct",
    "PreDestroy",
    "Lazy",
    "Scope",
]


def __getattr__(name: str):
    """Lazy import"""

    # Application
    if name == "Application":
        from .application import Application

        return Application

    # Core
    if name == "ContainerManager":
        from .core import ContainerManager

        return ContainerManager

    if name == "Component":
        from .core import Component

        return Component

    if name == "Factory":
        from .core import Factory

        return Factory

    if name == "Handler":
        from .core import Handler

        return Handler

    if name == "PostConstruct":
        from .core import PostConstruct

        return PostConstruct

    if name == "PreDestroy":
        from .core import PreDestroy

        return PreDestroy

    if name == "Lazy":
        from .core import Lazy

        return Lazy

    if name == "Scope":
        from .core import Scope

        return Scope

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# TYPE_CHECKING용 (IDE 지원)
if TYPE_CHECKING:
    from .application import Application
    from .core import (
        ContainerManager,
        Component,
        Factory,
        Handler,
        PostConstruct,
        PreDestroy,
        Lazy,
        Scope,
    )
