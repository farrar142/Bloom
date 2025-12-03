"""메시지 핸들러 테스트"""

import pytest
import json
from dataclasses import dataclass
from typing import Annotated

from bloom.web.messaging.handler import (
    MessageContext,
    MessageParameterInfo,
    MessageDispatcher,
    MessagePayloadResolver,
    DestinationVariableResolver,
    PrincipalResolver,
    SessionIdResolver,
    WebSocketSessionResolver,
    MessageContextResolver,
    ImplicitDestinationVariableResolver,
)
from bloom.web.messaging.stomp import StompFrame, StompCommand
from bloom.web.messaging.websocket import WebSocketSession, WebSocketState
from bloom.web.messaging.decorators import (
    MessageMapping,
    SubscribeMapping,
    SendTo,
    MessageController,
)
from bloom.web.messaging.params import (
    DestinationVariable,
    MessagePayload,
    MessageHeaders,
    Principal,
)


class MockReceive:
    async def __call__(self):
        return {"type": "websocket.disconnect"}


class MockSend:
    def __init__(self):
        self.sent = []

    async def __call__(self, msg):
        self.sent.append(msg)


def create_mock_session(session_id: str = "test-session") -> WebSocketSession:
    return WebSocketSession(
        scope={"type": "websocket", "path": "/ws"},
        receive=MockReceive(),
        send=MockSend(),
        session_id=session_id,
        user_id="user-123",
        state=WebSocketState.CONNECTED,
    )


def create_context(
    destination: str = "/test",
    body: str = "",
    headers: dict | None = None,
    dest_vars: dict | None = None,
    principal: str | None = "user-123",
) -> MessageContext:
    session = create_mock_session()
    frame = StompFrame(
        command=StompCommand.SEND,
        headers={"destination": destination, **(headers or {})},
        body=body,
    )
    return MessageContext(
        session=session,
        frame=frame,
        destination=destination,
        destination_variables=dest_vars or {},
        principal=principal,
    )


class TestMessageContext:
    """MessageContext 테스트"""

    def test_context_properties(self):
        """컨텍스트 프로퍼티"""
        ctx = create_context(
            destination="/chat/room1",
            body='{"text": "hello"}',
            headers={"custom": "header"},
        )

        assert ctx.destination == "/chat/room1"
        assert ctx.body == '{"text": "hello"}'
        assert ctx.headers["custom"] == "header"
        assert ctx.session_id == "test-session"

    def test_body_as_json(self):
        """JSON 파싱"""
        ctx = create_context(body='{"key": "value"}')
        data = ctx.body_as_json()

        assert data == {"key": "value"}

    def test_body_as_json_empty(self):
        """빈 본문 JSON 파싱"""
        ctx = create_context(body="")
        data = ctx.body_as_json()

        assert data == {}


