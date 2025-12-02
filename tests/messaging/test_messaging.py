"""WebSocket STOMP 메시징 테스트"""

import pytest
import asyncio
from dataclasses import dataclass

from bloom.web.messaging import (
    Message,
    StompFrame,
    StompCommand,
    SimpleBroker,
    MessageMapping,
    SendTo,
    SendToUser,
    SubscribeMapping,
    MessageController,
    is_message_controller,
    get_prefix,
    SimpMessagingTemplate,
    WebSocketSession,
    WebSocketDisconnect,
    WebSocketSessionManager,
    StompProtocolHandler,
)


# ============================================================================
# Message 모델 테스트
# ============================================================================


class TestStompFrame:
    """StompFrame 테스트"""

    async def test_parse_connect_frame(self):
        """CONNECT 프레임 파싱"""
        raw = "CONNECT\naccept-version:1.2\nhost:localhost\n\n\x00"
        frame = StompFrame.parse(raw)

        assert frame.command == StompCommand.CONNECT
        assert frame.headers["accept-version"] == "1.2"
        assert frame.headers["host"] == "localhost"
        assert frame.body == ""

    async def test_parse_send_frame_with_body(self):
        """SEND 프레임 파싱 (body 포함)"""
        raw = 'SEND\ndestination:/app/chat\ncontent-type:application/json\n\n{"text":"hello"}\x00'
        frame = StompFrame.parse(raw)

        assert frame.command == StompCommand.SEND
        assert frame.headers["destination"] == "/app/chat"
        assert frame.body == '{"text":"hello"}'

    async def test_parse_subscribe_frame(self):
        """SUBSCRIBE 프레임 파싱"""
        raw = "SUBSCRIBE\nid:sub-0\ndestination:/topic/chat\n\n\x00"
        frame = StompFrame.parse(raw)

        assert frame.command == StompCommand.SUBSCRIBE
        assert frame.headers["id"] == "sub-0"
        assert frame.headers["destination"] == "/topic/chat"

    async def test_encode_connected_frame(self):
        """CONNECTED 프레임 인코딩"""
        frame = StompFrame(
            command=StompCommand.CONNECTED,
            headers={"version": "1.2", "server": "bloom"},
        )
        encoded = frame.encode()

        assert "CONNECTED" in encoded
        assert "version:1.2" in encoded
        assert "server:bloom" in encoded
        assert encoded.endswith("\x00")

    async def test_encode_message_frame(self):
        """MESSAGE 프레임 인코딩"""
        frame = StompFrame(
            command=StompCommand.MESSAGE,
            headers={"destination": "/topic/chat", "subscription": "sub-0"},
            body='{"text":"hello"}',
        )
        encoded = frame.encode()

        assert "MESSAGE" in encoded
        assert "destination:/topic/chat" in encoded
        assert '{"text":"hello"}' in encoded


class TestMessage:
    """Message 테스트"""

    async def test_create_message(self):
        """Message 생성"""
        msg = Message(
            destination="/topic/chat",
            payload={"text": "hello"},
            user="alice",
        )

        assert msg.destination == "/topic/chat"
        assert msg.payload == {"text": "hello"}
        assert msg.user == "alice"

    async def test_to_json(self):
        """Message to JSON"""
        msg = Message(
            destination="/topic/chat",
            payload={"text": "hello", "count": 42},
        )

        json_str = msg.to_json()
        assert '"text": "hello"' in json_str or '"text":"hello"' in json_str

    async def test_from_stomp_frame(self):
        """STOMP 프레임에서 Message 생성"""
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/app/chat", "id": "sub-0"},
            body='{"text":"hello"}',
        )

        msg = Message.from_stomp_frame(frame, session_id="sess-1", user="alice")

        assert msg.destination == "/app/chat"
        assert msg.payload == {"text": "hello"}
        assert msg.session_id == "sess-1"
        assert msg.user == "alice"

    async def test_to_stomp_frame(self):
        """Message to STOMP 프레임"""
        msg = Message(
            destination="/topic/chat",
            payload={"text": "hello"},
            subscription_id="sub-0",
        )

        frame = msg.to_stomp_frame()

        assert frame.command == StompCommand.MESSAGE
        assert frame.headers["destination"] == "/topic/chat"
        assert frame.headers["subscription"] == "sub-0"


