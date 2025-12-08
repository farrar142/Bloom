from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar, get_origin, get_args, Annotated

T = TypeVar("T")


# =============================================================================
# Parameter Markers (with Type Alias support)
# =============================================================================


@dataclass(frozen=True)
class ParamMarker:
    """파라미터 마커 베이스 클래스"""

    name: str | None = None
    default: Any = ...

    def has_default(self) -> bool:
        return self.default is not ...

    def __class_getitem__(cls, item: type):
        """PathVariable[int] → Annotated[int, PathVariable()] 변환"""
        return Annotated[item, cls()]


@dataclass(frozen=True)
class PathVariableMarker(ParamMarker):
    """Path Variable 마커 + 타입 힌트

    URL 경로의 변수를 추출합니다.

    사용 예:
        @GetMapping("/users/{user_id}")
        async def get_user(user_id: PathVariable[int]):
            return {"id": user_id}

        # 커스텀 이름
        @GetMapping("/posts/{id}")
        async def get_post(post_id: Annotated[int, PathVariable(name="id")]):
            return {"post_id": post_id}
    """

    pass


@dataclass(frozen=True)
class QueryMarker(ParamMarker):
    """Query Parameter 마커 + 타입 힌트

    URL 쿼리 파라미터를 추출합니다.

    사용 예:
        @GetMapping("/users")
        async def list_users(
            page: Query[int] = 1,
            size: Query[int] = 10,
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
class RequestBodyMarker(ParamMarker):
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
class RequestFieldMarker(ParamMarker):
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
            user_name: Annotated[str, RequestField(name="userName")],
        ):
            ...
    """

    pass


@dataclass(frozen=True)
class HeaderMarker(ParamMarker):
    """HTTP Header 마커 + 타입 힌트

    HTTP 헤더 값을 추출합니다.

    사용 예:
        @GetMapping("/profile")
        async def get_profile(
            # 파라미터 이름을 헤더명으로 사용 (authorization → Authorization)
            authorization: Header[str],
            x_request_id: Header[str | None] = None,
        ):
            ...

        # 커스텀 헤더명 지정 (타입 포함)
        @GetMapping("/api")
        async def api_call(
            api_key: Header[str, "X-API-Key"],
        ):
            ...

        # 커스텀 헤더명만 지정 (타입은 str로 간주)
        @GetMapping("/info")
        async def info(
            agent: Header["User-Agent"],  # str 타입으로 간주
        ):
            ...
    """

    @classmethod
    def __class_getitem__(cls, item):
        """Header[str], Header[str, "X-Header"], Header["X-Header"] 형태 지원"""
        if isinstance(item, tuple):
            # Header[str, "X-Custom-Header"]
            type_arg, name = item
            return Annotated[type_arg, cls(name=name)]
        elif isinstance(item, str):
            # Header["User-Agent"] - 문자열만 전달시 key 이름으로 인식, 타입은 str
            return Annotated[str, cls(name=item)]
        else:
            # Header[str]
            return Annotated[item, cls()]


@dataclass(frozen=True)
class CookieMarker(ParamMarker):
    """Cookie 마커 + 타입 힌트

    쿠키 값을 추출합니다.

    사용 예:
        @GetMapping("/profile")
        async def get_profile(
            # 파라미터 이름을 쿠키명으로 사용
            session_id: Cookie[str],
        ):
            ...

        # 커스텀 쿠키명 지정 (타입 포함)
        @GetMapping("/preferences")
        async def get_prefs(
            theme: Cookie[str, "user_theme"],
        ):
            ...

        # 커스텀 쿠키명만 지정 (타입은 str로 간주)
        @GetMapping("/session")
        async def session(
            token: Cookie["auth_token"],
        ):
            ...
    """

    @classmethod
    def __class_getitem__(cls, item):
        """Cookie[str], Cookie[str, "name"], Cookie["name"] 형태 지원"""
        if isinstance(item, tuple):
            # Cookie[str, "session_id"]
            type_arg, name = item
            return Annotated[type_arg, cls(name=name)]
        elif isinstance(item, str):
            # Cookie["session_id"] - 문자열만 전달시 key 이름으로 인식, 타입은 str
            return Annotated[str, cls(name=item)]
        else:
            # Cookie[str]
            return Annotated[item, cls()]


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
# Special Markers (without Generic type)
# =============================================================================


from .upload import UploadedFile as UploadedFile


@dataclass(frozen=True)
class UploadedFileMarker(ParamMarker):
    """Uploaded File 마커

    multipart/form-data 요청에서 업로드된 파일을 나타냅니다.
    """

    required: bool = True


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


if TYPE_CHECKING:
    type RequestBody[T] = Annotated[T, RequestBodyMarker]
    type PathVariable[T] = Annotated[T, PathVariableMarker]
    type Query[T] = Annotated[T, QueryMarker]
    type RequestField[T] = Annotated[T, RequestFieldMarker]
    type Header[T] = Annotated[T, HeaderMarker]
    type Cookie[T] = Annotated[T, CookieMarker]
else:
    RequestBody = RequestBodyMarker
    PathVariable = PathVariableMarker
    Query = QueryMarker
    RequestField = RequestFieldMarker
    Header = HeaderMarker
    Cookie = CookieMarker
