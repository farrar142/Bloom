"""WebSocket 테스트 - WebSocketSessionManager 및 StompProtocolHandler"""

import pytest
from bloom import Application
from bloom.web.messaging import (
    SimpleBroker,
    WebSocketSessionManager,
    StompProtocolHandler,
    MessageController,
    MessageMapping,
    SendTo,
    SendToUser,
    Message,
    StompFrame,
    StompCommand,
    WebSocketSession,
    StompAuthenticator,
    StompAuthentication,
    STOMP_ANONYMOUS,
)


# ============================================================================
# WebSocketSessionManager 테스트
# ============================================================================


class TestWebSocketSessionManager:
    """WebSocketSessionManager 테스트"""

    def test_default_app_destination_prefixes(self):
        """기본 app_destination_prefixes 확인"""
        manager = WebSocketSessionManager()

        assert manager.app_destination_prefixes == ["/app"]
        assert manager.user_destination_prefix == "/user"

    def test_set_app_destination_prefixes(self):
        """app_destination_prefixes 설정"""
        manager = WebSocketSessionManager()

        manager.set_app_destination_prefixes(["/app", "/api"])

        assert manager.app_destination_prefixes == ["/app", "/api"]

    def test_set_user_destination_prefix(self):
        """user_destination_prefix 설정"""
        manager = WebSocketSessionManager()

        manager.set_user_destination_prefix("/private")

        assert manager.user_destination_prefix == "/private"

    def test_set_multiple_prefixes(self):
        """여러 프리픽스 설정"""
        manager = WebSocketSessionManager()

        manager.set_app_destination_prefixes(["/app", "/api", "/v1"])
        manager.set_user_destination_prefix("/me")

        assert "/app" in manager.app_destination_prefixes
        assert "/api" in manager.app_destination_prefixes
        assert "/v1" in manager.app_destination_prefixes
        assert manager.user_destination_prefix == "/me"


# ============================================================================
# StompProtocolHandler 설정 연동 테스트
# ============================================================================


class TestStompProtocolHandlerConfig:
    """StompProtocolHandler가 WebSocketSessionManager 설정을 참조하는지 테스트"""

    def test_handler_uses_session_manager_prefixes(self):
        """Handler가 SessionManager의 prefix를 사용하는지 확인"""
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        # 기본값 확인
        assert handler._app_destination_prefixes == ["/app"]
        assert handler._user_destination_prefix == "/user"

    def test_handler_reflects_session_manager_changes(self):
        """SessionManager 변경이 Handler에 반영되는지 확인"""
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        # SessionManager 설정 변경
        session_manager.set_app_destination_prefixes(["/app", "/api"])
        session_manager.set_user_destination_prefix("/private")

        # Handler에서 변경 반영 확인
        assert handler._app_destination_prefixes == ["/app", "/api"]
        assert handler._user_destination_prefix == "/private"

    def test_is_app_destination(self):
        """is_app_destination 메서드 테스트"""
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        # 기본 /app 프리픽스
        assert handler.is_app_destination("/app/chat") is True
        assert handler.is_app_destination("/app/user/send") is True
        assert handler.is_app_destination("/topic/messages") is False

    def test_is_app_destination_with_custom_prefixes(self):
        """커스텀 프리픽스로 is_app_destination 테스트"""
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        session_manager.set_app_destination_prefixes(["/app", "/api"])
        handler = StompProtocolHandler(broker, session_manager)

        assert handler.is_app_destination("/app/chat") is True
        assert handler.is_app_destination("/api/users") is True
        assert handler.is_app_destination("/topic/messages") is False

    def test_strip_app_prefix(self):
        """strip_app_prefix 메서드 테스트"""
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        session_manager.set_app_destination_prefixes(["/app", "/api"])
        handler = StompProtocolHandler(broker, session_manager)

        assert handler.strip_app_prefix("/app/chat") == "/chat"
        assert handler.strip_app_prefix("/api/users") == "/users"
        assert handler.strip_app_prefix("/topic/messages") == "/topic/messages"


# ============================================================================
# MessageController 통합 테스트
# ============================================================================


@MessageController
class TestChatController:
    """테스트용 채팅 컨트롤러"""

    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    def send_chat(self, message: dict) -> dict:
        return {"text": message.get("text", ""), "processed": True}


