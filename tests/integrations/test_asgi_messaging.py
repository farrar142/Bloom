"""ASGI와 Messaging 통합 테스트

실제 ASGI 앱과 WebSocket/STOMP 메시징 시스템의 통합 테스트.
DI 컨테이너, 메시지 브로커, 핸들러 디스패처가 함께 동작하는지 검증합니다.
"""

import pytest
import asyncio
import json
from dataclasses import dataclass

from bloom import Application
from bloom.core import (
    Component,
    Service,
    reset_container_manager,
    get_container_manager,
)
from bloom.web.messaging.broker import SimpleBroker, Message
from bloom.web.messaging.websocket import WebSocketSession, WebSocketState
from bloom.web.messaging.handler import (
    MessageDispatcher,
    MessageContext,
    StompMessageHandler,
)
from bloom.web.messaging.stomp import StompFrame, StompCommand, StompProtocol
from bloom.web.messaging.decorators import (
    MessageController,
    MessageMapping,
    SubscribeMapping,
    SendTo,
)
from bloom.web.messaging.params import (
    DestinationVariable,
    MessagePayload,
    Principal,
)


# =============================================================================
# Mock Classes
# =============================================================================


class MockReceive:
    """테스트용 receive 함수"""

    def __init__(self, messages: list | None = None):
        self.messages = messages or []
        self.index = 0

    async def __call__(self):
        if self.index < len(self.messages):
            msg = self.messages[self.index]
            self.index += 1
            return msg
        return {"type": "websocket.disconnect", "code": 1000}

    def add_message(self, text: str):
        """메시지 추가"""
        self.messages.append({"type": "websocket.receive", "text": text})


class MockSend:
    """테스트용 send 함수"""

    def __init__(self):
        self.sent: list = []

    async def __call__(self, message) -> None:
        self.sent.append(message)

    def get_text_messages(self) -> list[str]:
        """전송된 텍스트 메시지 목록"""
        return [
            m.get("text", "") for m in self.sent if m.get("type") == "websocket.send"
        ]

    def clear(self):
        """전송된 메시지 초기화"""
        self.sent = []


def create_mock_session(
    session_id: str = "session-1",
    user_id: str = "user-123",
    messages: list | None = None,
) -> WebSocketSession:
    """테스트용 WebSocketSession 생성"""
    scope = {
        "type": "websocket",
        "path": "/ws",
        "query_string": b"",
        "headers": [],
    }
    return WebSocketSession(
        scope=scope,
        receive=MockReceive(messages),
        send=MockSend(),
        session_id=session_id,
        user_id=user_id,
        state=WebSocketState.CONNECTED,
        _accepted=True,
    )


# =============================================================================
# Integration Tests
# =============================================================================


