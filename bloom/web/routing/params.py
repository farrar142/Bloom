"""bloom.web.routing.params - Parameter type annotations for routing"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar, get_origin, get_args, Annotated

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


@dataclass(frozen=True)
class UploadedFileMarker(ParamMarker):
    """Uploaded File 마커

    사용 예:
        @PostMapping("/upload")
        async def upload_file(file: UploadedFile):
            content = await file.read()
            return {"filename": file.filename, "size": file.size}
    """

    required: bool = True


@dataclass(frozen=True)
class AuthenticationMarker(ParamMarker):
    """Authentication 마커 (현재 인증된 사용자)

    사용 예:
        @GetMapping("/me")
        async def get_current_user(auth: Authentication[int]):
            return {"user_id": auth.id}
    """

    pass


# =============================================================================
# Type Aliases using Annotated
# =============================================================================


class _PathVariable(Generic[T]):
    """Path Variable 타입 힌트

    실제로는 Annotated[T, PathVariableMarker()]로 사용됩니다.

    사용 예:
        @GetMapping("/users/{id}")
        async def get_user(id: PathVariable[int]):
            return {"id": id}
    """

    def __class_getitem__(cls, item: type[T]) -> Any:
        return Annotated[item, PathVariableMarker()]


if TYPE_CHECKING:
    type PathVariable[T] = Annotated[T, PathVariableMarker]
else:
    PathVariable = _PathVariable


class _Query(Generic[T]):
    """Query Parameter 타입 힌트

    사용 예:
        @GetMapping("/users")
        async def list_users(
            page: Query[int],
            size: Query[int],
        ):
            return {"page": page, "size": size}
    """

    def __class_getitem__(cls, item: type[T]) -> Any:
        return Annotated[item, QueryMarker()]


if TYPE_CHECKING:
    type Query[T] = Annotated[T, QueryMarker]
else:
    Query = _Query


class _RequestBody(Generic[T]):
    """Request Body 타입 힌트

    사용 예:
        @PostMapping("/users")
        async def create_user(body: RequestBody[CreateUserSchema]):
            return {"name": body.name}
    """

    def __class_getitem__(cls, item: type[T]) -> Any:
        return Annotated[item, RequestBodyMarker()]


if TYPE_CHECKING:
    type RequestBody[T] = Annotated[T, RequestBodyMarker]
else:
    RequestBody = _RequestBody


class _RequestField(Generic[T]):
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

    def __class_getitem__(cls, item: type[T]) -> Any:
        return Annotated[item, RequestFieldMarker()]


if TYPE_CHECKING:
    type RequestField[T] = Annotated[T, RequestFieldMarker]
else:
    RequestField = _RequestField


class _Header(Generic[T]):
    """HTTP Header 타입 힌트

    사용 예:
        @GetMapping("/profile")
        async def get_profile(
            authorization: Header[str],
            x_request_id: Header[str | None],
        ):
            ...
    """

    def __class_getitem__(cls, item: type[T]) -> Any:
        return Annotated[item, HeaderMarker()]


if TYPE_CHECKING:
    type Header[T] = Annotated[T, HeaderMarker]
else:
    Header = _Header


class _Cookie(Generic[T]):
    """Cookie 타입 힌트

    사용 예:
        @GetMapping("/profile")
        async def get_profile(session_id: Cookie[str]):
            ...
    """

    def __class_getitem__(cls, item: type[T]) -> Any:
        return Annotated[item, CookieMarker()]


if TYPE_CHECKING:
    type Cookie[T] = Annotated[T, CookieMarker]
else:
    Cookie = _Cookie


class _UploadedFile:
    """Uploaded File 타입 힌트

    multipart/form-data 요청에서 업로드된 파일을 나타냅니다.

    사용 예:
        @PostMapping("/upload")
        async def upload_file(file: UploadedFile):
            content = await file.read()
            await file.save("/uploads/" + file.filename)
            return {"filename": file.filename, "size": file.size}

        # 선택적 파일
        @PostMapping("/profile")
        async def update_profile(avatar: UploadedFile | None = None):
            if avatar:
                await avatar.save(f"/avatars/{avatar.filename}")

    Note:
        실제 타입은 bloom.web.upload.UploadedFile입니다.
        이 클래스는 타입 힌트용으로만 사용됩니다.
    """

    pass


if TYPE_CHECKING:
    from ..upload import UploadedFile as _UploadedFileActual

    type UploadedFile = _UploadedFileActual
else:
    UploadedFile = _UploadedFile


class _Authentication(Generic[T]):
    """Authentication 타입 힌트 (현재 인증된 사용자)

    Spring Security의 Principal과 유사합니다.

    사용 예:
        @GetMapping("/me")
        async def get_current_user(auth: Authentication[int]):
            return {"user_id": auth.id}

        @GetMapping("/profile")
        async def get_profile(auth: Authentication[UserInfo]):
            return {"user": auth.principal}

    Authentication 객체 속성:
        - id: T (사용자 ID)
        - principal: Any (전체 사용자 정보)
        - is_authenticated: bool
        - roles: list[str]
    """

    def __class_getitem__(cls, item: type[T]) -> Any:
        return Annotated[item, AuthenticationMarker()]


if TYPE_CHECKING:
    type Authentication[T] = Annotated[T, AuthenticationMarker]
else:
    Authentication = _Authentication


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
