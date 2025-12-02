"""bloom - Python DI Container Framework

Django 스타일 lazy import: 최상위 패키지는 최소한만 로드하고,
.

Usage:
    # 필요한 것만 import (해당 모듈만 로드)
    from bloom import Application
    from bloom.core import Component, Factory
    from bloom.web import Controller, Get
    
    # 또는 전체 로드
    import bloom
    bloom.Component  # __getattr__로 lazy 로드
"""

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


def __getattr__(name: str):
    """Lazy import: 속성 접근 시에만 해당 모듈 로드"""
    # Application
    if name == "Application":
        from .application import Application

        return Application

    # Core
    if name in (
        "ContainerManager",
        "Component",
        "Factory",
        "Handler",
        "PostConstruct",
        "PreDestroy",
        "Lazy",
        "Scope",
    ):
        from . import core

        return getattr(core, name)

    # Logging
    if name == "logger":
        from .log import logger

        return logger
    if name == "get_logger":
        from .log import get_logger

        return get_logger
    if name == "configure_logging":
        from .log import configure_logging

        return configure_logging

    # Web
    if name in (
        "HttpRequest",
        "HttpResponse",
        "Get",
        "Post",
        "Put",
        "Patch",
        "Delete",
        "Controller",
        "RequestMapping",
    ):
        from . import web

        return getattr(web, name)

    # Web params
    if name in ("HttpCookie", "HttpHeader", "RequestBody", "UploadedFile"):
        from .web import params

        return getattr(params, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
