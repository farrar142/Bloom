from __future__ import annotations
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    get_origin,
    get_args,
    Annotated,
    Generic,
    TypeVar,
)


# =============================================================================
# KeyValue Container
# =============================================================================

T = TypeVar("T")


@dataclass
class KeyValue(Generic[T]):
    """키-값 쌍을 담는 컨테이너 (Cookie, Header 등에서 사용)"""

    key: str
    value: T


# =============================================================================
# Parameter Markers
# =============================================================================


@dataclass(frozen=True)
class ParamMarker:
    """파라미터 마커 베이스 클래스

    __class_getitem__을 통해 Marker[Type] 형태를 지원합니다.
    """

    name: str | None = None
    default: Any = ...

    def has_default(self) -> bool:
        return self.default is not ...

    def __class_getitem__(cls, item: Any) -> Any:
        """Marker[Type] → Annotated[Type, Marker()] 변환

        지원 형태:
            - Marker[int]           → Annotated[int, Marker()]
            - Marker[str, "name"]   → Annotated[str, Marker(name="name")]
            - Marker["name"]        → Annotated[str, Marker(name="name")]
            - Marker[Literal["x"]]  → Annotated[str, Marker(name="x")]
        """
        if isinstance(item, tuple):
            # Marker[str, "custom_name"]
            type_arg, name = item
            return Annotated[type_arg, cls(name=name)]
        elif isinstance(item, str):
            # Marker["custom_name"] - 문자열만 전달시 이름으로 인식, 타입은 str
            return Annotated[str, cls(name=item)]
        elif get_origin(item) is Literal:
            # Marker[Literal["name"]] - Literal에서 문자열 추출
            literal_args = get_args(item)
            if literal_args and isinstance(literal_args[0], str):
                return Annotated[str, cls(name=literal_args[0])]
            return Annotated[str, cls()]
        else:
            # Marker[int], Marker[str] 등
            return Annotated[item, cls()]


@dataclass(frozen=True)
class PathVariable(ParamMarker):
    """Path Variable 마커 + 타입 힌트

    URL 경로의 변수를 추출합니다.

    사용 예:
        @GetMapping("/users/{user_id}")
        async def get_user(user_id: PathVariable[int]):
            return {"id": user_id}

        # 커스텀 이름
        @GetMapping("/posts/{id}")
        async def get_post(post_id: PathVariable[int, "id"]):
            return {"post_id": post_id}
    """

    pass


@dataclass(frozen=True)
class Query(ParamMarker):
    """Query Parameter 마커 + 타입 힌트

    URL 쿼리 파라미터를 추출합니다.

    사용 예:
        @GetMapping("/users")
        async def list_users(
            page: Query[int],
            size: Query[int],
        ):
            return {"page": page, "size": size}

        # default 지정
        @GetMapping("/search")
        async def search(
            q: Query[str],
            limit: Query[int] = Query(default=10),
        ):
            ...
    """

    pass


@dataclass(frozen=True)
class RequestBody(ParamMarker):
    """Request Body 마커 + 타입 힌트

    요청 본문 전체를 파싱합니다.

    사용 예:
        @PostMapping("/users")
        async def create_user(body: RequestBody[CreateUserSchema]):
            return {"name": body.name}

        # dict로 받기
        @PostMapping("/data")
        async def receive_data(data: RequestBody[dict]):
            return data
    """

    pass


@dataclass(frozen=True)
class RequestField(ParamMarker):
    """Request Body Field 마커 + 타입 힌트

    요청 본문의 특정 필드만 추출합니다.

    사용 예:
        @PostMapping("/users")
        async def create_user(
            username: RequestField[str],  # body["username"]
            email: RequestField[str],     # body["email"]
        ):
            return {"username": username, "email": email}

        # 커스텀 필드명
        @PostMapping("/data")
        async def receive(
            user_name: RequestField[str, "userName"],
        ):
            ...
    """

    pass


@dataclass(frozen=True)
class _HeaderImpl(ParamMarker):
    """HTTP Header 마커 + 타입 힌트 (런타임 구현)

    HTTP 헤더 값을 추출합니다. 반환 타입은 KeyValue[str]입니다.

    사용 예:
        @GetMapping("/profile")
        async def get_profile(
            # 파라미터 이름을 헤더명으로 사용 (user_agent → User-Agent)
            user_agent: Header[str],
        ):
            return {"agent": user_agent.value}

        # 커스텀 헤더명 지정
        @GetMapping("/api")
        async def api_call(
            api_key: Header[str, "X-API-Key"],
        ):
            return {"key": api_key.value}

        # Literal로 헤더명 지정 (Pylance 타입 에러 방지)
        @GetMapping("/info")
        async def info(
            agent: Header[Literal["User-Agent"]],
        ):
            return {"agent": agent.value}
    """

    def __class_getitem__(cls, item: Any) -> Any:
        """Header[Type] → Annotated[KeyValue[str], Header()] 변환"""
        if isinstance(item, tuple):
            type_arg, name = item
            return Annotated[KeyValue[str], cls(name=name)]
        elif isinstance(item, str):
            return Annotated[KeyValue[str], cls(name=item)]
        elif get_origin(item) is Literal:
            literal_args = get_args(item)
            if literal_args and isinstance(literal_args[0], str):
                return Annotated[KeyValue[str], cls(name=literal_args[0])]
            return Annotated[KeyValue[str], cls()]
        else:
            return Annotated[KeyValue[str], cls()]


