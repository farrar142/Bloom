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


class TestMessageControllerIntegration:
    """MessageController 통합 테스트"""

    def test_collect_handlers(self, reset_container_manager):
        """핸들러 수집 테스트"""
        import tests.test_websocket as test_module

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
        import tests.test_websocket as test_module

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
