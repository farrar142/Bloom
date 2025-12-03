"""bloom.web.routing.params - Parameter type annotations for routing"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, get_origin, get_args, Annotated

T = TypeVar("T")


# =============================================================================
# Parameter Markers
# =============================================================================


@dataclass(frozen=True)
class ParamMarker:
    """파라미터 마커 베이스 클래스"""
    
    name: str | None = None
    default: Any = ...
    
    def has_default(self) -> bool:
        return self.default is not ...


@dataclass(frozen=True)
class PathVariableMarker(ParamMarker):
    """Path Variable 마커
    
    사용 예:
        @GetMapping("/users/{user_id}")
        async def get_user(user_id: PathVariable[int]):
            ...
    """
    pass


@dataclass(frozen=True)
class QueryMarker(ParamMarker):
    """Query Parameter 마커
    
    사용 예:
        @GetMapping("/users")
        async def list_users(
            page: Query[int] = Query(default=1),
            size: Query[int] = Query(default=10),
        ):
            ...
    """
    pass


@dataclass(frozen=True)
class RequestBodyMarker(ParamMarker):
    """Request Body 마커
    
    사용 예:
        @PostMapping("/users")
        async def create_user(body: RequestBody[CreateUserSchema]):
            ...
    """
    pass


@dataclass(frozen=True)
class RequestFieldMarker(ParamMarker):
    """Request Body의 특정 필드 마커
    
    사용 예:
        @PostMapping("/users")
        async def create_user(
            username: RequestField[str],  # body["username"]
            email: RequestField[str],     # body["email"]
        ):
            ...
    """
    pass


@dataclass(frozen=True)
class HeaderMarker(ParamMarker):
    """HTTP Header 마커
    
    사용 예:
        @GetMapping("/profile")
        async def get_profile(
            authorization: Header[str],
            x_request_id: Header[str | None] = Header(name="X-Request-ID", default=None),
        ):
            ...
    """
    pass


@dataclass(frozen=True)
class CookieMarker(ParamMarker):
    """Cookie 마커
    
    사용 예:
        @GetMapping("/profile")
        async def get_profile(session_id: Cookie[str]):
            ...
    """
    pass


# =============================================================================
# Type Aliases using Annotated
# =============================================================================


# PathVariable[T] = Annotated[T, PathVariableMarker()]
class PathVariable(Generic[T]):
    """Path Variable 타입 힌트
    
    실제로는 Annotated[T, PathVariableMarker()]로 사용됩니다.
    
    사용 예:
        @GetMapping("/users/{id}")
        async def get_user(id: PathVariable[int]):
            return {"id": id}
    """
    
    def __class_getitem__(cls, item: type[T]) -> type:
        return Annotated[item, PathVariableMarker()]
    
    def __new__(
        cls,
        name: str | None = None,
        default: Any = ...,
    ) -> PathVariableMarker:
        return PathVariableMarker(name=name, default=default)


class Query(Generic[T]):
    """Query Parameter 타입 힌트
    
    사용 예:
        @GetMapping("/users")
        async def list_users(
            page: Query[int],
            size: Query[int] = Query(default=10),
        ):
            return {"page": page, "size": size}
    """
    
    def __class_getitem__(cls, item: type[T]) -> type:
        return Annotated[item, QueryMarker()]
    
    def __new__(
        cls,
        name: str | None = None,
        default: Any = ...,
    ) -> QueryMarker:
        return QueryMarker(name=name, default=default)


class RequestBody(Generic[T]):
    """Request Body 타입 힌트
    
    사용 예:
        @PostMapping("/users")
        async def create_user(body: RequestBody[CreateUserSchema]):
            return {"name": body.name}
    """
    
    def __class_getitem__(cls, item: type[T]) -> type:
        return Annotated[item, RequestBodyMarker()]
    
    def __new__(
        cls,
        name: str | None = None,
        default: Any = ...,
    ) -> RequestBodyMarker:
        return RequestBodyMarker(name=name, default=default)


class RequestField(Generic[T]):
    """Request Body Field 타입 힌트
    
    Body의 특정 필드만 추출합니다.
    
    사용 예:
        @PostMapping("/users")
        async def create_user(
            username: RequestField[str],
            email: RequestField[str],
        ):
            return {"username": username, "email": email}
    """
    
    def __class_getitem__(cls, item: type[T]) -> type:
        return Annotated[item, RequestFieldMarker()]
    
    def __new__(
        cls,
        name: str | None = None,
        default: Any = ...,
    ) -> RequestFieldMarker:
        return RequestFieldMarker(name=name, default=default)


class Header(Generic[T]):
    """HTTP Header 타입 힌트
    
    사용 예:
        @GetMapping("/profile")
        async def get_profile(
            authorization: Header[str],
            x_request_id: Header[str | None] = Header(name="X-Request-ID", default=None),
        ):
            ...
    """
    
    def __class_getitem__(cls, item: type[T]) -> type:
        return Annotated[item, HeaderMarker()]
    
    def __new__(
        cls,
        name: str | None = None,
        default: Any = ...,
    ) -> HeaderMarker:
        return HeaderMarker(name=name, default=default)


class Cookie(Generic[T]):
    """Cookie 타입 힌트
    
    사용 예:
        @GetMapping("/profile")
        async def get_profile(session_id: Cookie[str]):
            ...
    """
    
    def __class_getitem__(cls, item: type[T]) -> type:
        return Annotated[item, CookieMarker()]
    
    def __new__(
        cls,
        name: str | None = None,
        default: Any = ...,
    ) -> CookieMarker:
        return CookieMarker(name=name, default=default)


# =============================================================================
# Helper Functions
# =============================================================================


def get_param_marker(annotation: Any) -> tuple[type, ParamMarker | None]:
    """타입 어노테이션에서 파라미터 마커 추출
    
    Returns:
        (actual_type, marker) 튜플
        마커가 없으면 (annotation, None)
    
    Examples:
        >>> get_param_marker(PathVariable[int])
        (int, PathVariableMarker())
        
        >>> get_param_marker(Annotated[str, QueryMarker(default="test")])
        (str, QueryMarker(default="test"))
        
        >>> get_param_marker(str)
        (str, None)
    """
    origin = get_origin(annotation)
    
    # Annotated[T, ...] 형태인지 확인
    if origin is Annotated:
        args = get_args(annotation)
        if len(args) >= 2:
            actual_type = args[0]
            for arg in args[1:]:
                if isinstance(arg, ParamMarker):
                    return (actual_type, arg)
            return (actual_type, None)
    
    return (annotation, None)


def is_optional(annotation: Any) -> tuple[bool, type]:
    """Optional[T] 또는 T | None 인지 확인
    
    Returns:
        (is_optional, inner_type)
    """
    origin = get_origin(annotation)
    
    # Union 타입 (T | None)
    if origin is type(None | int):  # types.UnionType
        args = get_args(annotation)
        non_none_args = [a for a in args if a is not type(None)]
        if len(non_none_args) == 1 and type(None) in args:
            return (True, non_none_args[0])
    
    return (False, annotation)