@MessageController("/game")
class TestGameController:
    """테스트용 게임 컨트롤러 (프리픽스 있음)"""

    @MessageMapping("/move")
    @SendTo("/topic/game")
    def handle_move(self, message: dict) -> dict:
        return {"action": "move", "data": message}


@MessageController("/auth")
class TestAuthController:
    """테스트용 인증 컨트롤러"""

    @MessageMapping("/login")
    @SendToUser("/queue/reply")
    def login(self, message: dict, authentication: StompAuthentication) -> dict:
        return {"status": "success", "user": authentication.user_id}


class TestMessageControllerIntegration:
    """MessageController 통합 테스트"""

    def test_collect_handlers(self, reset_container_manager):
        """핸들러 수집 테스트"""
        import tests.messaging.test_websocket as test_module

        app = Application("test_collect")
        app.scan(test_module).ready()

        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager, app.manager)
        handler.collect_handlers(app.manager)

        # 핸들러가 수집되었는지 확인
        destinations = [h.destination_pattern for h in handler._message_handlers]
        assert "/chat" in destinations
        assert "/game/move" in destinations  # 프리픽스 적용

    def test_handler_send_to(self, reset_container_manager):
        """@SendTo 데코레이터 확인"""
        import tests.messaging.test_websocket as test_module

        app = Application("test_send_to")
        app.scan(test_module).ready()

        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager, app.manager)
        handler.collect_handlers(app.manager)

        # chat 핸들러의 send_to 확인
        chat_handler = next(
            (h for h in handler._message_handlers if h.destination_pattern == "/chat"),
            None,
        )
        assert chat_handler is not None
        assert chat_handler.send_to == "/topic/chat"


# ============================================================================
# SimpleBroker 구독/발행 테스트
# ============================================================================


class TestSimpleBrokerWithSessionManager:
    """SimpleBroker와 SessionManager 연동 테스트"""

    @pytest.mark.asyncio
    async def test_publish_to_topic(self):
        """토픽 발행 테스트"""
        broker = SimpleBroker()
        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        await broker.subscribe(
            subscription_id="sub-1",
            destination="/topic/test",
            session_id="sess-1",
            send_callback=callback,
        )

        message = Message(destination="/topic/test", payload={"hello": "world"})
        count = await broker.publish(message)

        assert count == 1
        assert len(received) == 1
        assert received[0].payload == {"hello": "world"}

    @pytest.mark.asyncio
    async def test_send_to_user(self):
        """사용자 전송 테스트"""
        broker = SimpleBroker()
        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        # /user/queue/notifications 대신 /queue/notifications로 구독
        # send_to_user는 user의 세션을 찾아서 해당 destination에 매칭되는 구독에 전송
        await broker.subscribe(
            subscription_id="sub-1",
            destination="/queue/notifications",
            session_id="sess-1",
            send_callback=callback,
            user="alice",
        )

        message = Message(destination="/queue/notifications", payload={"alert": "hi"})
        count = await broker.send_to_user("alice", "/queue/notifications", message)

        assert count == 1
        assert received[0].payload == {"alert": "hi"}

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """구독 해제 테스트"""
        broker = SimpleBroker()
        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        await broker.subscribe("sub-1", "/topic/test", "sess-1", callback)

        # 첫 번째 메시지
        await broker.publish(Message(destination="/topic/test", payload={"n": 1}))
        assert len(received) == 1

        # 구독 해제
        await broker.unsubscribe("sub-1", "sess-1")

        # 두 번째 메시지 (수신 안됨)
        await broker.publish(Message(destination="/topic/test", payload={"n": 2}))
        assert len(received) == 1  # 변화 없음

    @pytest.mark.asyncio
    async def test_disconnect_cleanup(self):
        """연결 해제 시 구독 정리"""
        broker = SimpleBroker()

        async def callback(msg: Message):
            pass

        await broker.subscribe("sub-1", "/topic/a", "sess-1", callback)
        await broker.subscribe("sub-2", "/topic/b", "sess-1", callback)

        # 구독 확인
        assert len(broker._subscriptions.get("/topic/a", [])) == 1
        assert len(broker._subscriptions.get("/topic/b", [])) == 1

        # 연결 해제
        await broker.disconnect("sess-1")

        # 모든 구독 정리 확인
        assert len(broker._subscriptions.get("/topic/a", [])) == 0
        assert len(broker._subscriptions.get("/topic/b", [])) == 0


# ============================================================================
# 목적지 패턴 매칭 테스트
# ============================================================================


