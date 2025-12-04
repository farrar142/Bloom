"""Authentication 모듈 테스트

TDD 기반으로 Authentication 시스템을 테스트합니다.

테스트 범위:
1. Authentication 베이스 클래스 및 커스텀 인증 정보
2. Authenticator 인터페이스 및 구현
3. AuthContext - HTTP/WebSocket 통합 컨텍스트
4. AuthMiddleware - 인증 미들웨어
5. Authentication 파라미터 주입
"""

import pytest
from dataclasses import dataclass
from typing import Optional

from bloom.core import (
    Component,
    Service,
    Configuration,
    Factory,
    reset_container_manager,
    get_container_manager,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
async def setup_and_teardown():
    """각 테스트 전후로 컨테이너 초기화"""
    reset_container_manager()
    yield
    manager = get_container_manager()
    await manager.scope_manager.destroy_singletons()
    reset_container_manager()


# =============================================================================
# Test: Authentication Base Class
# =============================================================================


class TestAuthenticationBase:
    """Authentication 베이스 클래스 테스트"""

    def test_authentication_base_class_exists(self):
        """Authentication 베이스 클래스가 존재하고 id 속성을 요구함"""
        from bloom.web.auth import Authentication

        # Authentication은 Generic[T] 베이스 클래스
        # 직접 인스턴스화는 가능하지만 id 속성이 없으면 에러
        assert hasattr(Authentication, "__annotations__")

    def test_custom_authentication_can_inherit(self):
        """사용자가 Authentication을 상속하여 커스텀 인증 정보 생성 가능"""
        from bloom.web.auth import Authentication

        @dataclass
        class CustomAuthentication(Authentication[int]):
            id: int
            username: str
            email: str

        auth = CustomAuthentication(id=1, username="testuser", email="test@example.com")
        assert auth.id == 1
        assert auth.username == "testuser"
        assert auth.email == "test@example.com"

    def test_authentication_generic_type(self):
        """Authentication은 제네릭 타입을 지원해야 함"""
        from bloom.web.auth import Authentication

        @dataclass
        class StringIdAuth(Authentication[str]):
            id: str
            name: str

        auth = StringIdAuth(id="uuid-123", name="User")
        assert auth.id == "uuid-123"

    def test_anonymous_authentication(self):
        """AnonymousAuthentication은 미인증 상태를 표현"""
        from bloom.web.auth import AnonymousAuthentication

        anon = AnonymousAuthentication()
        assert anon.id is None
        assert anon.is_authenticated is False


# =============================================================================
# Test: AuthContext (HTTP/WebSocket 통합)
# =============================================================================


class TestAuthContext:
    """AuthContext - HTTP와 WebSocket 통합 컨텍스트 테스트"""

    def test_auth_context_from_http_request(self):
        """HTTP Request에서 AuthContext 생성"""
        from bloom.web.auth import AuthContext
        from bloom.web.request import Request

        # Mock HTTP Request 생성
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/users",
            "headers": [
                (b"authorization", b"Bearer token123"),
                (b"x-api-key", b"key456"),
            ],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        request = Request(scope, receive)
        context = AuthContext.from_request(request)

        assert context.headers.get("authorization") == "Bearer token123"
        assert context.headers.get("x-api-key") == "key456"
        assert context.path == "/api/users"
        assert context.is_http is True
        assert context.is_websocket is False

    def test_auth_context_from_websocket_session(self):
        """WebSocket Session에서 AuthContext 생성"""
        from bloom.web.auth import AuthContext
        from bloom.web.messaging.websocket import WebSocketSession, WebSocketState

        # Mock WebSocket Session 생성
        scope = {
            "type": "websocket",
            "path": "/ws/chat",
            "headers": [(b"authorization", b"Bearer wstoken")],
            "query_string": b"room=general",
        }

        async def receive():
            return {"type": "websocket.disconnect"}

        async def send(msg):
            pass

        session = WebSocketSession(
            scope=scope,
            receive=receive,
            send=send,
            session_id="session-1",
            user_id=None,
            state=WebSocketState.CONNECTED,
            _accepted=True,
        )
        context = AuthContext.from_websocket(session)

        assert context.headers.get("authorization") == "Bearer wstoken"
        assert context.path == "/ws/chat"
        assert context.is_http is False
        assert context.is_websocket is True
        assert context.session_id == "session-1"

    def test_auth_context_cookies(self):
        """AuthContext에서 쿠키 접근"""
        from bloom.web.auth import AuthContext
        from bloom.web.request import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"cookie", b"session=abc123; token=xyz")],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        request = Request(scope, receive)
        context = AuthContext.from_request(request)

        assert context.cookies.get("session") == "abc123"
        assert context.cookies.get("token") == "xyz"