# ============================================================================
# SimpleBroker 테스트
# ============================================================================


class TestSimpleBroker:
    """SimpleBroker 테스트"""

    @pytest.mark.asyncio
    async def test_subscribe_and_publish_topic(self):
        """토픽 구독 및 발행"""
        broker = SimpleBroker()
        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        await broker.subscribe(
            subscription_id="sub-1",
            destination="/topic/chat",
            session_id="sess-1",
            send_callback=callback,
        )

        msg = Message(destination="/topic/chat", payload={"text": "hello"})
        count = await broker.publish(msg)

        assert count == 1
        assert len(received) == 1
        assert received[0].payload == {"text": "hello"}

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_subscribers(self):
        """다중 구독자에게 브로드캐스트"""
        broker = SimpleBroker()
        received1: list[Message] = []
        received2: list[Message] = []

        async def callback1(msg: Message):
            received1.append(msg)

        async def callback2(msg: Message):
            received2.append(msg)

        await broker.subscribe("sub-1", "/topic/chat", "sess-1", callback1)
        await broker.subscribe("sub-2", "/topic/chat", "sess-2", callback2)

        msg = Message(destination="/topic/chat", payload={"text": "hello"})
        count = await broker.publish(msg)

        assert count == 2
        assert len(received1) == 1
        assert len(received2) == 1

    @pytest.mark.asyncio
    async def test_queue_round_robin(self):
        """큐 라운드로빈 전송"""
        broker = SimpleBroker()
        received1: list[Message] = []
        received2: list[Message] = []

        async def callback1(msg: Message):
            received1.append(msg)

        async def callback2(msg: Message):
            received2.append(msg)

        await broker.subscribe("sub-1", "/queue/work", "sess-1", callback1)
        await broker.subscribe("sub-2", "/queue/work", "sess-2", callback2)

        # 3개 메시지 전송 → 라운드로빈
        for i in range(3):
            msg = Message(destination="/queue/work", payload={"id": i})
            await broker.publish(msg)

        # 1-2-1 또는 2-1-2 분배
        assert len(received1) + len(received2) == 3
        assert len(received1) >= 1
        assert len(received2) >= 1

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """구독 해제"""
        broker = SimpleBroker()
        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        await broker.subscribe("sub-1", "/topic/chat", "sess-1", callback)
        await broker.unsubscribe("sub-1", "sess-1")

        msg = Message(destination="/topic/chat", payload={"text": "hello"})
        count = await broker.publish(msg)

        assert count == 0
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_disconnect_cleans_subscriptions(self):
        """세션 연결 해제 시 구독 정리"""
        broker = SimpleBroker()
        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        await broker.subscribe("sub-1", "/topic/chat", "sess-1", callback)
        await broker.subscribe("sub-2", "/topic/news", "sess-1", callback)
        await broker.disconnect("sess-1")

        msg1 = Message(destination="/topic/chat", payload={})
        msg2 = Message(destination="/topic/news", payload={})

        await broker.publish(msg1)
        await broker.publish(msg2)

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_wildcard_subscription(self):
        """와일드카드 구독"""
        broker = SimpleBroker()
        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        # /topic/chat.* 패턴 구독
        await broker.subscribe("sub-1", "/topic/chat.*", "sess-1", callback)

        # 패턴 매칭되는 메시지
        msg1 = Message(destination="/topic/chat.room1", payload={"room": 1})
        msg2 = Message(destination="/topic/chat.room2", payload={"room": 2})
        # 매칭 안되는 메시지
        msg3 = Message(destination="/topic/news", payload={"news": True})

        await broker.publish(msg1)
        await broker.publish(msg2)
        await broker.publish(msg3)

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_send_to_user(self):
        """특정 사용자에게 메시지 전송"""
        broker = SimpleBroker()
        alice_received: list[Message] = []
        bob_received: list[Message] = []

        async def alice_callback(msg: Message):
            alice_received.append(msg)

        async def bob_callback(msg: Message):
            bob_received.append(msg)

        await broker.subscribe(
            "sub-1", "/queue/notifications", "sess-alice", alice_callback, user="alice"
        )
        await broker.subscribe(
            "sub-2", "/queue/notifications", "sess-bob", bob_callback, user="bob"
        )

        msg = Message(destination="/queue/notifications", payload={"alert": "hi"})
        count = await broker.send_to_user("alice", "/queue/notifications", msg)

        assert count == 1
        assert len(alice_received) == 1
        assert len(bob_received) == 0


