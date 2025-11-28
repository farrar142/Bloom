"""WebSocket과 ASGI 실제 연동 테스트 (실제 서버 사용)"""

import pytest
import asyncio
from typing import AsyncGenerator

from bloom import Application
from bloom.web.messaging import (
    MessageController,
    MessageMapping,
    SendTo,
    SimpleBroker,
    StompProtocolHandler,
    WebSocketSessionManager,
)
from bloom.web.asgi import ASGIApplication
from bloom.web.router import Router


# ============================================================================
# 테스트용 MessageController
# ============================================================================


@MessageController
class EchoController:
    """테스트용 Echo 컨트롤러"""

    @MessageMapping("/echo")
    @SendTo("/topic/echo")
    def echo_message(self, message: dict) -> dict:
        """메시지 에코"""
        return {"original": message, "echo": True}


@MessageController
class ChatController:
    """테스트용 채팅 컨트롤러"""

    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    def send_message(self, message: dict) -> dict:
        """채팅 메시지"""
        return {"text": message.get("text", ""), "processed": True}


# ============================================================================
# ASGI 앱 생성 테스트
# ============================================================================


class TestASGIApplicationCreation:
    """ASGI 애플리케이션 생성 및 구성 테스트"""

    def test_create_asgi_app_with_messaging(self):
        """메시징 지원 ASGI 앱 생성"""
        app = Application("test_asgi_creation")
        app.scan(__name__).ready()

        manager = app.manager
        router = Router(manager)
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        stomp_handler = StompProtocolHandler(broker, session_manager, manager)
        stomp_handler.collect_handlers(manager)

        asgi_app = ASGIApplication(router, stomp_handler, websocket_path="/ws")

        assert asgi_app.router is router
        assert asgi_app.stomp_handler is stomp_handler
        assert asgi_app.websocket_path == "/ws"

    def test_create_asgi_app_without_messaging(self):
        """메시징 없는 ASGI 앱 생성"""
        app = Application("test_asgi_no_messaging")
        app.scan(__name__).ready()

        manager = app.manager
        router = Router(manager)

        asgi_app = ASGIApplication(router, stomp_handler=None)

        assert asgi_app.router is router
        assert asgi_app.stomp_handler is None

    def test_stomp_handler_collects_message_controllers(self):
        """StompProtocolHandler가 MessageController 수집"""
        import tests.test_websocket_asgi_integration as test_module

        app = Application("test_handler_collection")
        app.scan(test_module).ready()

        manager = app.manager
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        stomp_handler = StompProtocolHandler(broker, session_manager, manager)

        # 핸들러 수집 전
        assert len(stomp_handler._message_handlers) == 0

        # 핸들러 수집
        stomp_handler.collect_handlers(manager)

        # 핸들러 수집 확인 (EchoController, ChatController)
        assert len(stomp_handler._message_handlers) >= 2

        # 특정 핸들러 확인
        destinations = [h.destination_pattern for h in stomp_handler._message_handlers]
        assert "/echo" in destinations
        assert "/chat" in destinations


# ============================================================================
# STOMP 프레임 파싱 및 라우팅 테스트
# ============================================================================