class TestMessagingDIIntegration:
    """메시징과 DI 컨테이너 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_message_controller_with_di(self):
        """DI 컨테이너와 MessageController 통합"""

        # 테스트 내에서 컴포넌트 정의 (데코레이터가 자동 등록)
        @Service
        class TestNotificationService:
            def __init__(self):
                self.notifications: list[str] = []

            def add_notification(self, message: str):
                self.notifications.append(message)

        @MessageController()
        class TestNotificationController:
            notification_service: TestNotificationService

            @MessageMapping("/notify/{user_id}")
            async def handle_notify(
                self,
                user_id: str,
                message: MessagePayload[dict],
            ) -> dict:
                self.notification_service.add_notification(f"{user_id}: {message}")
                return {"status": "ok", "user_id": user_id}

        manager = get_container_manager()
        await manager.initialize()

        # 디스패처 설정
        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(TestNotificationController)

        # 메시지 컨텍스트 생성
        session = create_mock_session()
        await broker.register_session(session)

        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/notify/user-123"},
            body='{"title": "Hello", "body": "World"}',
        )

        context = MessageContext(
            session=session,
            frame=frame,
            destination="/notify/user-123",
            principal=session.user_id,
        )

        # 메시지 디스패치
        result = await dispatcher.dispatch_message(context)

        # 결과 확인
        assert result["status"] == "ok"
        assert result["user_id"] == "user-123"

        # NotificationService가 호출되었는지 확인
        notification_service = await manager.get_instance_async(
            TestNotificationService, required=True
        )
        assert len(notification_service.notifications) == 1

    @pytest.mark.asyncio
    async def test_message_payload_deserialization(self):
        """MessagePayload 역직렬화 테스트"""

        @dataclass
        class TestChatMessage:
            text: str
            sender: str = ""

        @dataclass
        class TestChatResponse:
            text: str
            room: str
            from_user: str

        @MessageController()
        class TestChatController:
            def __init__(self):
                self.received_messages: list = []

            @MessageMapping("/chat/{room}")
            @SendTo("/topic/chat/{room}")
            async def handle_chat(
                self,
                room: str,
                message: MessagePayload[TestChatMessage],
                principal: Principal[str | None] = None,
            ) -> TestChatResponse:
                self.received_messages.append(message)
                return TestChatResponse(
                    text=message.text,
                    room=room,
                    from_user=principal or "anonymous",
                )

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(TestChatController)

        session = create_mock_session()
        await broker.register_session(session)

        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/chat/room1"},
            body='{"text": "Hello World", "sender": "alice"}',
        )

        context = MessageContext(
            session=session,
            frame=frame,
            destination="/chat/room1",
            principal="alice",
        )

        result = await dispatcher.dispatch_message(context)

        assert isinstance(result, TestChatResponse)
        assert result.text == "Hello World"
        assert result.room == "room1"
        assert result.from_user == "alice"


class TestBrokerDispatcherIntegration:
    """브로커와 디스패처 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_subscribe_mapping_initial_data(self):
        """SubscribeMapping으로 초기 데이터 전송"""

        @MessageController()
        class TestSubscribeController:
            @SubscribeMapping("/topic/chat/{room}")
            async def on_subscribe_chat(self, room: str) -> dict:
                return {"type": "joined", "room": room}

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(TestSubscribeController)

        session = create_mock_session()
        await broker.register_session(session)

        # SUBSCRIBE 프레임
        frame = StompFrame(
            command=StompCommand.SUBSCRIBE,
            headers={
                "destination": "/topic/chat/general",
                "id": "sub-1",
            },
            body="",
        )

        context = MessageContext(
            session=session,
            frame=frame,
            destination="/topic/chat/general",
        )

        # SubscribeMapping 호출
        result = await dispatcher.dispatch_subscribe(context)

        assert result is not None
        assert result["type"] == "joined"
        assert result["room"] == "general"

    @pytest.mark.asyncio
    async def test_send_to_broadcast(self):
        """@SendTo로 브로드캐스트"""

        @dataclass
        class BroadcastMessage:
            text: str
            sender: str = ""

        @dataclass
        class BroadcastResponse:
            text: str
            room: str
            from_user: str

        @MessageController()
        class TestBroadcastController:
            @MessageMapping("/chat/{room}")
            @SendTo("/topic/chat/{room}")
            async def handle_chat(
                self,
                room: str,
                message: MessagePayload[BroadcastMessage],
                principal: Principal[str | None] = None,
            ) -> BroadcastResponse:
                return BroadcastResponse(
                    text=message.text,
                    room=room,
                    from_user=principal or "anonymous",
                )

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(TestBroadcastController)

        # 두 세션 준비
        session1 = create_mock_session("session-1")
        session2 = create_mock_session("session-2")

        await broker.register_session(session1)
        await broker.register_session(session2)

        # 두 세션 모두 구독
        await broker.subscribe("/topic/chat/room1", "sub-1", session1)
        await broker.subscribe("/topic/chat/room1", "sub-2", session2)

        # session1에서 메시지 전송
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/chat/room1"},
            body='{"text": "Broadcast message", "sender": "alice"}',
        )

        context = MessageContext(
            session=session1,
            frame=frame,
            destination="/chat/room1",
            principal="alice",
        )

        # 메시지 디스패치
        result = await dispatcher.dispatch_message(context)

        # @SendTo 처리
        from bloom.web.messaging.decorators import _match_destination

        for mapping, _, method in dispatcher._message_mappings:
            match_vars = _match_destination(
                mapping.pattern, mapping.variables, "/chat/room1"
            )
            if match_vars is not None:
                context.destination_variables = match_vars
                await dispatcher.handle_send_to(context, method, result)
                break

        # 두 세션 모두 메시지 수신 확인
        assert len(session1.send.sent) > 0
        assert len(session2.send.sent) > 0


