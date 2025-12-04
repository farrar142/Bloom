"""bloom.web.auth - Authentication & Authorization"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar, TYPE_CHECKING, Union, get_origin, get_args

if TYPE_CHECKING:
    from .request import Request
    from .messaging.websocket import WebSocketSession


T = TypeVar("T")


# =============================================================================
# Authentication Base Class
# =============================================================================


class Authentication(Generic[T]):
    """
    인증 정보 베이스 클래스.

    사용자는 이 클래스를 상속하여 커스텀 인증 정보를 정의합니다.
    `id` 속성은 반드시 정의해야 합니다.

    사용 예:
        @dataclass
        class CustomAuthentication(Authentication[int]):
            id: int
            username: str
            email: str

        # 컨트롤러에서 사용
        @PostMapping("/posts")
        async def create_post(self, auth: CustomAuthentication):
            return {"author_id": auth.id}
    """

    id: T
    """사용자 ID (제네릭 타입) - 서브클래스에서 정의"""

    def __init_subclass__(cls, **kwargs):
        """서브클래스 생성 시 id 속성 검증"""
        super().__init_subclass__(**kwargs)
        # dataclass는 __annotations__에 id를 가지고 있어야 함
        # 단, Generic 상속 클래스는 제외
        if cls.__name__ not in ("AuthenticationInfo", "AnonymousAuthentication"):
            annotations = getattr(cls, "__annotations__", {})
            if "id" not in annotations and not hasattr(cls, "id"):
                # 직접 상속이 아닌 경우 허용 (AuthenticationInfo 상속 등)
                pass


# =============================================================================
# Authentication Info (Legacy, 하위 호환성)
# =============================================================================


@dataclass
class AuthenticationInfo(Authentication[T]):
    """
    인증 정보 객체.

    Spring Security의 Authentication/Principal과 유사합니다.

    사용 예:
        # 미들웨어에서 인증 정보 설정
        request.state.authentication = AuthenticationInfo(
            id=user.id,
            principal=user,
            roles=["admin"],
        )

        # 컨트롤러에서 사용
        @GetMapping("/me")
        async def get_current_user(auth: Authentication[int]):
            return {"user_id": auth.id}
    """

    id: T
    """사용자 ID (제네릭 타입)"""

    principal: Any = None
    """전체 사용자 정보 (User 객체 등)"""

    is_authenticated: bool = True
    """인증 여부"""

    roles: list[str] = field(default_factory=list)
    """사용자 역할/권한"""

    attributes: dict[str, Any] = field(default_factory=dict)
    """추가 속성"""

    def has_role(self, role: str) -> bool:
        """특정 역할 보유 여부"""
        return role in self.roles

    def has_any_role(self, *roles: str) -> bool:
        """주어진 역할 중 하나라도 보유 여부"""
        return any(role in self.roles for role in roles)

    def has_all_roles(self, *roles: str) -> bool:
        """주어진 역할을 모두 보유 여부"""
        return all(role in self.roles for role in roles)


@dataclass
class AnonymousAuthentication(AuthenticationInfo[None]):
    """익명 사용자 인증 정보"""

    id: None = None
    principal: Any = None
    is_authenticated: bool = False
    roles: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# AuthContext - HTTP/WebSocket 통합 컨텍스트
# =============================================================================


@dataclass
class AuthContext:
    """
    인증 컨텍스트.

    HTTP Request와 WebSocket Session을 추상화하여
    동일한 인터페이스로 인증을 처리합니다.

    사용 예:
        # HTTP Request에서 생성
        context = AuthContext.from_request(request)

        # WebSocket Session에서 생성
        context = AuthContext.from_websocket(session)

        # 인증기에서 사용
        class MyAuthenticator(Authenticator):
            async def authenticate(self, context: AuthContext):
                token = context.headers.get("authorization")
                ...
    """

    headers: dict[str, str]
    """HTTP 헤더 (소문자 키)"""

    cookies: dict[str, str]
    """쿠키"""

    path: str
    """요청 경로"""

    query_string: str
    """쿼리 스트링"""

    is_http: bool = True
    """HTTP 요청 여부"""

    is_websocket: bool = False
    """WebSocket 요청 여부"""

    session_id: str | None = None
    """WebSocket 세션 ID (WebSocket인 경우)"""

    _request: "Request | None" = field(default=None, repr=False)
    """원본 HTTP Request 객체"""

    _websocket: "WebSocketSession | None" = field(default=None, repr=False)
    """원본 WebSocket Session 객체"""

    @classmethod
    def from_request(cls, request: "Request") -> "AuthContext":
        """HTTP Request에서 AuthContext 생성"""
        return cls(
            headers=request.headers,
            cookies=request.cookies,
            path=request.path,
            query_string=request.query_string.decode("utf-8"),
            is_http=True,
            is_websocket=False,
            session_id=None,
            _request=request,
        )

    @classmethod
    def from_websocket(cls, session: "WebSocketSession") -> "AuthContext":
        """WebSocket Session에서 AuthContext 생성"""
        # 헤더 파싱
        raw_headers = session.scope.get("headers", [])
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in raw_headers
        }

        # 쿠키 파싱
        cookies: dict[str, str] = {}
        cookie_header = headers.get("cookie", "")
        if cookie_header:
            for item in cookie_header.split(";"):
                item = item.strip()
                if "=" in item:
                    key, value = item.split("=", 1)
                    cookies[key.strip()] = value.strip()

        return cls(
            headers=headers,
            cookies=cookies,
            path=session.scope.get("path", "/"),
            query_string=session.scope.get("query_string", b"").decode("utf-8"),
            is_http=False,
            is_websocket=True,
            session_id=session.session_id,
            _websocket=session,
        )

    @property
    def request(self) -> "Request | None":
        """원본 HTTP Request (HTTP인 경우)"""
        return self._request

    @property
    def websocket(self) -> "WebSocketSession | None":
        """원본 WebSocket Session (WebSocket인 경우)"""
        return self._websocket


# =============================================================================
# Authenticator Interface
# =============================================================================


A = TypeVar("A", bound=Authentication)


class Authenticator(ABC, Generic[A]):
    """
    인증기 추상 클래스.

    사용자는 이 클래스를 상속하여 커스텀 인증기를 구현합니다.

    사용 예:
        @Component
        class JwtAuthenticator(Authenticator[UserAuth]):
            user_service: UserService  # DI 주입

            async def supports(self, context: AuthContext) -> bool:
                auth_header = context.headers.get("authorization", "")
                return auth_header.startswith("Bearer ")

            async def authenticate(self, context: AuthContext) -> UserAuth | None:
                token = context.headers.get("authorization", "")[7:]
                user = await self.user_service.verify_token(token)
                if user:
                    return UserAuth(id=user.id, username=user.username)
                return None
    """

    @abstractmethod
    async def supports(self, context: AuthContext) -> bool:
        """
        이 인증기가 주어진 컨텍스트를 처리할 수 있는지 확인.

        Args:
            context: 인증 컨텍스트

        Returns:
            처리 가능 여부
        """
        ...

    @abstractmethod
    async def authenticate(self, context: AuthContext) -> A | None:
        """
        인증 수행.

        Args:
            context: 인증 컨텍스트

        Returns:
            인증 정보 또는 None (인증 실패 시)

        Raises:
            AuthenticationException: 인증 오류 시
        """
        ...


# =============================================================================
# Authentication Exception
# =============================================================================


class AuthenticationException(Exception):
    """
    인증 예외.

    인증 실패 시 발생하며, HTTP 401/403 응답으로 변환됩니다.

    사용 예:
        raise AuthenticationException("Invalid token")
        raise AuthenticationException("Forbidden", status_code=403)
    """

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


# =============================================================================
# AuthenticatorGroup
# =============================================================================


class AuthenticatorGroup:
    """
    인증기 그룹.

    특정 경로 패턴에 대해 여러 인증기를 체인으로 연결합니다.
    첫 번째로 supports()가 True인 인증기가 인증을 수행합니다.

    사용 예:
        group = AuthenticatorGroup(path="/api/v1")
        group.add(JwtAuthenticator(), ApiKeyAuthenticator())
    """

    def __init__(self, path: str = "") -> None:
        self.path = path
        self.authenticators: list[Authenticator] = []

    def add(self, *authenticators: Authenticator) -> "AuthenticatorGroup":
        """인증기 추가"""
        self.authenticators.extend(authenticators)
        return self

    def matches(self, request_path: str) -> bool:
        """경로가 이 그룹과 매칭되는지 확인"""
        if not self.path:
            return True

        # 와일드카드 지원
        if self.path.endswith("/*"):
            prefix = self.path[:-2]
            return request_path.startswith(prefix)
        if self.path.endswith("/**"):
            prefix = self.path[:-3]
            return request_path.startswith(prefix)

        return request_path.startswith(self.path)

    async def authenticate(self, context: AuthContext) -> Authentication | None:
        """
        인증 수행.

        체인의 각 인증기를 순회하며 첫 번째로 supports()가 True인
        인증기로 인증을 시도합니다.

        Returns:
            인증 정보 또는 None
        """
        for authenticator in self.authenticators:
            if await authenticator.supports(context):
                return await authenticator.authenticate(context)
        return None


# =============================================================================
# AuthMiddleware
# =============================================================================


class AuthMiddleware:
    """
    인증 미들웨어.

    경로별로 다른 인증기 그룹을 설정할 수 있습니다.

    사용 예:
        @Configuration
        class AuthConfig:
            @Factory
            def auth_middleware(
                self,
                jwt_auth: JwtAuthenticator,
                api_key_auth: ApiKeyAuthenticator,
            ) -> AuthMiddleware:
                middleware = AuthMiddleware()

                api_group = middleware.add_group(path="/api/v1")
                api_group.add(jwt_auth, api_key_auth)

                admin_group = middleware.add_group(path="/api/admin")
                admin_group.add(jwt_auth)

                return middleware
    """

    def __init__(self) -> None:
        self.groups: list[AuthenticatorGroup] = []

    def add_group(self, path: str = "") -> AuthenticatorGroup:
        """인증기 그룹 추가"""
        group = AuthenticatorGroup(path=path)
        self.groups.append(group)
        return group

    async def authenticate(self, context: AuthContext) -> Authentication | None:
        """
        인증 수행.

        매칭되는 그룹을 찾아 인증을 시도합니다.

        Returns:
            인증 정보 또는 None
        """
        for group in self.groups:
            if group.matches(context.path):
                auth = await group.authenticate(context)
                if auth is not None:
                    return auth
        return None


# =============================================================================
# Helper Functions
# =============================================================================


def is_authentication_type(hint: type) -> bool:
    """
    타입 힌트가 Authentication 서브클래스인지 확인.

    Args:
        hint: 타입 힌트

    Returns:
        Authentication 서브클래스 여부
    """
    try:
        if hint is Authentication:
            return True
        if isinstance(hint, type) and issubclass(hint, Authentication):
            return True
    except TypeError:
        pass
    return False


def get_authentication_param_marker(hint: type) -> type | None:
    """
    파라미터 타입에서 Authentication 타입 추출.

    Optional[UserAuth] 같은 경우도 처리합니다.

    Args:
        hint: 파라미터 타입 힌트

    Returns:
        Authentication 서브클래스 또는 None
    """
    # 직접 Authentication 서브클래스인 경우
    if is_authentication_type(hint):
        return hint

    # Optional[T] = Union[T, None] 처리
    origin = get_origin(hint)
    if origin is Union:
        args = get_args(hint)
        for arg in args:
            if arg is not type(None) and is_authentication_type(arg):
                return arg

    return None


# =============================================================================
# Decorators
# =============================================================================


def Authenticated(func=None, *, roles: list[str] | None = None):
    """
    인증 필수 데코레이터.

    인증되지 않은 요청은 401 Unauthorized를 반환합니다.
    roles가 지정되면 해당 역할이 필요합니다.

    사용 예:
        @Controller
        class AdminController:
            @GetMapping("/admin")
            @Authenticated(roles=["admin"])
            async def admin_page(self, auth: Authentication[int]):
                return {"admin_id": auth.id}
    """

    def decorator(fn):
        fn.__bloom_authenticated__ = True  # type: ignore
        fn.__bloom_required_roles__ = roles or []  # type: ignore
        return fn

    if func is not None:
        return decorator(func)
    return decorator


def get_authentication_metadata(func) -> dict[str, Any] | None:
    """함수의 인증 메타데이터 조회"""
    if not getattr(func, "__bloom_authenticated__", False):
        return None

    return {
        "authenticated": True,
        "roles": getattr(func, "__bloom_required_roles__", []),
    }