class TestDestinationPatternMatching:
    """목적지 패턴 매칭 테스트"""

    def test_simple_match(self):
        """단순 매칭"""
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        result = handler._match_destination("/chat", "/chat")
        assert result == {}

    def test_path_param_match(self):
        """경로 파라미터 매칭"""
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        result = handler._match_destination("/chat.{room_id}", "/chat.room123")
        assert result == {"room_id": "room123"}

    def test_multiple_path_params(self):
        """다중 경로 파라미터 매칭"""
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        result = handler._match_destination(
            "/game.{game_id}.{action}", "/game.abc.move"
        )
        assert result == {"game_id": "abc", "action": "move"}

    def test_no_match(self):
        """매칭 실패"""
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        result = handler._match_destination("/chat", "/other")
        assert result is None


# ============================================================================
# STOMP 인증 테스트
# ============================================================================


class TokenStompAuthenticator(StompAuthenticator):
    """테스트용 토큰 기반 인증기"""

    def __init__(self, valid_tokens: dict[str, str] | None = None):
        """
        Args:
            valid_tokens: {token: user_id} 매핑
        """
        self.valid_tokens = valid_tokens or {"valid-token": "user123"}

    def supports(self, session: WebSocketSession, frame: StompFrame) -> bool:
        """Authorization 헤더가 있으면 지원"""
        return "Authorization" in frame.headers

    def authenticate(
        self, session: WebSocketSession, frame: StompFrame
    ) -> StompAuthentication | None:
        """토큰 검증"""
        auth_header = frame.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "")

        if token in self.valid_tokens:
            return StompAuthentication(
                user_id=self.valid_tokens[token],
                authenticated=True,
                authorities=["ROLE_USER"],
            )
        # 토큰이 있지만 유효하지 않음 -> 인증 실패
        return StompAuthentication(authenticated=False)


class LoginStompAuthenticator(StompAuthenticator):
    """테스트용 login/passcode 기반 인증기"""

    def __init__(self, users: dict[str, str] | None = None):
        """
        Args:
            users: {login: passcode} 매핑
        """
        self.users = users or {"admin": "admin123", "user": "user123"}

    def supports(self, session: WebSocketSession, frame: StompFrame) -> bool:
        """login 헤더가 있으면 지원"""
        return "login" in frame.headers

    def authenticate(
        self, session: WebSocketSession, frame: StompFrame
    ) -> StompAuthentication | None:
        """login/passcode 검증"""
        login = frame.headers.get("login", "")
        passcode = frame.headers.get("passcode", "")

        if login in self.users and self.users[login] == passcode:
            return StompAuthentication(
                user_id=login,
                authenticated=True,
                authorities=["ROLE_ADMIN"] if login == "admin" else ["ROLE_USER"],
            )
        # 로그인 시도했지만 실패
        return StompAuthentication(authenticated=False)


class TestStompAuthenticator:
    """StompAuthenticator 기본 테스트"""

    def test_stomp_authentication_default(self):
        """StompAuthentication 기본값"""
        auth = StompAuthentication()

        assert auth.user_id is None
        assert auth.authenticated is False
        assert auth.authorities == []
        assert auth.is_authenticated() is False

    def test_stomp_authentication_authenticated(self):
        """인증된 StompAuthentication"""
        auth = StompAuthentication(
            user_id="user123",
            authenticated=True,
            authorities=["ROLE_USER", "ROLE_ADMIN"],
        )

        assert auth.user_id == "user123"
        assert auth.is_authenticated() is True
        assert auth.has_authority("ROLE_USER") is True
        assert auth.has_authority("ROLE_ADMIN") is True
        assert auth.has_authority("ROLE_SUPER") is False

    def test_stomp_anonymous(self):
        """STOMP_ANONYMOUS 상수"""
        assert STOMP_ANONYMOUS.authenticated is False
        assert STOMP_ANONYMOUS.user_id is None


