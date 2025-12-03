"""메시지 브로커 테스트"""

import pytest

from bloom.web.messaging.broker import (
    SimpleBroker,
    Subscription,
    Message,
)
from bloom.web.messaging.websocket import WebSocketSession, WebSocketState


class MockReceive:
    """테스트용 가짜 receive 함수"""

    def __init__(self, messages: list[dict] | None = None):
        self.messages = messages or []
        self.index = 0

    async def __call__(self) -> dict:
        if self.index < len(self.messages):
            msg = self.messages[self.index]
            self.index += 1
            return msg
        return {"type": "websocket.disconnect", "code": 1000}


class MockSend:
    """테스트용 가짜 send 함수"""

    def __init__(self):
        self.sent: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.sent.append(message)


def create_mock_session(session_id: str = "session-1") -> WebSocketSession:
    """테스트용 WebSocketSession 생성"""
    scope = {
        "type": "websocket",
        "path": "/ws",
        "query_string": b"",
        "headers": [],
    }
    return WebSocketSession(
        scope=scope,
        receive=MockReceive(),
        send=MockSend(),
        session_id=session_id,
        state=WebSocketState.CONNECTED,
    )


class TestSimpleBroker:
    """SimpleBroker 테스트"""

    @pytest.mark.asyncio
    async def test_register_and_unregister_session(self):
        """세션 등록/해제"""
        broker = SimpleBroker()
        session = create_mock_session("session-1")

        # 등록
        await broker.register_session(session)
        assert "session-1" in broker._sessions

        # 해제
        await broker.unregister_session("session-1")
        assert "session-1" not in broker._sessions

    @pytest.mark.asyncio
    async def test_subscribe(self):
        """destination 구독"""
        broker = SimpleBroker()
        session = create_mock_session("session-1")
        await broker.register_session(session)

        # 구독
        sub = await broker.subscribe(
            destination="/topic/chat",
            subscription_id="sub-1",
            session=session,
        )

        assert sub.id == "sub-1"
        assert sub.destination == "/topic/chat"
        assert sub.session_id == "session-1"

    @pytest.mark.asyncio
    async def test_subscribe_duplicate(self):
        """중복 구독 시 기존 구독 반환"""
        broker = SimpleBroker()
        session = create_mock_session()
        await broker.register_session(session)

        sub1 = await broker.subscribe("/topic/chat", "sub-1", session)
        sub2 = await broker.subscribe("/topic/chat", "sub-1", session)

        assert sub1 is sub2

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """구독 해제"""
        broker = SimpleBroker()
        session = create_mock_session()
        await broker.register_session(session)

        await broker.subscribe("/topic/chat", "sub-1", session)
        result = await broker.unsubscribe("sub-1", session.session_id)

        assert result is True
        assert "sub-1" not in broker._subscription_by_id

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent(self):
        """존재하지 않는 구독 해제"""
        broker = SimpleBroker()
        session = create_mock_session()

        result = await broker.unsubscribe("nonexistent", session.session_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_unsubscribe_all(self):
        """세션의 모든 구독 해제"""
        broker = SimpleBroker()
        session = create_mock_session()
        await broker.register_session(session)

        await broker.subscribe("/topic/a", "sub-1", session)
        await broker.subscribe("/topic/b", "sub-2", session)

        await broker.unsubscribe_all(session.session_id)

        subs = broker.get_session_subscriptions(session.session_id)
        assert len(subs) == 0

    @pytest.mark.asyncio
    async def test_publish(self):
        """메시지 발행"""
        broker = SimpleBroker()
        session = create_mock_session()
        session._accepted = True  # send_text를 위해
        await broker.register_session(session)

        await broker.subscribe("/topic/chat", "sub-1", session)

        # 발행
        result = await broker.publish("/topic/chat", {"text": "Hello"})
        assert result == 1  # 1개 구독자

        # 메시지 수신 확인
        mock_send = session.send
        assert len(mock_send.sent) > 0

    @pytest.mark.asyncio
    async def test_publish_to_multiple_subscribers(self):
        """여러 구독자에게 발행"""
        broker = SimpleBroker()

        session1 = create_mock_session("session-1")
        session1._accepted = True
        session2 = create_mock_session("session-2")
        session2._accepted = True

        await broker.register_session(session1)
        await broker.register_session(session2)

        await broker.subscribe("/topic/chat", "sub-1", session1)
        await broker.subscribe("/topic/chat", "sub-2", session2)

        result = await broker.publish("/topic/chat", {"text": "Broadcast"})
        assert result == 2

    @pytest.mark.asyncio
    async def test_send_to_session(self):
        """특정 세션에만 메시지 전송"""
        broker = SimpleBroker()

        session1 = create_mock_session("session-1")
        session1._accepted = True
        session2 = create_mock_session("session-2")
        session2._accepted = True

        await broker.register_session(session1)
        await broker.register_session(session2)

        await broker.subscribe("/topic/chat", "sub-1", session1)
        await broker.subscribe("/topic/chat", "sub-2", session2)

        # session-1에만 전송
        result = await broker.send_to_session(
            "session-1", "/topic/chat", {"text": "Private"}
        )
        assert result is True

        # session-1만 메시지 수신
        assert len(session1.send.sent) > 0
        assert len(session2.send.sent) == 0

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_session(self):
        """존재하지 않는 세션에 전송"""
        broker = SimpleBroker()

        result = await broker.send_to_session(
            "nonexistent", "/topic/chat", {"text": "Hello"}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_get_subscriptions(self):
        """destination의 구독 목록 조회"""
        broker = SimpleBroker()

        session1 = create_mock_session("session-1")
        session2 = create_mock_session("session-2")

        await broker.register_session(session1)
        await broker.register_session(session2)

        await broker.subscribe("/topic/chat", "sub-1", session1)
        await broker.subscribe("/topic/chat", "sub-2", session2)
        await broker.subscribe("/topic/news", "sub-3", session1)

        chat_subs = broker.get_subscriptions("/topic/chat")
        assert len(chat_subs) == 2

        news_subs = broker.get_subscriptions("/topic/news")
        assert len(news_subs) == 1

    @pytest.mark.asyncio
    async def test_get_session_subscriptions(self):
        """세션의 구독 목록 조회"""
        broker = SimpleBroker()
        session = create_mock_session()
        await broker.register_session(session)

        await broker.subscribe("/topic/a", "sub-1", session)
        await broker.subscribe("/topic/b", "sub-2", session)

        subs = broker.get_session_subscriptions(session.session_id)
        assert len(subs) == 2

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self):
        """구독자 없는 destination에 발행"""
        broker = SimpleBroker()

        result = await broker.publish("/topic/empty", {"text": "Hello"})
        assert result == 0


class TestSubscription:
    """Subscription 데이터클래스 테스트"""

    def test_subscription_creation(self):
        """Subscription 생성"""
        session = create_mock_session("session-1")
        sub = Subscription(
            id="sub-1",
            destination="/topic/chat",
            session_id="session-1",
            session=session,
            ack_mode="auto",
        )

        assert sub.id == "sub-1"
        assert sub.destination == "/topic/chat"
        assert sub.session_id == "session-1"
        assert sub.ack_mode == "auto"


class TestMessage:
    """Message 데이터클래스 테스트"""

    def test_message_creation(self):
        """Message 생성"""
        msg = Message(
            destination="/topic/chat",
            body={"text": "Hello"},
            headers={"custom": "header"},
            message_id="msg-1",
        )

        assert msg.destination == "/topic/chat"
        assert msg.body == {"text": "Hello"}
        assert msg.headers["custom"] == "header"
        assert msg.message_id == "msg-1"

    def test_message_default_values(self):
        """Message 기본값"""
        msg = Message(
            destination="/topic/test",
            body="Simple text",
        )

        assert msg.headers == {}
        assert msg.message_id is not None  # UUID 자동 생성
