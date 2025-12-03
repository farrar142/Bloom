"""bloom - Python DI Container Framework

Usage:
    from bloom import Application, Component, Factory
    from bloom import Controller, Get, Post
"""

__version__ = "0.1.0"

# Application
from .application import Application

# Core
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