class TestMessagePayloadResolver:
    """MessagePayloadResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return MessagePayloadResolver()

    @dataclass
    class ChatMessage:
        text: str
        sender: str = ""

    def test_supports_with_marker(self, resolver):
        """MessagePayload 마커 지원"""
        from bloom.web.messaging.params import MessagePayloadMarker

        param = MessageParameterInfo(
            name="message",
            annotation=Annotated[dict, MessagePayloadMarker()],
            actual_type=dict,
            marker=MessagePayloadMarker(),
            default=None,
            has_default=False,
            is_optional=False,
        )

        assert resolver.supports(param)

    def test_not_supports_without_marker(self, resolver):
        """마커 없으면 미지원"""
        param = MessageParameterInfo(
            name="data",
            annotation=dict,
            actual_type=dict,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        assert not resolver.supports(param)

    @pytest.mark.asyncio
    async def test_resolve_dict(self, resolver):
        """dict 타입 리졸빙"""
        from bloom.web.messaging.params import MessagePayloadMarker

        param = MessageParameterInfo(
            name="data",
            annotation=dict,
            actual_type=dict,
            marker=MessagePayloadMarker(),
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context(body='{"key": "value"}')

        result = await resolver.resolve(param, ctx)
        assert result == {"key": "value"}

    @pytest.mark.asyncio
    async def test_resolve_str(self, resolver):
        """str 타입 리졸빙"""
        from bloom.web.messaging.params import MessagePayloadMarker

        param = MessageParameterInfo(
            name="data",
            annotation=str,
            actual_type=str,
            marker=MessagePayloadMarker(),
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context(body="raw text")

        result = await resolver.resolve(param, ctx)
        assert result == "raw text"

    @pytest.mark.asyncio
    async def test_resolve_dataclass(self, resolver):
        """dataclass 타입 리졸빙"""
        from bloom.web.messaging.params import MessagePayloadMarker

        param = MessageParameterInfo(
            name="msg",
            annotation=self.ChatMessage,
            actual_type=self.ChatMessage,
            marker=MessagePayloadMarker(),
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context(body='{"text": "hello", "sender": "john"}')

        result = await resolver.resolve(param, ctx)
        assert isinstance(result, self.ChatMessage)
        assert result.text == "hello"
        assert result.sender == "john"


class TestDestinationVariableResolver:
    """DestinationVariableResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return DestinationVariableResolver()

    def test_supports_with_marker(self, resolver):
        """DestinationVariable 마커 지원"""
        from bloom.web.messaging.params import DestinationVariableMarker

        param = MessageParameterInfo(
            name="room",
            annotation=str,
            actual_type=str,
            marker=DestinationVariableMarker(),
            default=None,
            has_default=False,
            is_optional=False,
        )

        assert resolver.supports(param)

    @pytest.mark.asyncio
    async def test_resolve_variable(self, resolver):
        """변수 리졸빙"""
        from bloom.web.messaging.params import DestinationVariableMarker

        param = MessageParameterInfo(
            name="room",
            annotation=str,
            actual_type=str,
            marker=DestinationVariableMarker(),
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context(dest_vars={"room": "general"})

        result = await resolver.resolve(param, ctx)
        assert result == "general"

    @pytest.mark.asyncio
    async def test_resolve_int_variable(self, resolver):
        """정수 변수 리졸빙"""
        from bloom.web.messaging.params import DestinationVariableMarker

        param = MessageParameterInfo(
            name="id",
            annotation=int,
            actual_type=int,
            marker=DestinationVariableMarker(),
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context(dest_vars={"id": "123"})

        result = await resolver.resolve(param, ctx)
        assert result == 123

    @pytest.mark.asyncio
    async def test_resolve_with_custom_name(self, resolver):
        """커스텀 이름 리졸빙"""
        from bloom.web.messaging.params import DestinationVariableMarker

        param = MessageParameterInfo(
            name="room_name",
            annotation=str,
            actual_type=str,
            marker=DestinationVariableMarker(name="room"),
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context(dest_vars={"room": "general"})

        result = await resolver.resolve(param, ctx)
        assert result == "general"

    @pytest.mark.asyncio
    async def test_resolve_missing_with_default(self, resolver):
        """없는 변수 + 기본값"""
        from bloom.web.messaging.params import DestinationVariableMarker

        param = MessageParameterInfo(
            name="room",
            annotation=str,
            actual_type=str,
            marker=DestinationVariableMarker(),
            default="default-room",
            has_default=True,
            is_optional=False,
        )
        ctx = create_context(dest_vars={})

        result = await resolver.resolve(param, ctx)
        assert result == "default-room"


class TestPrincipalResolver:
    """PrincipalResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return PrincipalResolver()

    @pytest.mark.asyncio
    async def test_resolve_principal(self, resolver):
        """Principal 리졸빙"""
        from bloom.web.messaging.params import PrincipalMarker

        param = MessageParameterInfo(
            name="user",
            annotation=str,
            actual_type=str,
            marker=PrincipalMarker(),
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context(principal="user-123")

        result = await resolver.resolve(param, ctx)
        assert result == "user-123"

    @pytest.mark.asyncio
    async def test_resolve_missing_principal_optional(self, resolver):
        """없는 Principal + Optional"""
        from bloom.web.messaging.params import PrincipalMarker

        param = MessageParameterInfo(
            name="user",
            annotation=str,
            actual_type=str,
            marker=PrincipalMarker(),
            default=None,
            has_default=False,
            is_optional=True,
        )
        ctx = create_context(principal=None)

        result = await resolver.resolve(param, ctx)
        assert result is None


class TestSessionIdResolver:
    """SessionIdResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return SessionIdResolver()

    def test_supports_by_name(self, resolver):
        """session_id 이름으로 지원"""
        param = MessageParameterInfo(
            name="session_id",
            annotation=str,
            actual_type=str,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        assert resolver.supports(param)

    @pytest.mark.asyncio
    async def test_resolve(self, resolver):
        """세션 ID 리졸빙"""
        param = MessageParameterInfo(
            name="session_id",
            annotation=str,
            actual_type=str,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context()

        result = await resolver.resolve(param, ctx)
        assert result == "test-session"


class TestWebSocketSessionResolver:
    """WebSocketSessionResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return WebSocketSessionResolver()

    def test_supports_by_type(self, resolver):
        """타입으로 지원"""
        param = MessageParameterInfo(
            name="ws",
            annotation=WebSocketSession,
            actual_type=WebSocketSession,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        assert resolver.supports(param)

    def test_supports_by_name(self, resolver):
        """이름으로 지원"""
        param = MessageParameterInfo(
            name="session",
            annotation=object,
            actual_type=object,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        assert resolver.supports(param)

    @pytest.mark.asyncio
    async def test_resolve(self, resolver):
        """세션 리졸빙"""
        param = MessageParameterInfo(
            name="session",
            annotation=WebSocketSession,
            actual_type=WebSocketSession,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context()

        result = await resolver.resolve(param, ctx)
        assert isinstance(result, WebSocketSession)


class TestMessageContextResolver:
    """MessageContextResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return MessageContextResolver()

    def test_supports_by_type(self, resolver):
        """타입으로 지원"""
        param = MessageParameterInfo(
            name="ctx",
            annotation=MessageContext,
            actual_type=MessageContext,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        assert resolver.supports(param)

    @pytest.mark.asyncio
    async def test_resolve(self, resolver):
        """컨텍스트 리졸빙"""
        param = MessageParameterInfo(
            name="context",
            annotation=MessageContext,
            actual_type=MessageContext,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context()

        result = await resolver.resolve(param, ctx)
        assert result is ctx


class TestImplicitDestinationVariableResolver:
    """ImplicitDestinationVariableResolver 테스트"""

    @pytest.fixture
    def resolver(self):
        return ImplicitDestinationVariableResolver()

    def test_supports_str(self, resolver):
        """str 타입 지원"""
        param = MessageParameterInfo(
            name="room",
            annotation=str,
            actual_type=str,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        assert resolver.supports(param)

    def test_not_supports_complex_type(self, resolver):
        """복잡한 타입 미지원"""
        param = MessageParameterInfo(
            name="data",
            annotation=dict,
            actual_type=dict,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )

        assert not resolver.supports(param)

    @pytest.mark.asyncio
    async def test_resolve_from_dest_vars(self, resolver):
        """destination 변수에서 리졸빙"""
        param = MessageParameterInfo(
            name="room",
            annotation=str,
            actual_type=str,
            marker=None,
            default=None,
            has_default=False,
            is_optional=False,
        )
        ctx = create_context(dest_vars={"room": "general"})

        result = await resolver.resolve(param, ctx)
        assert result == "general"
