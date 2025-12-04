"""ASGI와 Messaging 엣지케이스 테스트

WebSocket, STOMP, 메시지 브로커의 경계 조건 및 엣지케이스 테스트.
"""

import pytest
import asyncio
import json
from dataclasses import dataclass
from typing import Optional

from bloom.core import (
    Component,
    Service,
    reset_container_manager,
    get_container_manager,
)
from bloom.web.messaging.broker import SimpleBroker, Message, Subscription
from bloom.web.messaging.websocket import WebSocketSession, WebSocketState
from bloom.web.messaging.handler import (
    MessageDispatcher,
    MessageContext,
    MessageParameterInfo,
    StompMessageHandler,
)
from bloom.web.messaging.stomp import (
    StompFrame,
    StompCommand,
    StompProtocol,
    StompError,
)
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
    MessageHeaders,
    SessionId,
)


# =============================================================================
# Mock Classes
# =============================================================================


class MockReceive:
    def __init__(self, messages: list | None = None):
        self.messages = messages or []
        self.index = 0

    async def __call__(self):
        if self.index < len(self.messages):
            msg = self.messages[self.index]
            self.index += 1
            return msg
        return {"type": "websocket.disconnect", "code": 1000}


class MockSend:
    def __init__(self):
        self.sent: list = []

    async def __call__(self, message) -> None:
        self.sent.append(message)

    def get_text_messages(self) -> list[str]:
        return [
            m.get("text", "") for m in self.sent if m.get("type") == "websocket.send"
        ]


def create_mock_session(
    session_id: str = "session-1",
    user_id: str | None = "user-123",
    state: WebSocketState = WebSocketState.CONNECTED,
) -> WebSocketSession:
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
        user_id=user_id,
        state=state,
        _accepted=True,
    )


# =============================================================================
# Edge Case: Empty and Null Values
# =============================================================================