class TestMultipleControllersIntegration:
    """여러 컨트롤러 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_multiple_controllers_routing(self):
        """여러 컨트롤러로 라우팅"""

        @dataclass
        class ChatMsg:
            text: str

        @dataclass
        class ChatResp:
            text: str
            room: str

        @MessageController()
        class MultiChatController:
            @MessageMapping("/chat/{room}")
            async def handle_chat(
                self,
                room: str,
                message: MessagePayload[ChatMsg],
            ) -> ChatResp:
                return ChatResp(text=message.text, room=room)

        @Service
        class MultiNotificationService:
            def __init__(self):
                self.notifications: list = []

        @MessageController()
        class MultiNotificationController:
            notification_service: MultiNotificationService

            @MessageMapping("/notify/{user_id}")
            async def handle_notify(
                self,
                user_id: str,
                message: MessagePayload[dict],
            ) -> dict:
                self.notification_service.notifications.append(f"{user_id}: {message}")
                return {"status": "ok", "user_id": user_id}

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(MultiChatController)
        dispatcher.register_controller(MultiNotificationController)

        session = create_mock_session()
        await broker.register_session(session)

        # ChatController로 라우팅
        chat_frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/chat/lobby"},
            body='{"text": "Hello"}',
        )
        chat_context = MessageContext(
            session=session,
            frame=chat_frame,
            destination="/chat/lobby",
            principal="user1",
        )
        chat_result = await dispatcher.dispatch_message(chat_context)
        assert isinstance(chat_result, ChatResp)

        # NotificationController로 라우팅
        notify_frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/notify/user-456"},
            body='{"message": "Alert!"}',
        )
        notify_context = MessageContext(
            session=session, frame=notify_frame, destination="/notify/user-456"
        )
        notify_result = await dispatcher.dispatch_message(notify_context)
        assert notify_result["status"] == "ok"


class TestWebSocketSessionLifecycle:
    """WebSocket 세션 라이프사이클 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield

    @pytest.mark.asyncio
    async def test_session_subscription_cleanup(self):
        """세션 종료 시 구독 정리"""
        broker = SimpleBroker()

        session = create_mock_session("session-cleanup")
        await broker.register_session(session)

        # 여러 구독 등록
        await broker.subscribe("/topic/a", "sub-1", session)
        await broker.subscribe("/topic/b", "sub-2", session)
        await broker.subscribe("/topic/c", "sub-3", session)

        assert broker.get_total_subscriptions() == 3

        # 세션 해제
        await broker.unregister_session("session-cleanup")

        # 모든 구독 정리됨
        assert broker.get_total_subscriptions() == 0
        assert broker.get_session_count() == 0

    @pytest.mark.asyncio
    async def test_multiple_sessions_same_topic(self):
        """같은 토픽에 여러 세션 구독"""
        broker = SimpleBroker()

        sessions = []
        for i in range(5):
            session = create_mock_session(f"session-{i}")
            await broker.register_session(session)
            await broker.subscribe("/topic/broadcast", f"sub-{i}", session)
            sessions.append(session)

        assert broker.get_subscription_count("/topic/broadcast") == 5

        # 메시지 브로드캐스트
        sent = await broker.publish("/topic/broadcast", {"text": "Hello all"})
        assert sent == 5

        # 일부 세션 해제
        await broker.unregister_session("session-2")
        await broker.unregister_session("session-4")

        assert broker.get_subscription_count("/topic/broadcast") == 3


