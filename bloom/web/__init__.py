"""bloom.web - Web Layer Module"""

from .types import ASGIApp, Scope, Receive, Send, Message
from .request import Request
from .response import Response, JSONResponse, HTMLResponse, PlainTextResponse
from .middleware import Middleware, RequestScopeMiddleware
from .asgi import ASGIApplication
from .routing import (
    # Router
    Router,
    Route,
    RouteMatch,
    # Decorators
    Controller,
    RequestMapping,
    GetMapping,
    PostMapping,
    PutMapping,
    DeleteMapping,
    PatchMapping,
    # Params
    PathVariable,
    Query,
    RequestBody,
    RequestField,
    Header,
    Cookie,
    # Resolver
    ParameterResolver,
    ResolverRegistry,
)

__all__ = [
    # Types
    "ASGIApp",
    "Scope",
    "Receive",
    "Send",
    "Message",
    # Request/Response
    "Request",
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    # Middleware
    "Middleware",
    "RequestScopeMiddleware",
    # Application
    "ASGIApplication",
    # Router
    "Router",
    "Route",
    "RouteMatch",
    # Decorators
    "Controller",
    "RequestMapping",
    "GetMapping",
    "PostMapping",
    "PutMapping",
    "DeleteMapping",
    "PatchMapping",
    # Params
    "PathVariable",
    "Query",
    "RequestBody",
    "RequestField",
    "Header",
    "Cookie",
    # Resolver
    "ParameterResolver",
    "ResolverRegistry",
]