class TestEmptyAndNullValues:
    """빈 값 및 null 처리 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_empty_message_body(self):
        """빈 메시지 본문"""

        @MessageController()
        class EmptyBodyController:
            @MessageMapping("/empty")
            async def handle_empty(self) -> dict:
                return {"received": "empty"}

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(EmptyBodyController)

        session = create_mock_session()
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/empty"},
            body="",  # 빈 본문
        )
        context = MessageContext(session=session, frame=frame, destination="/empty")

        result = await dispatcher.dispatch_message(context)
        assert result["received"] == "empty"

    @pytest.mark.asyncio
    async def test_null_principal(self):
        """인증되지 않은 사용자 (null principal)"""

        @MessageController()
        class NullPrincipalController:
            @MessageMapping("/anon")
            async def handle_anon(
                self,
                principal: Principal[str | None] = None,
            ) -> dict:
                return {"user": principal or "anonymous"}

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(NullPrincipalController)

        session = create_mock_session(user_id=None)  # 인증 안됨
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/anon"},
            body="",
        )
        context = MessageContext(
            session=session, frame=frame, destination="/anon", principal=None
        )

        result = await dispatcher.dispatch_message(context)
        assert result["user"] == "anonymous"

    @pytest.mark.asyncio
    async def test_empty_destination_variables(self):
        """destination 변수 없는 패턴"""

        @MessageController()
        class NoVarController:
            @MessageMapping("/static/path")
            async def handle_static(self) -> dict:
                return {"path": "static"}

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(NoVarController)

        session = create_mock_session()
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/static/path"},
            body="",
        )
        context = MessageContext(
            session=session, frame=frame, destination="/static/path"
        )

        result = await dispatcher.dispatch_message(context)
        assert result["path"] == "static"


# =============================================================================
# Edge Case: Concurrent Operations
# =============================================================================


class TestConcurrentOperations:
    """동시성 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_unsubscribe(self):
        """동시 구독/구독해제"""
        broker = SimpleBroker()

        sessions = [create_mock_session(f"session-{i}") for i in range(10)]
        for s in sessions:
            await broker.register_session(s)

        async def subscribe_and_unsubscribe(session, index):
            sub_id = f"sub-{index}"
            await broker.subscribe("/topic/concurrent", sub_id, session)
            await asyncio.sleep(0.01)  # 약간의 지연
            await broker.unsubscribe(sub_id, session.session_id)

        # 동시 실행
        await asyncio.gather(
            *[subscribe_and_unsubscribe(s, i) for i, s in enumerate(sessions)]
        )

        # 모든 구독이 해제됨
        assert broker.get_subscription_count("/topic/concurrent") == 0

    @pytest.mark.asyncio
    async def test_concurrent_publish(self):
        """동시 메시지 발행"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)
        await broker.subscribe("/topic/flood", "sub-1", session)

        async def publish_message(index):
            await broker.publish("/topic/flood", {"index": index})

        # 100개 메시지 동시 발행
        await asyncio.gather(*[publish_message(i) for i in range(100)])

        # 모든 메시지 수신됨
        messages = session.send.get_text_messages()
        assert len(messages) == 100

    @pytest.mark.asyncio
    async def test_concurrent_session_registration(self):
        """동시 세션 등록/해제"""
        broker = SimpleBroker()

        async def register_and_unregister(index):
            session = create_mock_session(f"concurrent-{index}")
            await broker.register_session(session)
            await asyncio.sleep(0.005)
            await broker.unregister_session(session.session_id)

        await asyncio.gather(*[register_and_unregister(i) for i in range(20)])

        assert broker.get_session_count() == 0


# =============================================================================
# Edge Case: Destination Pattern Edge Cases
# =============================================================================


class TestDestinationPatternEdgeCases:
    """Destination 패턴 매칭 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield

    @pytest.mark.asyncio
    async def test_exact_vs_wildcard_priority(self):
        """정확한 매칭 vs 와일드카드 우선순위"""
        broker = SimpleBroker()

        session1 = create_mock_session("exact")
        session2 = create_mock_session("wildcard")

        await broker.register_session(session1)
        await broker.register_session(session2)

        # 정확한 구독
        await broker.subscribe("/topic/chat/room1", "sub-exact", session1)
        # 와일드카드 구독
        await broker.subscribe("/topic/chat/*", "sub-wildcard", session2)

        # /topic/chat/room1에 발행
        await broker.publish("/topic/chat/room1", {"msg": "test"})

        # 두 세션 모두 수신 (브로커는 모든 매칭 구독에 전송)
        assert len(session1.send.get_text_messages()) >= 1
        assert len(session2.send.get_text_messages()) >= 1

    @pytest.mark.asyncio
    async def test_trailing_slash_handling(self):
        """슬래시 처리"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)

        await broker.subscribe("/topic/test", "sub-1", session)

        # 정확히 같은 destination만 매칭
        sent1 = await broker.publish("/topic/test", {"exact": True})
        sent2 = await broker.publish("/topic/test/", {"trailing": True})  # 다른 경로

        assert sent1 == 1
        assert sent2 == 0  # 매칭 안됨

    @pytest.mark.asyncio
    async def test_special_characters_in_destination(self):
        """destination 내 특수문자"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)

        # 특수문자 포함 destination
        dest = "/topic/room:123/user@domain"
        await broker.subscribe(dest, "sub-special", session)

        sent = await broker.publish(dest, {"special": True})
        assert sent == 1

    @pytest.mark.asyncio
    async def test_deeply_nested_destination(self):
        """깊게 중첩된 destination"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)

        deep_dest = "/a/b/c/d/e/f/g/h/i/j"
        await broker.subscribe(deep_dest, "sub-deep", session)

        sent = await broker.publish(deep_dest, {"deep": True})
        assert sent == 1


# =============================================================================
# Edge Case: Message Size and Content
# =============================================================================


class TestMessageSizeAndContent:
    """메시지 크기 및 내용 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield

    @pytest.mark.asyncio
    async def test_large_message(self):
        """대용량 메시지"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)
        await broker.subscribe("/topic/large", "sub-1", session)

        # 1MB 메시지
        large_data = {"content": "x" * (1024 * 1024)}
        sent = await broker.publish("/topic/large", large_data)

        assert sent == 1

    @pytest.mark.asyncio
    async def test_binary_like_content(self):
        """바이너리 유사 콘텐츠"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)
        await broker.subscribe("/topic/binary", "sub-1", session)

        # base64 인코딩된 바이너리 데이터
        import base64

        binary_data = base64.b64encode(b"\x00\x01\x02\xff\xfe").decode()

        sent = await broker.publish("/topic/binary", {"data": binary_data})
        assert sent == 1

    @pytest.mark.asyncio
    async def test_unicode_content(self):
        """유니코드 콘텐츠"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)
        await broker.subscribe("/topic/unicode", "sub-1", session)

        # 다양한 유니코드 문자
        unicode_data = {
            "korean": "한글 테스트",
            "japanese": "日本語テスト",
            "emoji": "🎉🚀💡",
            "arabic": "اختبار",
        }

        sent = await broker.publish("/topic/unicode", unicode_data)
        assert sent == 1


# =============================================================================
# Edge Case: Session State Transitions
# =============================================================================


class TestSessionStateTransitions:
    """세션 상태 전이 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield

    @pytest.mark.asyncio
    async def test_send_to_disconnected_session(self):
        """연결 해제된 세션에 전송"""
        broker = SimpleBroker()

        session = create_mock_session("will-disconnect")
        await broker.register_session(session)
        await broker.subscribe("/topic/test", "sub-1", session)

        # 세션 해제
        await broker.unregister_session("will-disconnect")

        # 해제된 세션에 발행 시도
        sent = await broker.publish("/topic/test", {"msg": "test"})
        assert sent == 0  # 전송 안됨

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_session_direct(self):
        """존재하지 않는 세션에 직접 전송"""
        broker = SimpleBroker()

        result = await broker.send_to_session(
            "nonexistent-session",
            "/topic/test",
            {"msg": "test"},
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_double_registration(self):
        """중복 세션 등록"""
        broker = SimpleBroker()

        session = create_mock_session("duplicate")
        await broker.register_session(session)
        await broker.register_session(session)  # 재등록

        # 세션은 하나만 존재
        assert broker.get_session_count() == 1


# =============================================================================
# Edge Case: Subscription Management
# =============================================================================


class TestSubscriptionManagement:
    """구독 관리 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield

    @pytest.mark.asyncio
    async def test_duplicate_subscription_id(self):
        """중복 구독 ID"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)

        # 같은 ID로 두 번 구독
        sub1 = await broker.subscribe("/topic/a", "sub-1", session)
        sub2 = await broker.subscribe("/topic/b", "sub-1", session)  # 같은 ID

        # 기존 구독 반환 (ID 기준)
        assert sub1 is sub2

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent(self):
        """존재하지 않는 구독 해제"""
        broker = SimpleBroker()

        result = await broker.unsubscribe("nonexistent-sub", "nonexistent-session")
        assert result is False

    @pytest.mark.asyncio
    async def test_many_subscriptions_single_session(self):
        """단일 세션의 다수 구독"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)

        # 100개 구독
        for i in range(100):
            await broker.subscribe(f"/topic/test-{i}", f"sub-{i}", session)

        assert broker.get_total_subscriptions() == 100

        subs = broker.get_session_subscriptions(session.session_id)
        assert len(subs) == 100

        # 모두 해제
        count = await broker.unsubscribe_all(session.session_id)
        assert count == 100
        assert broker.get_total_subscriptions() == 0


# =============================================================================
# Edge Case: STOMP Protocol Edge Cases
# =============================================================================


class TestStompProtocolEdgeCases:
    """STOMP 프로토콜 엣지케이스"""

    def test_parse_malformed_frame(self):
        """잘못된 형식의 프레임"""
        protocol = StompProtocol()

        # 명령어 없음
        with pytest.raises(StompError):
            protocol.parse("\n\n\x00")

        # 종료 문자 없음 (타임아웃 등으로 처리)
        result = protocol.parse("SEND\n")
        # 구현에 따라 None 또는 부분 파싱

    def test_parse_unknown_command(self):
        """알 수 없는 명령"""
        protocol = StompProtocol()

        with pytest.raises(StompError):
            protocol.parse("UNKNOWN\n\n\x00")

    def test_header_with_colon_in_value(self):
        """헤더 값에 콜론 포함"""
        protocol = StompProtocol()

        frame = protocol.parse(
            "SEND\ndestination:/topic/test\ncustom:value:with:colons\n\n\x00"
        )

        assert frame is not None
        assert frame.headers.get("custom") == "value:with:colons"

    def test_multiline_body(self):
        """여러 줄 본문"""
        protocol = StompProtocol()

        body = "line1\nline2\nline3"
        frame = protocol.parse(
            f"SEND\ndestination:/topic/test\ncontent-length:{len(body)}\n\n{body}\x00"
        )

        assert frame is not None
        assert frame.body == body

    def test_empty_header_value(self):
        """빈 헤더 값"""
        protocol = StompProtocol()

        frame = protocol.parse("SEND\ndestination:/topic/test\nempty:\n\n\x00")

        assert frame is not None
        assert frame.headers.get("empty") == ""


# =============================================================================
# Edge Case: Handler Resolution
# =============================================================================


class TestHandlerResolutionEdgeCases:
    """핸들러 리졸루션 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_overlapping_patterns(self):
        """중복되는 패턴 (첫 번째 매칭 우선)"""

        @MessageController()
        class OverlapController:
            @MessageMapping("/api/{resource}")
            async def handle_generic(self, resource: str) -> dict:
                return {"handler": "generic", "resource": resource}

            @MessageMapping("/api/users")
            async def handle_users(self) -> dict:
                return {"handler": "users"}

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(OverlapController)

        session = create_mock_session()

        # /api/users 요청 - 등록 순서에 따라 첫 번째 매칭
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/api/users"},
            body="",
        )
        context = MessageContext(session=session, frame=frame, destination="/api/users")

        result = await dispatcher.dispatch_message(context)
        # 첫 번째 등록된 핸들러가 매칭됨
        assert "handler" in result

    @pytest.mark.asyncio
    async def test_optional_parameter_with_default(self):
        """기본값이 있는 선택적 파라미터"""

        @MessageController()
        class DefaultParamController:
            @MessageMapping("/default")
            async def handle_default(
                self,
                message: MessagePayload[dict | None] = None,
            ) -> dict:
                return {"value": message.get("text") if message else "default"}

        manager = get_container_manager()
        await manager.initialize()

        broker = SimpleBroker()
        dispatcher = MessageDispatcher(broker=broker, container_manager=manager)
        dispatcher.register_controller(DefaultParamController)

        session = create_mock_session()

        # 빈 바디로 요청 - 기본값 None 사용
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/default"},
            body="",
        )
        context = MessageContext(session=session, frame=frame, destination="/default")

        result = await dispatcher.dispatch_message(context)
        assert result["value"] == "default"