# ============================================================================
# SimpMessagingTemplate 테스트
# ============================================================================


class TestSimpMessagingTemplate:
    """SimpMessagingTemplate 테스트"""

    @pytest.mark.asyncio
    async def test_convert_and_send(self):
        """메시지 변환 및 전송"""
        broker = SimpleBroker()
        template = SimpMessagingTemplate(broker)
        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        await broker.subscribe("sub-1", "/topic/chat", "sess-1", callback)

        count = await template.convert_and_send("/topic/chat", {"text": "hello"})

        assert count == 1
        assert received[0].payload == {"text": "hello"}

    @pytest.mark.asyncio
    async def test_convert_and_send_to_user(self):
        """특정 사용자에게 메시지 전송"""
        broker = SimpleBroker()
        template = SimpMessagingTemplate(broker)
        received: list[Message] = []

        async def callback(msg: Message):
            received.append(msg)

        await broker.subscribe(
            "sub-1", "/queue/notifications", "sess-1", callback, user="alice"
        )

        count = await template.convert_and_send_to_user(
            "alice", "/queue/notifications", {"alert": "hi"}
        )

        assert count == 1
        assert received[0].payload == {"alert": "hi"}


# ============================================================================
# WebSocketSession 테스트
# ============================================================================


class TestWebSocketSession:
    """WebSocketSession 테스트"""

    @pytest.mark.asyncio
    async def test_session_creation(self):
        """세션 생성"""
        session = WebSocketSession(
            path="/ws",
            headers={"authorization": "Bearer token"},
            query_params={"room": "123"},
        )

        assert session.path == "/ws"
        assert session.headers["authorization"] == "Bearer token"
        assert session.query_params["room"] == "123"
        assert session.id is not None

    @pytest.mark.asyncio
    async def test_session_manager(self):
        """세션 매니저"""
        manager = WebSocketSessionManager()

        session1 = WebSocketSession(path="/ws", user="alice")
        session2 = WebSocketSession(path="/ws", user="bob")

        manager.add(session1)
        manager.add(session2)

        assert manager.count == 2
        assert manager.get(session1.id) == session1
        assert len(manager.get_by_user("alice")) == 1

        manager.remove(session1.id)
        assert manager.count == 1


# ============================================================================
# 데코레이터 테스트
# ============================================================================