class TestStompProtocolIntegration:
    """STOMP 프로토콜 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_full_stomp_flow(self):
        """전체 STOMP 플로우: CONNECT -> SUBSCRIBE -> SEND -> DISCONNECT"""

        @dataclass
        class StompChatMessage:
            text: str
            sender: str = ""

        @dataclass
        class StompChatResponse:
            text: str
            room: str

        @MessageController()
        class StompTestController:
            @MessageMapping("/chat/{room}")
            @SendTo("/topic/chat/{room}")
            async def handle_chat(
                self,
                room: str,
                message: MessagePayload[StompChatMessage],
            ) -> StompChatResponse:
                return StompChatResponse(text=message.text, room=room)

            @SubscribeMapping("/topic/chat/{room}")
            async def on_subscribe(self, room: str) -> dict:
                return {"type": "joined", "room": room}

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(StompTestController)
        handler = StompMessageHandler(dispatcher, broker)

        protocol = StompProtocol()

        # STOMP 프레임 시퀀스
        frames = [
            # CONNECT
            protocol.create_connect("1.2", "localhost").serialize(),
            # SUBSCRIBE
            StompFrame(
                command=StompCommand.SUBSCRIBE,
                headers={"destination": "/topic/chat/test-room", "id": "sub-0"},
                body="",
            ).serialize(),
            # SEND
            StompFrame(
                command=StompCommand.SEND,
                headers={"destination": "/chat/test-room"},
                body='{"text": "Hello from STOMP", "sender": "tester"}',
            ).serialize(),
        ]

        # Mock receive 설정
        messages: list = [{"type": "websocket.receive", "text": f} for f in frames]
        messages.append({"type": "websocket.disconnect", "code": 1000})

        mock_receive = MockReceive(messages)
        mock_send = MockSend()

        scope = {
            "type": "websocket",
            "path": "/ws/stomp",
            "query_string": b"",
            "headers": [],
        }

        # 핸들러 실행
        await handler(scope, mock_receive, mock_send)

        # 응답 확인
        text_messages = mock_send.get_text_messages()

        # CONNECTED 프레임 확인
        connected = [m for m in text_messages if "CONNECTED" in m]
        assert len(connected) >= 1

        # MESSAGE 프레임 확인 (구독 응답 또는 SendTo 결과)
        message_frames = [m for m in text_messages if "MESSAGE" in m]
        assert len(message_frames) >= 1


class TestDestinationPatternMatching:
    """Destination 패턴 매칭 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self):
        """와일드카드 구독 패턴"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)

        # /topic/* 패턴 구독
        await broker.subscribe("/topic/*", "sub-wildcard", session)

        # 다양한 destination에 발행
        await broker.publish("/topic/chat", {"msg": "1"})
        await broker.publish("/topic/news", {"msg": "2"})
        await broker.publish("/other/path", {"msg": "3"})  # 매칭 안됨

        # /topic/* 패턴과 매칭되는 메시지만 수신
        messages = session.send.get_text_messages()
        assert len(messages) == 2  # chat, news

    @pytest.mark.asyncio
    async def test_multi_level_wildcard(self):
        """다단계 와일드카드 (/**) 패턴"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)

        # /topic/** 패턴 구독
        await broker.subscribe("/topic/**", "sub-all", session)

        # 다양한 레벨에 발행
        await broker.publish("/topic/a", {"level": 1})
        await broker.publish("/topic/a/b", {"level": 2})
        await broker.publish("/topic/a/b/c", {"level": 3})

        messages = session.send.get_text_messages()
        assert len(messages) == 3


class TestErrorHandlingIntegration:
    """에러 처리 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_no_handler_for_destination(self):
        """핸들러가 없는 destination"""
        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        # 컨트롤러 미등록

        session = create_mock_session()
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/unknown/path"},
            body="{}",
        )
        context = MessageContext(
            session=session, frame=frame, destination="/unknown/path"
        )

        from bloom.web.messaging.stomp import StompError

        with pytest.raises(StompError) as exc_info:
            await dispatcher.dispatch_message(context)

        assert "No handler" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_invalid_json_payload(self):
        """잘못된 JSON 페이로드"""

        @dataclass
        class InvalidJsonMessage:
            text: str

        @MessageController()
        class InvalidJsonController:
            @MessageMapping("/test")
            async def handle(
                self,
                message: MessagePayload[InvalidJsonMessage],
            ) -> dict:
                return {"received": message.text}

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(InvalidJsonController)

        session = create_mock_session()
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/test"},
            body="invalid json {{{",
        )
        context = MessageContext(session=session, frame=frame, destination="/test")

        # JSON 파싱 에러
        with pytest.raises(json.JSONDecodeError):
            await dispatcher.dispatch_message(context)