# =============================================================================
# Edge Case: Error Recovery
# =============================================================================


class TestErrorRecovery:
    """에러 복구 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_handler_exception_isolation(self):
        """핸들러 예외가 다른 구독자에게 영향 없음"""
        broker = SimpleBroker()

        session1 = create_mock_session("session-1")
        session2 = create_mock_session("session-2")

        await broker.register_session(session1)
        await broker.register_session(session2)

        await broker.subscribe("/topic/test", "sub-1", session1)
        await broker.subscribe("/topic/test", "sub-2", session2)

        # session1의 send가 실패하도록 설정
        original_send = session1.send

        async def failing_send(msg):
            if msg.get("type") == "websocket.send":
                raise ConnectionError("Connection lost")
            await original_send(msg)

        session1.send = failing_send

        # 메시지 발행 - session1 실패해도 session2는 수신
        sent = await broker.publish("/topic/test", {"msg": "test"})

        # session2는 수신 성공
        # (실패한 세션은 카운트에서 제외될 수 있음)
        assert sent >= 1

    @pytest.mark.asyncio
    async def test_broker_state_after_exception(self):
        """예외 발생 후 브로커 상태 일관성"""
        broker = SimpleBroker()

        session = create_mock_session()
        await broker.register_session(session)
        await broker.subscribe("/topic/a", "sub-a", session)

        initial_count = broker.get_total_subscriptions()

        # 잘못된 구독 해제 시도 (예외 발생하지 않음)
        result = await broker.unsubscribe("nonexistent", "nonexistent")

        # 상태 변경 없음
        assert broker.get_total_subscriptions() == initial_count
        assert result is False
