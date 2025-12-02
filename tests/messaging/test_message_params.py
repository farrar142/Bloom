"""STOMP 메시징 파라미터 리졸버 테스트"""

import pytest
from dataclasses import dataclass
from pydantic import BaseModel

from bloom.web.messaging.params import (
    MessageResolverContext,
    MessageBody,
    get_default_message_registry,
    is_optional,
    unwrap_optional,
)
from bloom.web.messaging.session import Message, WebSocketSession
from bloom.web.messaging.auth import StompAuthentication


# ============================================================================
# 테스트용 모델들
# ============================================================================


class ChatMessage(BaseModel):
    """Pydantic 모델"""

    text: str
    sender: str = "anonymous"


class UserInfo(BaseModel):
    """중첩 Pydantic 모델"""

    name: str
    age: int


@dataclass
class ChatMessageDC:
    """dataclass 모델"""

    text: str
    sender: str = "anonymous"


@dataclass
class UserInfoDC:
    """중첩 dataclass 모델"""

    name: str
    age: int


# ============================================================================
# 헬퍼 함수 테스트
# ============================================================================


class TestOptionalHelpers:
    """is_optional, unwrap_optional 테스트"""

    async def test_is_optional_with_union(self):
        """T | None 형태"""
        assert is_optional(str | None) is True
        assert is_optional(ChatMessage | None) is True
        assert is_optional(list[ChatMessage] | None) is True

    async def test_is_optional_plain_type(self):
        """일반 타입"""
        assert is_optional(str) is False
        assert is_optional(ChatMessage) is False
        assert is_optional(list[ChatMessage]) is False

    async def test_unwrap_optional(self):
        """Optional에서 내부 타입 추출"""
        assert unwrap_optional(str | None) is str
        assert unwrap_optional(ChatMessage | None) is ChatMessage

    async def test_unwrap_optional_non_optional(self):
        """Optional이 아닌 경우 그대로 반환"""
        assert unwrap_optional(str) is str
        assert unwrap_optional(ChatMessage) is ChatMessage


# ============================================================================
# MessageBody 리졸버 테스트
# ============================================================================