class TestDecorators:
    """데코레이터 테스트"""

    async def test_message_mapping(self):
        """@MessageMapping 데코레이터"""

        class TestController:
            @MessageMapping("/chat.send")
            def handle_chat(self, msg):
                return msg

        from bloom.core.container import HandlerContainer

        container = HandlerContainer.get_container(TestController.handle_chat)
        assert container is not None
        assert (
            container.get_metadata("message_mapping", raise_exception=False)
            == "/chat.send"
        )

    async def test_send_to(self):
        """@SendTo 데코레이터"""

        class TestController:
            @MessageMapping("/chat.send")
            @SendTo("/topic/chat")
            def handle_chat(self, msg):
                return msg

        from bloom.core.container import HandlerContainer

        container = HandlerContainer.get_container(TestController.handle_chat)
        if container is None:
            raise AssertionError("HandlerContainer not found for handle_chat")
        assert container.get_metadata("send_to", raise_exception=False) == "/topic/chat"

    async def test_send_to_user(self):
        """@SendToUser 데코레이터"""

        class TestController:
            @MessageMapping("/chat.private")
            @SendToUser("/queue/private")
            def private_message(self, msg):
                return msg

        from bloom.core.container import HandlerContainer

        container = HandlerContainer.get_container(TestController.private_message)
        if container is None:
            raise AssertionError("HandlerContainer not found for private_message")
        assert (
            container.get_metadata("send_to_user", raise_exception=False)
            == "/queue/private"
        )

    async def test_subscribe_mapping(self):
        """@SubscribeMapping 데코레이터"""

        class TestController:
            @SubscribeMapping("/topic/init")
            def on_subscribe(self):
                return []

        from bloom.core.container import HandlerContainer

        container = HandlerContainer.get_container(TestController.on_subscribe)
        if container is None:
            raise AssertionError("HandlerContainer not found for on_subscribe")
        assert (
            container.get_metadata("subscribe_mapping", raise_exception=False)
            == "/topic/init"
        )


# ============================================================================
# MessageController 테스트
# ============================================================================


class TestMessageController:
    """MessageController 테스트"""

    async def test_message_controller_decorator(self):
        """@MessageController 데코레이터"""

        @MessageController
        class ChatController:
            @MessageMapping("/chat.send")
            def handle_chat(self, msg):
                return msg

        assert is_message_controller(ChatController)
        assert get_prefix(ChatController) == ""

    async def test_message_controller_with_prefix(self):
        """@MessageController with prefix"""

        @MessageController("/v1")
        class ChatController:
            pass

        assert get_prefix(ChatController) == "/v1"


# ============================================================================
# 통합 시나리오 테스트
# ============================================================================


@dataclass
class ChatMessage:
    sender: str
    content: str
    room_id: str


class TestIntegrationScenarios:
    """통합 시나리오 테스트"""

    @pytest.mark.asyncio
    async def test_chat_room_scenario(self):
        """채팅방 시나리오"""
        broker = SimpleBroker()
        template = SimpMessagingTemplate(broker)

        # 3명의 사용자가 채팅방 구독
        user_messages: dict[str, list[Message]] = {
            "alice": [],
            "bob": [],
            "charlie": [],
        }

        for user in user_messages:

            async def callback(msg: Message, u=user):
                user_messages[u].append(msg)

            await broker.subscribe(
                f"sub-{user}",
                "/topic/chat.room1",
                f"sess-{user}",
                callback,
                user=user,
            )

        # Alice가 메시지 전송
        await template.convert_and_send(
            "/topic/chat.room1",
            {"sender": "alice", "content": "Hello everyone!"},
        )

        # 모든 사용자가 메시지 수신
        for user in user_messages:
            assert len(user_messages[user]) == 1
            assert user_messages[user][0].payload["sender"] == "alice"

    @pytest.mark.asyncio
    async def test_private_notification_scenario(self):
        """개인 알림 시나리오"""
        broker = SimpleBroker()
        template = SimpMessagingTemplate(broker)

        alice_notifications: list[Message] = []
        bob_notifications: list[Message] = []

        async def alice_callback(msg: Message):
            alice_notifications.append(msg)

        async def bob_callback(msg: Message):
            bob_notifications.append(msg)

        await broker.subscribe(
            "sub-alice",
            "/queue/notifications",
            "sess-alice",
            alice_callback,
            user="alice",
        )
        await broker.subscribe(
            "sub-bob",
            "/queue/notifications",
            "sess-bob",
            bob_callback,
            user="bob",
        )

        # Alice에게만 알림
        await template.convert_and_send_to_user(
            "alice",
            "/queue/notifications",
            {"title": "New Order", "body": "Order #123 completed"},
        )

        assert len(alice_notifications) == 1
        assert len(bob_notifications) == 0
        assert alice_notifications[0].payload["title"] == "New Order"
