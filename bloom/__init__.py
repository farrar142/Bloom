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

# Logging
from .log import logger, get_logger, configure_logging

# Web
from .web import (
    HttpRequest,
    HttpResponse,
    Get,
    Post,
    Put,
    Patch,
    Delete,
    Controller,
    RequestMapping,
)
from .web.params import (
    RequestBody,
    HttpHeader,
    HttpCookie,
    UploadedFile,
)

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
    # Logging
    "logger",
    "get_logger",
    "configure_logging",
    # Web
    "HttpRequest",
    "HttpResponse",
    "Get",
    "Post",
    "Put",
    "Patch",
    "Delete",
    "Controller",
    "RequestMapping",
    "RequestBody",
    "HttpHeader",
    "HttpCookie",
    "UploadedFile",
]