# =============================================================================
# Test: Authenticator Interface
# =============================================================================


class TestAuthenticator:
    """Authenticator 인터페이스 테스트"""

    @pytest.mark.asyncio
    async def test_authenticator_is_abstract(self):
        """Authenticator는 추상 클래스여야 함"""
        from bloom.web.auth import Authenticator

        with pytest.raises(TypeError):
            Authenticator()  # type: ignore

    @pytest.mark.asyncio
    async def test_custom_authenticator_implementation(self):
        """커스텀 Authenticator 구현"""
        from bloom.web.auth import Authenticator, AuthContext, Authentication

        @dataclass
        class UserAuth(Authentication[int]):
            id: int
            username: str

        class ApiKeyAuthenticator(Authenticator[UserAuth]):
            async def supports(self, context: AuthContext) -> bool:
                return context.headers.get("x-api-key") is not None

            async def authenticate(self, context: AuthContext) -> Optional[UserAuth]:
                api_key = context.headers.get("x-api-key")
                if api_key == "valid-key":
                    return UserAuth(id=1, username="api_user")
                return None

        authenticator = ApiKeyAuthenticator()

        # supports 테스트
        from bloom.web.request import Request

        scope_with_key = {
            "type": "http",
            "path": "/",
            "headers": [(b"x-api-key", b"valid-key")],
            "query_string": b"",
        }
        scope_without_key = {
            "type": "http",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        ctx_with_key = AuthContext.from_request(Request(scope_with_key, receive))
        ctx_without_key = AuthContext.from_request(Request(scope_without_key, receive))

        assert await authenticator.supports(ctx_with_key) is True
        assert await authenticator.supports(ctx_without_key) is False

        # authenticate 테스트
        auth = await authenticator.authenticate(ctx_with_key)
        assert auth is not None
        assert auth.id == 1
        assert auth.username == "api_user"

    @pytest.mark.asyncio
    async def test_authenticator_with_di_injection(self):
        """DI를 통한 서비스 주입이 가능한 Authenticator"""
        from bloom.web.auth import Authenticator, AuthContext, Authentication

        @dataclass
        class UserAuth(Authentication[int]):
            id: int
            username: str

        @Service
        class UserService:
            def get_user_by_api_key(self, api_key: str) -> Optional[dict]:
                if api_key == "valid-key":
                    return {"id": 42, "username": "service_user"}
                return None

        @Component
        class DIAuthenticator(Authenticator[UserAuth]):
            user_service: UserService

            async def supports(self, context: AuthContext) -> bool:
                return context.headers.get("x-api-key") is not None

            async def authenticate(self, context: AuthContext) -> Optional[UserAuth]:
                api_key = context.headers.get("x-api-key")
                if not api_key:
                    return None
                user = self.user_service.get_user_by_api_key(api_key)
                if user:
                    return UserAuth(id=user["id"], username=user["username"])
                return None

        manager = get_container_manager()
        await manager.initialize()

        authenticator = await manager.get_instance_async(DIAuthenticator)

        scope = {
            "type": "http",
            "path": "/",
            "headers": [(b"x-api-key", b"valid-key")],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        from bloom.web.request import Request

        ctx = AuthContext.from_request(Request(scope, receive))
        auth = await authenticator.authenticate(ctx)

        assert auth is not None
        assert auth.id == 42
        assert auth.username == "service_user"


# =============================================================================
# Test: AuthenticationException
# =============================================================================


class TestAuthenticationException:
    """인증 예외 테스트"""

    def test_authentication_exception(self):
        """AuthenticationException 기본 사용"""
        from bloom.web.auth import AuthenticationException

        exc = AuthenticationException("Invalid credentials")
        assert str(exc) == "Invalid credentials"
        assert exc.status_code == 401

    def test_authentication_exception_custom_status(self):
        """커스텀 상태 코드"""
        from bloom.web.auth import AuthenticationException

        exc = AuthenticationException("Forbidden", status_code=403)
        assert exc.status_code == 403


# =============================================================================
# Test: AuthMiddleware
# =============================================================================


class TestAuthMiddleware:
    """AuthMiddleware 테스트"""

    @pytest.mark.asyncio
    async def test_auth_middleware_basic_setup(self):
        """AuthMiddleware 기본 설정"""
        from bloom.web.auth import (
            AuthMiddleware,
            Authenticator,
            AuthContext,
            Authentication,
        )

        @dataclass
        class SimpleAuth(Authentication[int]):
            id: int

        class SimpleAuthenticator(Authenticator[SimpleAuth]):
            async def supports(self, context: AuthContext) -> bool:
                return "authorization" in context.headers

            async def authenticate(self, context: AuthContext) -> Optional[SimpleAuth]:
                auth_header = context.headers.get("authorization", "")
                if auth_header == "Bearer valid":
                    return SimpleAuth(id=1)
                return None

        middleware = AuthMiddleware()
        # 그룹 추가 및 인증기 등록
        group = middleware.add_group(path="/api/v1")
        group.add(SimpleAuthenticator())

        assert len(middleware.groups) == 1
        assert middleware.groups[0].path == "/api/v1"

    @pytest.mark.asyncio
    async def test_auth_middleware_multiple_groups(self):
        """여러 경로 그룹 설정"""
        from bloom.web.auth import (
            AuthMiddleware,
            Authenticator,
            AuthContext,
            Authentication,
        )

        @dataclass
        class Auth(Authentication[int]):
            id: int

        class Auth1(Authenticator[Auth]):
            async def supports(self, context: AuthContext) -> bool:
                return True

            async def authenticate(self, context: AuthContext) -> Optional[Auth]:
                return Auth(id=1)

        class Auth2(Authenticator[Auth]):
            async def supports(self, context: AuthContext) -> bool:
                return True

            async def authenticate(self, context: AuthContext) -> Optional[Auth]:
                return Auth(id=2)

        middleware = AuthMiddleware()

        api_group = middleware.add_group(path="/api/v1")
        api_group.add(Auth1())

        admin_group = middleware.add_group(path="/api/admin")
        admin_group.add(Auth1(), Auth2())

        assert len(middleware.groups) == 2
        assert len(admin_group.authenticators) == 2

    @pytest.mark.asyncio
    async def test_auth_middleware_authenticator_chain(self):
        """인증기 체인 - 첫 번째 성공한 인증기 사용"""
        from bloom.web.auth import (
            AuthMiddleware,
            AuthenticatorGroup,
            Authenticator,
            AuthContext,
            Authentication,
        )
        from bloom.web.request import Request

        @dataclass
        class Auth(Authentication[int]):
            id: int
            source: str

        class JwtAuthenticator(Authenticator[Auth]):
            async def supports(self, context: AuthContext) -> bool:
                auth_header = context.headers.get("authorization", "")
                return auth_header.startswith("Bearer ")

            async def authenticate(self, context: AuthContext) -> Optional[Auth]:
                auth_header = context.headers.get("authorization", "")
                if auth_header == "Bearer jwt-token":
                    return Auth(id=1, source="jwt")
                return None

        class ApiKeyAuthenticator(Authenticator[Auth]):
            async def supports(self, context: AuthContext) -> bool:
                return "x-api-key" in context.headers

            async def authenticate(self, context: AuthContext) -> Optional[Auth]:
                if context.headers.get("x-api-key") == "valid-api-key":
                    return Auth(id=2, source="api-key")
                return None

        group = AuthenticatorGroup(path="/api")
        group.add(JwtAuthenticator(), ApiKeyAuthenticator())

        # JWT 인증
        scope_jwt = {
            "type": "http",
            "path": "/api/users",
            "headers": [(b"authorization", b"Bearer jwt-token")],
            "query_string": b"",
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        ctx_jwt = AuthContext.from_request(Request(scope_jwt, receive))
        auth = await group.authenticate(ctx_jwt)
        assert auth is not None
        assert auth.source == "jwt"

        # API Key 인증
        scope_api = {
            "type": "http",
            "path": "/api/users",
            "headers": [(b"x-api-key", b"valid-api-key")],
            "query_string": b"",
        }
        ctx_api = AuthContext.from_request(Request(scope_api, receive))
        auth = await group.authenticate(ctx_api)
        assert auth is not None
        assert auth.source == "api-key"

        # 인증 실패
        scope_none = {
            "type": "http",
            "path": "/api/users",
            "headers": [],
            "query_string": b"",
        }
        ctx_none = AuthContext.from_request(Request(scope_none, receive))
        auth = await group.authenticate(ctx_none)
        assert auth is None


# =============================================================================
# Test: Authentication Parameter Injection
# =============================================================================


class TestAuthenticationParameterInjection:
    """컨트롤러에서 Authentication 파라미터 주입 테스트"""

    @pytest.mark.asyncio
    async def test_authentication_required_parameter(self):
        """인증 정보 필수 파라미터 주입"""
        from bloom.web.auth import Authentication, get_authentication_param_marker
        from typing import get_type_hints, get_origin, get_args
        import inspect

        @dataclass
        class UserAuth(Authentication[int]):
            id: int
            username: str

        # 컨트롤러 메서드 시그니처
        async def my_endpoint(authentication: UserAuth) -> dict:
            return {"user_id": authentication.id}

        # 파라미터 분석
        sig = inspect.signature(my_endpoint)
        hints = get_type_hints(my_endpoint)

        param = sig.parameters["authentication"]
        hint = hints["authentication"]

        # Authentication 서브클래스인지 확인
        from bloom.web.auth import is_authentication_type

        assert is_authentication_type(hint) is True

    @pytest.mark.asyncio
    async def test_optional_authentication_parameter(self):
        """선택적 인증 정보 파라미터 (인증 안 된 경우 None)"""
        from bloom.web.auth import Authentication, is_authentication_type
        from typing import get_type_hints, get_origin, get_args, Union
        import inspect

        @dataclass
        class UserAuth(Authentication[int]):
            id: int

        async def my_endpoint(authentication: Optional[UserAuth]) -> dict:
            if authentication:
                return {"user_id": authentication.id}
            return {"user_id": None}

        hints = get_type_hints(my_endpoint)
        hint = hints["authentication"]

        # Optional[UserAuth]는 Union[UserAuth, None]
        origin = get_origin(hint)
        assert origin is Union

        args = get_args(hint)
        # UserAuth가 Authentication 서브클래스인지 확인
        auth_type = next((a for a in args if a is not type(None)), None)
        assert auth_type is not None
        assert is_authentication_type(auth_type) is True


# =============================================================================
# Test: Full Integration (HTTP Endpoint with Authentication)
# =============================================================================


class TestFullHttpIntegration:
    """HTTP 엔드포인트와 Authentication 통합 테스트"""

    @pytest.mark.asyncio
    async def test_controller_with_authentication_injection(self):
        """컨트롤러에서 Authentication 주입"""
        from bloom.web.auth import (
            Authentication,
            Authenticator,
            AuthContext,
            AuthMiddleware,
        )
        from bloom.web import Controller, PostMapping
        from bloom.web.request import Request

        @dataclass
        class UserAuth(Authentication[int]):
            id: int
            username: str

        @dataclass
        class CreatePostRequest:
            title: str
            content: str

        @Service
        class MockAuthenticator(Authenticator[UserAuth]):
            async def supports(self, context: AuthContext) -> bool:
                return "authorization" in context.headers

            async def authenticate(self, context: AuthContext) -> Optional[UserAuth]:
                auth_header = context.headers.get("authorization", "")
                if auth_header == "Bearer valid-token":
                    return UserAuth(id=123, username="testuser")
                return None

        @Controller
        class PostController:
            @PostMapping("/posts")
            async def create_post(
                self,
                authentication: UserAuth,
            ) -> dict:
                return {
                    "author_id": authentication.id,
                    "author": authentication.username,
                }

        manager = get_container_manager()
        await manager.initialize()

        # 컨트롤러 인스턴스 생성 확인
        controller = await manager.get_instance_async(PostController)
        assert controller is not None


# =============================================================================
# Test: Messaging Integration (WebSocket with Authentication)
# =============================================================================


class TestMessagingIntegration:
    """Messaging과 Authentication 통합 테스트"""

    @pytest.mark.asyncio
    async def test_message_controller_with_authentication(self):
        """MessageController에서 Authentication 주입"""
        from bloom.web.auth import Authentication
        from bloom.web.messaging.decorators import MessageController, MessageMapping
        from bloom.web.messaging.params import MessagePayload

        @dataclass
        class UserAuth(Authentication[int]):
            id: int
            username: str

        @dataclass
        class ChatMessage:
            text: str

        @MessageController()
        class ChatController:
            @MessageMapping("/chat/{room}")
            async def send_message(
                self,
                room: str,
                message: MessagePayload[ChatMessage],
                authentication: Optional[UserAuth] = None,
            ) -> dict:
                sender = authentication.username if authentication else "anonymous"
                return {
                    "room": room,
                    "text": message.text,
                    "sender": sender,
                }

        # 컨트롤러 등록 확인
        manager = get_container_manager()
        await manager.initialize()

        controller = await manager.get_instance_async(ChatController)
        assert controller is not None
