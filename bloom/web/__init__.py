"""bloom.web 패키지 - Lazy import"""

__all__ = [
    "Authenticator",
    "Authentication",
    "ANONYMOUS",
    "Authorize",
    "AuthorizeElement",
    "ErrorHandler",
    "ErrorHandlerContainer",
    "ErrorHandlerMiddleware",
    "HttpRequest",
    "HttpResponse",
    "StreamingResponse",
    "FileResponse",
    "HttpMethodHandlerContainer",
    "Get",
    "Post",
    "Put",
    "Patch",
    "Delete",
    "Router",
    "ControllerContainer",
    "RequestMappingElement",
    "Controller",
    "RequestMapping",
    "ASGIApplication",
    "create_asgi_app",
    "StaticFiles",
    "StaticFilesContainer",
    "StaticFilesManager",
    "RouteEntry",
    "RouteRegistry",
    "RouteManager",
]


def __getattr__(name: str):
    """Lazy import"""
    # Auth
    if name in ("Authenticator", "Authentication", "ANONYMOUS", "Authorize", "AuthorizeElement"):
        from .auth import Authenticator, Authentication, ANONYMOUS, Authorize, AuthorizeElement
        return locals()[name]
    
    # Error
    if name in ("ErrorHandler", "ErrorHandlerContainer", "ErrorHandlerMiddleware"):
        from .error import ErrorHandler, ErrorHandlerContainer, ErrorHandlerMiddleware
        return locals()[name]
    
    # HTTP
    if name in ("HttpRequest", "HttpResponse", "StreamingResponse", "FileResponse"):
        from .http import HttpRequest, HttpResponse, StreamingResponse, FileResponse
        return locals()[name]
    
    # Handler
    if name in ("HttpMethodHandlerContainer", "Get", "Post", "Put", "Patch", "Delete"):
        from .handler import HttpMethodHandlerContainer, Get, Post, Put, Patch, Delete
        return locals()[name]
    
    # Router
    if name == "Router":
        from .router import Router
        return Router
    
    # Controller
    if name in ("ControllerContainer", "RequestMappingElement", "Controller", "RequestMapping"):
        from .controller import ControllerContainer, RequestMappingElement, Controller, RequestMapping
        return locals()[name]
    
    # ASGI
    if name in ("ASGIApplication", "create_asgi_app"):
        from .asgi import ASGIApplication, create_asgi_app
        return locals()[name]
    
    # Static
    if name in ("StaticFiles", "StaticFilesContainer", "StaticFilesManager"):
        from .static import StaticFiles, StaticFilesContainer, StaticFilesManager
        return locals()[name]
    
    # Routing
    if name in ("RouteEntry", "RouteRegistry", "RouteManager"):
        from .routing import RouteEntry, RouteRegistry, RouteManager
        return locals()[name]
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