class TestMessageBodyResolver:
    """MessageBody[T] 리졸버 테스트"""

    @pytest.fixture
    def registry(self):
        return get_default_message_registry()

    @pytest.fixture
    def session(self):
        return WebSocketSession(path="/ws")

    @pytest.mark.asyncio
    async def test_message_body_pydantic(self, registry, session):
        """MessageBody[BaseModel]"""
        message = Message(
            destination="/test",
            payload={"text": "hello", "sender": "alice"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        # 타입 힌트 시뮬레이션
        param_type = MessageBody[ChatMessage]

        resolved = await registry.resolve_parameters(
            handler_id=1,
            type_hints={"data": param_type},
            context=context,
        )

        assert "data" in resolved
        assert isinstance(resolved["data"], ChatMessage)
        assert resolved["data"].text == "hello"
        assert resolved["data"].sender == "alice"

    @pytest.mark.asyncio
    async def test_message_body_dataclass(self, registry, session):
        """MessageBody[dataclass]"""
        message = Message(
            destination="/test",
            payload={"text": "hello", "sender": "bob"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        param_type = MessageBody[ChatMessageDC]

        resolved = await registry.resolve_parameters(
            handler_id=2,
            type_hints={"data": param_type},
            context=context,
        )

        assert "data" in resolved
        assert isinstance(resolved["data"], ChatMessageDC)
        assert resolved["data"].text == "hello"
        assert resolved["data"].sender == "bob"

    @pytest.mark.asyncio
    async def test_message_body_optional_with_payload(self, registry, session):
        """MessageBody[T] | None (payload 있음)"""
        message = Message(
            destination="/test",
            payload={"text": "hello"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        param_type = MessageBody[ChatMessage] | None

        resolved = await registry.resolve_parameters(
            handler_id=3,
            type_hints={"data": param_type},
            context=context,
        )

        assert "data" in resolved
        assert isinstance(resolved["data"], ChatMessage)
        assert resolved["data"].text == "hello"

    @pytest.mark.asyncio
    async def test_message_body_optional_without_payload(self, registry, session):
        """MessageBody[T] | None (payload 없음)"""
        message = Message(destination="/test", payload=None)
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        param_type = MessageBody[ChatMessage] | None

        resolved = await registry.resolve_parameters(
            handler_id=4,
            type_hints={"data": param_type},
            context=context,
        )

        assert "data" in resolved
        assert resolved["data"] is None


# ============================================================================
# list[T] 리졸버 테스트
# ============================================================================


class TestListPayloadResolver:
    """list[T] 리졸버 테스트"""

    @pytest.fixture
    def registry(self):
        return get_default_message_registry()

    @pytest.fixture
    def session(self):
        return WebSocketSession(path="/ws")

    @pytest.mark.asyncio
    async def test_list_pydantic(self, registry, session):
        """list[BaseModel]"""
        message = Message(
            destination="/test",
            payload=[
                {"text": "hello", "sender": "alice"},
                {"text": "world", "sender": "bob"},
            ],
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=10,
            type_hints={"items": list[ChatMessage]},
            context=context,
        )

        assert "items" in resolved
        assert isinstance(resolved["items"], list)
        assert len(resolved["items"]) == 2
        assert isinstance(resolved["items"][0], ChatMessage)
        assert resolved["items"][0].text == "hello"
        assert resolved["items"][1].text == "world"

    @pytest.mark.asyncio
    async def test_list_dataclass(self, registry, session):
        """list[dataclass]"""
        message = Message(
            destination="/test",
            payload=[
                {"text": "hello", "sender": "alice"},
                {"text": "world", "sender": "bob"},
            ],
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=11,
            type_hints={"items": list[ChatMessageDC]},
            context=context,
        )

        assert "items" in resolved
        assert isinstance(resolved["items"], list)
        assert len(resolved["items"]) == 2
        assert isinstance(resolved["items"][0], ChatMessageDC)
        assert resolved["items"][0].text == "hello"

    @pytest.mark.asyncio
    async def test_list_dict(self, registry, session):
        """list[dict]"""
        message = Message(
            destination="/test",
            payload=[{"a": 1}, {"b": 2}],
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=12,
            type_hints={"items": list[dict]},
            context=context,
        )

        assert "items" in resolved
        assert len(resolved["items"]) == 2
        assert resolved["items"][0] == {"a": 1}

    @pytest.mark.asyncio
    async def test_list_optional_with_payload(self, registry, session):
        """list[T] | None (payload 있음)"""
        message = Message(
            destination="/test",
            payload=[{"text": "hello"}],
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=13,
            type_hints={"items": list[ChatMessage] | None},
            context=context,
        )

        assert "items" in resolved
        assert isinstance(resolved["items"], list)
        assert len(resolved["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_optional_without_payload(self, registry, session):
        """list[T] | None (payload 없음)"""
        message = Message(destination="/test", payload=None)
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=14,
            type_hints={"items": list[ChatMessage] | None},
            context=context,
        )

        assert "items" in resolved
        assert resolved["items"] is None


# ============================================================================
# Optional 리졸버 테스트
# ============================================================================


class TestOptionalPayloadResolver:
    """Optional[T] (T | None) 리졸버 테스트"""

    @pytest.fixture
    def registry(self):
        return get_default_message_registry()

    @pytest.fixture
    def session(self):
        return WebSocketSession(path="/ws")

    @pytest.mark.asyncio
    async def test_optional_pydantic_with_payload(self, registry, session):
        """BaseModel | None (payload 있음)"""
        message = Message(
            destination="/test",
            payload={"text": "hello"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=20,
            type_hints={"data": ChatMessage | None},
            context=context,
        )

        assert "data" in resolved
        assert isinstance(resolved["data"], ChatMessage)
        assert resolved["data"].text == "hello"

    @pytest.mark.asyncio
    async def test_optional_pydantic_without_payload(self, registry, session):
        """BaseModel | None (payload 없음)"""
        message = Message(destination="/test", payload=None)
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=21,
            type_hints={"data": ChatMessage | None},
            context=context,
        )

        assert "data" in resolved
        assert resolved["data"] is None

    @pytest.mark.asyncio
    async def test_optional_dataclass_with_payload(self, registry, session):
        """dataclass | None (payload 있음)"""
        message = Message(
            destination="/test",
            payload={"text": "hello", "sender": "alice"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=22,
            type_hints={"data": ChatMessageDC | None},
            context=context,
        )

        assert "data" in resolved
        assert isinstance(resolved["data"], ChatMessageDC)
        assert resolved["data"].text == "hello"

    @pytest.mark.asyncio
    async def test_optional_dataclass_without_payload(self, registry, session):
        """dataclass | None (payload 없음)"""
        message = Message(destination="/test", payload=None)
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=23,
            type_hints={"data": ChatMessageDC | None},
            context=context,
        )

        assert "data" in resolved
        assert resolved["data"] is None

    @pytest.mark.asyncio
    async def test_optional_dict_with_payload(self, registry, session):
        """dict | None (payload 있음)"""
        message = Message(
            destination="/test",
            payload={"key": "value"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=24,
            type_hints={"data": dict | None},
            context=context,
        )

        assert "data" in resolved
        assert resolved["data"] == {"key": "value"}


# ============================================================================
# 일반 Payload 리졸버 테스트 (기존)
# ============================================================================


class TestPayloadResolver:
    """PayloadResolver 테스트 (마커 없이 직접 타입 지정)"""

    @pytest.fixture
    def registry(self):
        return get_default_message_registry()

    @pytest.fixture
    def session(self):
        return WebSocketSession(path="/ws")

    @pytest.mark.asyncio
    async def test_pydantic_model(self, registry, session):
        """BaseModel 직접 지정"""
        message = Message(
            destination="/test",
            payload={"text": "hello"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=30,
            type_hints={"data": ChatMessage},
            context=context,
        )

        assert "data" in resolved
        assert isinstance(resolved["data"], ChatMessage)

    @pytest.mark.asyncio
    async def test_dataclass(self, registry, session):
        """dataclass 직접 지정"""
        message = Message(
            destination="/test",
            payload={"text": "hello"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=31,
            type_hints={"data": ChatMessageDC},
            context=context,
        )

        assert "data" in resolved
        assert isinstance(resolved["data"], ChatMessageDC)

    @pytest.mark.asyncio
    async def test_dict(self, registry, session):
        """dict 직접 지정"""
        message = Message(
            destination="/test",
            payload={"key": "value"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=32,
            type_hints={"data": dict},
            context=context,
        )

        assert "data" in resolved
        assert resolved["data"] == {"key": "value"}


# ============================================================================
# 복합 시나리오 테스트
# ============================================================================


class TestComplexScenarios:
    """여러 파라미터가 함께 사용되는 시나리오"""

    @pytest.fixture
    def registry(self):
        return get_default_message_registry()

    @pytest.fixture
    def session(self):
        session = WebSocketSession(path="/ws")
        session.authentication = StompAuthentication(
            user_id="alice", authenticated=True
        )
        return session

    @pytest.mark.asyncio
    async def test_multiple_params(self, registry, session):
        """여러 타입의 파라미터 동시 사용"""
        message = Message(
            destination="/test",
            payload={"text": "hello"},
        )
        context = MessageResolverContext(
            session=session,
            message=message,
            path_params={"room_id": "123"},
        )

        resolved = await registry.resolve_parameters(
            handler_id=40,
            type_hints={
                "auth": StompAuthentication,
                "room_id": str,
                "data": ChatMessage,
            },
            context=context,
        )

        assert "auth" in resolved
        assert resolved["auth"].user_id == "alice"

        assert "room_id" in resolved
        assert resolved["room_id"] == "123"

        assert "data" in resolved
        assert isinstance(resolved["data"], ChatMessage)
        assert resolved["data"].text == "hello"

    @pytest.mark.asyncio
    async def test_message_body_with_auth(self, registry, session):
        """MessageBody[T]와 StompAuthentication 함께 사용"""
        message = Message(
            destination="/test",
            payload={"text": "hello"},
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        resolved = await registry.resolve_parameters(
            handler_id=41,
            type_hints={
                "auth": StompAuthentication,
                "data": MessageBody[ChatMessage],
            },
            context=context,
        )

        assert "auth" in resolved
        assert resolved["auth"].user_id == "alice"

        assert "data" in resolved
        assert isinstance(resolved["data"], ChatMessage)

    @pytest.mark.asyncio
    async def test_list_with_optional(self, registry, session):
        """list[T]와 T | None 함께 사용"""
        message = Message(
            destination="/test",
            payload=[{"text": "hello"}],
        )
        context = MessageResolverContext(
            session=session, message=message, path_params={}
        )

        # list[ChatMessage]는 items에 매핑
        # ChatMessage | None은 UNRESOLVED (payload가 list이므로)
        resolved = await registry.resolve_parameters(
            handler_id=42,
            type_hints={
                "items": list[ChatMessage],
            },
            context=context,
        )

        assert "items" in resolved
        assert len(resolved["items"]) == 1
        assert resolved["items"][0].text == "hello"
