"""bloom.web.routing - Routing and Controller support"""

from .router import Router, Route, RouteMatch
from .decorators import (
    Controller,
    RequestMapping,
    GetMapping,
    PostMapping,
    PutMapping,
    DeleteMapping,
    PatchMapping,
    get_controller_routes,
    is_controller,
)
from .params import (
    PathVariable,
    Query,
    RequestBody,
    RequestField,
    Header,
    Cookie,
)
from .resolver import (
    ParameterResolver,
    PathVariableResolver,
    QueryResolver,
    RequestBodyResolver,
    HeaderResolver,
    CookieResolver,
    RequestResolver,
    ResolverRegistry,
)

__all__ = [
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
    "get_controller_routes",
    "is_controller",
    # Params
    "PathVariable",
    "Query",
    "RequestBody",
    "RequestField",
    "Header",
    "Cookie",
    # Resolver
    "ParameterResolver",
    "PathVariableResolver",
    "QueryResolver",
    "RequestBodyResolver",
    "HeaderResolver",
    "CookieResolver",
    "RequestResolver",
    "ResolverRegistry",
]