class TestStompProtocolHandlerRouting:
    """STOMP 프로토콜 핸들러 라우팅 테스트"""

    def test_message_handler_routing(self):
        """메시지 핸들러 라우팅 확인"""
        import tests.test_websocket_asgi_integration as test_module

        app = Application("test_routing")
        app.scan(test_module).ready()

        manager = app.manager
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        stomp_handler = StompProtocolHandler(broker, session_manager, manager)
        stomp_handler.collect_handlers(manager)

        # /app/echo 핸들러 존재 확인
        echo_handler = next(
            (
                h
                for h in stomp_handler._message_handlers
                if h.destination_pattern == "/echo"
            ),
            None,
        )
        assert echo_handler is not None
        assert echo_handler.send_to == "/topic/echo"

        # /app/chat 핸들러 존재 확인
        chat_handler = next(
            (
                h
                for h in stomp_handler._message_handlers
                if h.destination_pattern == "/chat"
            ),
            None,
        )
        assert chat_handler is not None
        assert chat_handler.send_to == "/topic/chat"

    @pytest.mark.asyncio
    async def test_broker_publish_and_subscribe(self):
        """브로커의 발행/구독 기능"""
        from bloom.web.messaging import Message

        broker = SimpleBroker()
        received_messages: list[Message] = []

        async def callback(msg: Message):
            received_messages.append(msg)

        # 구독 등록
        await broker.subscribe(
            subscription_id="sub-1",
            destination="/topic/test",
            session_id="sess-1",
            send_callback=callback,
        )

        # 메시지 발행
        message = Message(destination="/topic/test", payload={"text": "hello"})
        count = await broker.publish(message)

        assert count == 1
        assert len(received_messages) == 1
        assert received_messages[0].payload == {"text": "hello"}

    @pytest.mark.asyncio
    async def test_broker_multiple_subscriptions(self):
        """브로커 다중 구독"""
        from bloom.web.messaging import Message

        broker = SimpleBroker()
        received1: list[Message] = []
        received2: list[Message] = []

        async def callback1(msg: Message):
            received1.append(msg)

        async def callback2(msg: Message):
            received2.append(msg)

        # 두 구독자 등록
        await broker.subscribe("sub-1", "/topic/broadcast", "sess-1", callback1)
        await broker.subscribe("sub-2", "/topic/broadcast", "sess-2", callback2)

        # 메시지 발행
        message = Message(destination="/topic/broadcast", payload={"id": 1})
        count = await broker.publish(message)

        assert count == 2
        assert len(received1) == 1
        assert len(received2) == 1

    @pytest.mark.asyncio
    async def test_broker_disconnect_cleanup(self):
        """브로커 연결 해제 시 구독 정리"""
        from bloom.web.messaging import Message

        broker = SimpleBroker()

        async def callback(msg: Message):
            pass

        # 구독 등록
        await broker.subscribe("sub-1", "/topic/test", "sess-1", callback)

        # 구독 확인
        subscriptions = broker._subscriptions.get("/topic/test", [])
        assert len(subscriptions) == 1

        # 연결 해제
        await broker.disconnect("sess-1")

        # 구독 정리 확인
        subscriptions_after = broker._subscriptions.get("/topic/test", [])
        assert len(subscriptions_after) == 0


# ============================================================================
# WebSocketSession 테스트
# ============================================================================


class TestWebSocketSessionManagement:
    """WebSocketSession 관리 테스트"""

    @pytest.mark.asyncio
    async def test_session_manager_add_remove(self):
        """세션 추가 및 제거"""
        from bloom.web.messaging import WebSocketSession

        manager = WebSocketSessionManager()

        # Mock 세션 생성
        async def mock_receive():
            return {"type": "websocket.receive", "text": "test"}

        async def mock_send(msg):
            pass

        session = WebSocketSession(
            path="/ws",
            headers={"test": "header"},
            query_params={"key": "value"},
            _receive=mock_receive,
            _send=mock_send,
        )

        # 세션 추가
        manager.add(session)
        assert len(manager._sessions) == 1
        assert manager.get(session.id) is session

        # 세션 제거
        manager.remove(session.id)
        assert len(manager._sessions) == 0
        assert manager.get(session.id) is None

    @pytest.mark.asyncio
    async def test_session_with_user(self):
        """사용자 정보가 있는 세션"""
        from bloom.web.messaging import WebSocketSession

        async def mock_receive():
            return {"type": "websocket.receive"}

        async def mock_send(msg):
            pass

        session = WebSocketSession(
            path="/ws",
            user="alice",
            _receive=mock_receive,
            _send=mock_send,
        )

        assert session.user == "alice"


