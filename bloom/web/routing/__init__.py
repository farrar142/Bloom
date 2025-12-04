"""bloom.web.routing - Routing and Controller support"""

from .router import Router, Route, RouteMatch
from .trie import PathTrie, PathIncluded, TrieMatch
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
    UploadedFile,
    Authentication,
)
from .resolver import (
    ParameterResolver,
    PathVariableResolver,
    QueryResolver,
    RequestBodyResolver,
    HeaderResolver,
    CookieResolver,
    RequestResolver,
    UploadedFileResolver,
    AuthenticationResolver,
    ResolverRegistry,
)

__all__ = [
    # Router
    "Router",
    "Route",
    "RouteMatch",
    # Trie
    "PathTrie",
    "PathIncluded",
    "TrieMatch",
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
    "UploadedFile",
    "Authentication",
    # Resolver
    "ParameterResolver",
    "PathVariableResolver",
    "QueryResolver",
    "RequestBodyResolver",
    "HeaderResolver",
    "CookieResolver",
    "RequestResolver",
    "UploadedFileResolver",
    "AuthenticationResolver",
    "ResolverRegistry",
]
