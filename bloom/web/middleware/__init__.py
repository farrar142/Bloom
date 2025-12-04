"""bloom.web.middleware - Middleware System"""

from .base import (
    Middleware,
    MiddlewareComponent,
    MiddlewareStack,
    MiddlewareEntry,
    MiddlewareMetadata,
    is_middleware_component,
    get_middleware_metadata,
)
from .request_scope import RequestScopeMiddleware
from .error_handler import ErrorHandlerMiddleware, CORSMiddleware

__all__ = [
    # Base
    "Middleware",
    "MiddlewareComponent",
    "MiddlewareStack",
    "MiddlewareEntry",
    "MiddlewareMetadata",
    "is_middleware_component",
    "get_middleware_metadata",
    # Built-in Middlewares
    "RequestScopeMiddleware",
    "ErrorHandlerMiddleware",
    "CORSMiddleware",
]