class TestWebSocketSessionManagerAuthentication:
    """WebSocketSessionManager 인증 테스트"""

    def test_add_authenticator(self):
        """인증기 추가"""
        manager = WebSocketSessionManager()
        authenticator = TokenStompAuthenticator()

        manager.add_authenticator(authenticator)

        assert len(manager.authenticators) == 1
        assert manager.authenticators[0] is authenticator

    def test_set_authenticators(self):
        """인증기 목록 설정"""
        manager = WebSocketSessionManager()
        auth1 = TokenStompAuthenticator()
        auth2 = LoginStompAuthenticator()

        manager.set_authenticators([auth1, auth2])

        assert len(manager.authenticators) == 2

    def test_authenticate_with_token(self):
        """토큰 인증 성공"""
        manager = WebSocketSessionManager()
        manager.add_authenticator(TokenStompAuthenticator())

        session = WebSocketSession(path="/ws")
        frame = StompFrame(
            command=StompCommand.CONNECT,
            headers={"Authorization": "Bearer valid-token"},
        )

        result = manager.authenticate(session, frame)

        assert result is not None
        assert result.is_authenticated() is True
        assert result.user_id == "user123"

    def test_authenticate_with_invalid_token(self):
        """토큰 인증 실패"""
        manager = WebSocketSessionManager()
        manager.add_authenticator(TokenStompAuthenticator())

        session = WebSocketSession(path="/ws")
        frame = StompFrame(
            command=StompCommand.CONNECT,
            headers={"Authorization": "Bearer invalid-token"},
        )

        result = manager.authenticate(session, frame)

        assert result is not None
        assert result.is_authenticated() is False

    def test_authenticate_with_login(self):
        """login/passcode 인증 성공"""
        manager = WebSocketSessionManager()
        manager.add_authenticator(LoginStompAuthenticator())

        session = WebSocketSession(path="/ws")
        frame = StompFrame(
            command=StompCommand.CONNECT,
            headers={"login": "admin", "passcode": "admin123"},
        )

        result = manager.authenticate(session, frame)

        assert result is not None
        assert result.is_authenticated() is True
        assert result.user_id == "admin"
        assert "ROLE_ADMIN" in result.authorities

    def test_authenticate_with_wrong_password(self):
        """login/passcode 인증 실패 (잘못된 비밀번호)"""
        manager = WebSocketSessionManager()
        manager.add_authenticator(LoginStompAuthenticator())

        session = WebSocketSession(path="/ws")
        frame = StompFrame(
            command=StompCommand.CONNECT,
            headers={"login": "admin", "passcode": "wrong"},
        )

        result = manager.authenticate(session, frame)

        assert result is not None
        assert result.is_authenticated() is False

    def test_authenticate_no_authenticator(self):
        """인증기 없음 - None 반환"""
        manager = WebSocketSessionManager()

        session = WebSocketSession(path="/ws")
        frame = StompFrame(
            command=StompCommand.CONNECT,
            headers={"Authorization": "Bearer token"},
        )

        result = manager.authenticate(session, frame)

        assert result is None

    def test_authenticate_chain_first_match(self):
        """인증기 체인 - 첫 번째 매칭 인증기 사용"""
        manager = WebSocketSessionManager()
        # 토큰 인증기를 먼저 등록
        manager.add_authenticator(TokenStompAuthenticator())
        manager.add_authenticator(LoginStompAuthenticator())

        session = WebSocketSession(path="/ws")
        # Authorization 헤더 있음 -> TokenStompAuthenticator 사용
        frame = StompFrame(
            command=StompCommand.CONNECT,
            headers={"Authorization": "Bearer valid-token"},
        )

        result = manager.authenticate(session, frame)

        assert result is not None
        assert result.user_id == "user123"  # TokenStompAuthenticator의 결과

    def test_authenticate_chain_fallback(self):
        """인증기 체인 - 첫 번째가 지원하지 않으면 다음으로"""
        manager = WebSocketSessionManager()
        manager.add_authenticator(TokenStompAuthenticator())
        manager.add_authenticator(LoginStompAuthenticator())

        session = WebSocketSession(path="/ws")
        # login 헤더만 있음 -> LoginStompAuthenticator 사용
        frame = StompFrame(
            command=StompCommand.CONNECT,
            headers={"login": "user", "passcode": "user123"},
        )

        result = manager.authenticate(session, frame)

        assert result is not None
        assert result.user_id == "user"  # LoginStompAuthenticator의 결과

    def test_authenticate_no_matching_authenticator(self):
        """인증기 체인 - 지원하는 인증기 없음"""
        manager = WebSocketSessionManager()
        manager.add_authenticator(TokenStompAuthenticator())

        session = WebSocketSession(path="/ws")
        # 아무 인증 헤더도 없음
        frame = StompFrame(
            command=StompCommand.CONNECT,
            headers={},
        )

        result = manager.authenticate(session, frame)

        assert result is None  # 아무 인증기도 지원하지 않음