@dataclass(frozen=True)
class _CookieImpl(ParamMarker):
    """Cookie 마커 + 타입 힌트 (런타임 구현)

    쿠키 값을 추출합니다. 반환 타입은 KeyValue[str]입니다.

    사용 예:
        @GetMapping("/profile")
        async def get_profile(
            # 파라미터 이름을 쿠키명으로 사용
            session_id: Cookie[str],
        ):
            return {"session": session_id.value}

        # 커스텀 쿠키명 지정
        @GetMapping("/preferences")
        async def get_prefs(
            theme: Cookie[str, "user_theme"],
        ):
            return {"theme": theme.value}

        # Literal로 쿠키명 지정 (Pylance 타입 에러 방지)
        @GetMapping("/session")
        async def session(
            token: Cookie[Literal["auth_token"]],
        ):
            return {"token": token.value}
    """

    def __class_getitem__(cls, item: Any) -> Any:
        """Cookie[Type] → Annotated[KeyValue[str], Cookie()] 변환"""
        if isinstance(item, tuple):
            type_arg, name = item
            return Annotated[KeyValue[str], cls(name=name)]
        elif isinstance(item, str):
            return Annotated[KeyValue[str], cls(name=item)]
        elif get_origin(item) is Literal:
            literal_args = get_args(item)
            if literal_args and isinstance(literal_args[0], str):
                return Annotated[KeyValue[str], cls(name=literal_args[0])]
            return Annotated[KeyValue[str], cls()]
        else:
            return Annotated[KeyValue[str], cls()]


@dataclass(frozen=True)
class Authentication(ParamMarker):
    """Authentication 마커 + 타입 힌트 (현재 인증된 사용자)

    Spring Security의 Principal과 유사합니다.

    사용 예:
        @GetMapping("/me")
        async def get_current_user(auth: Authentication[int]):
            return {"user_id": auth}

        @GetMapping("/profile")
        async def get_profile(user: Authentication[UserInfo]):
            return {"user": user}
    """

    pass


# =============================================================================
# Special Markers
# =============================================================================


from .upload import UploadedFile as UploadedFile


@dataclass(frozen=True)
class UploadedFileMarker(ParamMarker):
    """Uploaded File 마커

    multipart/form-data 요청에서 업로드된 파일을 나타냅니다.
    """

    required: bool = True


# =============================================================================
# TYPE_CHECKING: 정적 분석기용 타입 재정의
# =============================================================================
# Pylance/mypy가 Header[T] 및 Cookie[T]를 KeyValue[str]로 올바르게 추론하도록
# TYPE_CHECKING 블록 내에서 KeyValue를 상속하는 Generic 버전으로 재정의합니다.

if TYPE_CHECKING:

    class Header(KeyValue[str], Generic[T]):
        """정적 분석용 Header - Header[T]가 KeyValue[str]처럼 동작"""

        name: str | None
        default: Any

        def __init__(self, *, name: str | None = None, default: Any = ...) -> None: ...
        def has_default(self) -> bool: ...

    class Cookie(KeyValue[str], Generic[T]):
        """정적 분석용 Cookie - Cookie[T]가 KeyValue[str]처럼 동작"""

        name: str | None
        default: Any

        def __init__(self, *, name: str | None = None, default: Any = ...) -> None: ...
        def has_default(self) -> bool: ...

else:
    # 런타임에는 실제 구현체 사용
    Header = _HeaderImpl
    Cookie = _CookieImpl


# =============================================================================
# Type Aliases for backwards compatibility
# =============================================================================

# 이전 코드와의 호환성을 위한 별칭
PathVariableMarker = PathVariable
QueryMarker = Query
RequestBodyMarker = RequestBody
RequestFieldMarker = RequestField
HeaderMarker = Header
CookieMarker = Cookie


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
        (int, PathVariable())

        >>> get_param_marker(Annotated[str, Query(default="test")])
        (str, Query(default="test"))

        >>> get_param_marker(str)
        (str, None)

        >>> get_param_marker(Header)  # 마커 클래스 자체
        (str, Header())
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

    # 마커 클래스 자체가 전달된 경우 (예: Header, Cookie 등 제네릭 없이 사용)
    if isinstance(annotation, type) and issubclass(annotation, ParamMarker):
        return (str, annotation())

    return (annotation, None)


def is_optional(annotation: Any) -> tuple[bool, type]:
    """Optional 또는 T | None 인지 확인

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
