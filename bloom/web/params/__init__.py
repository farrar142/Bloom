"""파라미터 리졸버 패키지"""

from .base import ParameterResolver, get_type_info, is_optional, unwrap_optional
from .registry import (
    UNRESOLVED,
    CachedResolverInfo,
    ParameterResolverRegistry,
    get_default_registry,
    register_resolver,
    resolve_parameters,
    resolve_parameters_cached,
)
from .resolvers import (
    AuthenticationResolver,
    HttpCookieResolver,
    HttpHeaderResolver,
    HttpRequestResolver,
    KeyValueResolver,
    ListBodyResolver,
    ModelParamResolver,
    PathParamResolver,
    QueryParamResolver,
    RequestBodyResolver,
    UploadedFileResolver,
)
from .types import HttpCookie, HttpHeader, KeyValue, RequestBody, UploadedFile

# 기본 리졸버들 등록
_registry = get_default_registry()
_registry.register(HttpRequestResolver())  # HttpRequest 먼저
_registry.register(AuthenticationResolver())  # Authentication
_registry.register(HttpHeaderResolver())  # HttpHeader
_registry.register(HttpCookieResolver())  # HttpCookie
_registry.register(UploadedFileResolver())  # UploadedFile, list[UploadedFile]
_registry.register(RequestBodyResolver())  # RequestBody[T]
_registry.register(ListBodyResolver())  # list[T]
_registry.register(ModelParamResolver())  # dataclass, BaseModel (마커 없는 경우)
_registry.register(PathParamResolver())  # path params
_registry.register(QueryParamResolver())  # query params

__all__ = [
    # Base
    "ParameterResolver",
    "get_type_info",
    # Registry
    "ParameterResolverRegistry",
    "CachedResolverInfo",
    "UNRESOLVED",
    "get_default_registry",
    "register_resolver",
    "resolve_parameters",
    "resolve_parameters_cached",
    # Types
    "RequestBody",
    "HttpHeader",
    "HttpCookie",
    "KeyValue",
    "UploadedFile",
    # Resolvers
    "AuthenticationResolver",
    "RequestBodyResolver",
    "ListBodyResolver",
    "PathParamResolver",
    "QueryParamResolver",
    "HttpRequestResolver",
    "HttpHeaderResolver",
    "HttpCookieResolver",
    "KeyValueResolver",
    "UploadedFileResolver",
]