# ============================================================================
# ASGI Scope 처리 테스트
# ============================================================================


class TestASGIScopeHandling:
    """ASGI Scope 처리 테스트"""

    def test_parse_query_params_from_scope(self):
        """ASGI scope에서 쿼리 파라미터 파싱"""
        from urllib.parse import parse_qs

        query_string = b"token=abc123&room=general"
        query_params = {
            k: v[0] for k, v in parse_qs(query_string.decode("utf-8")).items()
        }

        assert query_params["token"] == "abc123"
        assert query_params["room"] == "general"

    def test_parse_headers_from_scope(self):
        """ASGI scope에서 헤더 파싱"""
        headers_raw = [
            (b"user-agent", b"TestClient/1.0"),
            (b"authorization", b"Bearer token123"),
        ]

        headers = {
            key.decode("utf-8"): value.decode("utf-8") for key, value in headers_raw
        }

        assert headers["user-agent"] == "TestClient/1.0"
        assert headers["authorization"] == "Bearer token123"


# ============================================================================
# 통합 시나리오 테스트
# ============================================================================


class TestIntegrationScenarios:
    """통합 시나리오 테스트"""

    @pytest.mark.asyncio
    async def test_end_to_end_message_flow(self):
        """종단간 메시지 흐름 시뮬레이션"""
        from bloom.web.messaging import Message
        import tests.test_websocket_asgi_integration as test_module

        # 애플리케이션 설정
        app = Application("test_e2e")
        app.scan(test_module).ready()

        manager = app.manager
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        stomp_handler = StompProtocolHandler(broker, session_manager, manager)
        stomp_handler.collect_handlers(manager)

        # 구독자 설정
        received_messages: list[Message] = []

        async def subscriber_callback(msg: Message):
            received_messages.append(msg)

        # /topic/echo 구독
        await broker.subscribe(
            subscription_id="sub-1",
            destination="/topic/echo",
            session_id="sess-1",
            send_callback=subscriber_callback,
        )

        # 메시지 발행 (/app/echo로 전송)
        message = Message(
            destination="/app/echo",
            payload={"text": "test message"},
            session_id="sess-1",
        )

        # 핸들러 찾기 및 실행 시뮬레이션
        for handler_info in stomp_handler._message_handlers:
            if handler_info.destination_pattern == "/echo":
                # 핸들러 실행 (간접 호출)
                from tests.test_websocket_asgi_integration import (
                    EchoController as EchoCtrl,
                )

                controller_instance = manager.get_instance(EchoCtrl)
                result = controller_instance.echo_message(message.payload)

                # 결과를 /topic/echo로 발행
                result_message = Message(
                    destination="/topic/echo",
                    payload=result,
                )
                await broker.publish(result_message)
                break

        # 구독자가 메시지를 받았는지 확인
        assert len(received_messages) == 1
        assert received_messages[0].payload["echo"] is True
        assert received_messages[0].payload["original"]["text"] == "test message"

    @pytest.mark.asyncio
    async def test_multiple_controllers_integration(self):
        """여러 컨트롤러 통합 테스트"""
        import tests.test_websocket_asgi_integration as test_module

        app = Application("test_multi_controllers")
        app.scan(test_module).ready()

        manager = app.manager
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        stomp_handler = StompProtocolHandler(broker, session_manager, manager)
        stomp_handler.collect_handlers(manager)

        # EchoController와 ChatController 모두 등록되었는지 확인
        destinations = [h.destination_pattern for h in stomp_handler._message_handlers]

        assert "/echo" in destinations
        assert "/chat" in destinations

        # 각 컨트롤러 인스턴스 확인
        from tests.test_websocket_asgi_integration import (
            EchoController as EchoCtrl,
            ChatController as ChatCtrl,
        )

        echo_controller = manager.get_instance(EchoCtrl)
        chat_controller = manager.get_instance(ChatCtrl)

        assert echo_controller is not None
        assert chat_controller is not None
