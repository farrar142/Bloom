"""STOMP 메시징 기본 파라미터 리졸버들

WebSocket/STOMP 전용 리졸버만 포함합니다.
PathParamResolver, AuthenticationResolver 등은 web/params에서 공유합니다.
"""

from typing import Any, Annotated, get_origin, get_args

from bloom.web.params.context import MessageResolverContext

from ..session import Message, WebSocketSession
from .base import (
    MessageParameterResolver,
    is_optional,
    unwrap_optional,
)
from .registry import UNRESOLVED
from .types import MessageBodyType


class MessageResolver(MessageParameterResolver):
    """
    Message 객체를 주입하는 리졸버

    컨텍스트의 message를 그대로 반환합니다.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        return param_type is Message

    async def resolve_message(
        self,
        param_name: str,
        param_type: type,
        context: MessageResolverContext,
    ) -> Any:
        return context.stomp_message


class WebSocketSessionResolver(MessageParameterResolver):
    """
    WebSocketSession 객체를 주입하는 리졸버

    컨텍스트의 session을 그대로 반환합니다.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        return param_type is WebSocketSession

    async def resolve_message(
        self,
        param_name: str,
        param_type: type,
        context: MessageResolverContext,
    ) -> Any:
        return context.session


class PayloadResolver(MessageParameterResolver):
    """
    메시지 페이로드를 주입하는 리졸버

    Message의 payload를 적절한 타입으로 변환하여 주입합니다.
    - Pydantic BaseModel: model_validate() 사용
    - dataclass: **kwargs 언패킹
    - dict: 그대로 반환
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # dict, Pydantic 모델, dataclass 등
        if param_type is dict:
            return True
        # list[dict] 등 제네릭 dict
        if origin is dict or origin is list:
            return True
        # Pydantic 모델
        if hasattr(param_type, "model_validate"):
            return True
        # dataclass
        if hasattr(param_type, "__dataclass_fields__"):
            return True
        return False

    async def resolve_message(
        self,
        param_name: str,
        param_type: type,
        context: MessageResolverContext,
    ) -> Any:
        message = context.stomp_message
        if message is None or message.payload is None:
            return UNRESOLVED

        payload = message.payload

        # Pydantic 모델
        if hasattr(param_type, "model_validate"):
            return param_type.model_validate(payload)  # type: ignore

        # dataclass
        if hasattr(param_type, "__dataclass_fields__"):
            if isinstance(payload, dict):
                return param_type(**payload)  # type: ignore
            return payload

        # dict나 기타
        return payload


class MessageBodyResolver(MessageParameterResolver):
    """
    MessageBody[T] 마커 타입을 처리하는 리졸버

    Message의 payload를 지정된 타입으로 변환합니다.
    Optional[MessageBody[T]]도 지원합니다.

    사용법:
        @MessageMapping("/chat")
        def handle(self, data: MessageBody[ChatMessage]) -> dict:
            return {"text": data.text}

        @MessageMapping("/optional")
        def handle_optional(self, data: MessageBody[ChatMessage] | None) -> dict:
            ...
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # Optional 처리
        if is_optional(param_type):
            param_type = unwrap_optional(param_type)
            origin = get_origin(param_type)

        # Annotated[MessageBodyType, T] 형태 확인
        if origin is Annotated:
            args = get_args(param_type)
            if args and args[0] is MessageBodyType:
                return True
        return False

    async def resolve_message(
        self,
        param_name: str,
        param_type: type,
        context: MessageResolverContext,
    ) -> Any:
        original_type = param_type
        optional = is_optional(param_type)

        if optional:
            param_type = unwrap_optional(param_type)

        # Annotated에서 실제 타입 추출
        origin = get_origin(param_type)
        if origin is Annotated:
            args = get_args(param_type)
            if len(args) >= 2:
                # args[1]이 실제 타입 (예: ChatMessage)
                inner_type = args[1]
            else:
                return UNRESOLVED
        else:
            return UNRESOLVED

        message = context.stomp_message
        if message is None or message.payload is None:
            return None if optional else UNRESOLVED

        payload = message.payload
        return self._convert_payload(payload, inner_type)

    def _convert_payload(self, payload: Any, target_type: type) -> Any:
        """페이로드를 타겟 타입으로 변환"""
        # Pydantic 모델
        if hasattr(target_type, "model_validate"):
            return target_type.model_validate(payload)  # type: ignore

        # dataclass
        if hasattr(target_type, "__dataclass_fields__"):
            if isinstance(payload, dict):
                return target_type(**payload)  # type: ignore
            return payload

        # 기본
        return payload


class ListPayloadResolver(MessageParameterResolver):
    """
    list[T] 형태의 페이로드를 처리하는 리졸버

    list[BaseModel], list[dataclass], list[dict] 등을 지원합니다.
    Optional[list[T]]도 지원합니다.

    사용법:
        @MessageMapping("/batch")
        def handle_batch(self, items: list[ChatMessage]) -> dict:
            return {"count": len(items)}

        @MessageMapping("/optional-batch")
        def handle_optional(self, items: list[ChatMessage] | None) -> dict:
            ...
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # Optional 처리
        if is_optional(param_type):
            param_type = unwrap_optional(param_type)
            origin = get_origin(param_type)

        return origin is list

    async def resolve_message(
        self,
        param_name: str,
        param_type: type,
        context: MessageResolverContext,
    ) -> Any:
        optional = is_optional(param_type)

        if optional:
            param_type = unwrap_optional(param_type)

        origin = get_origin(param_type)
        if origin is not list:
            return UNRESOLVED

        # list[T]에서 T 추출
        args = get_args(param_type)
        message = context.stomp_message

        if not args:
            # list (제네릭 없음) - 그대로 반환
            if message is None or message.payload is None:
                return None if optional else UNRESOLVED
            return message.payload

        item_type = args[0]

        if message is None or message.payload is None:
            return None if optional else UNRESOLVED

        payload = message.payload

        if not isinstance(payload, list):
            return UNRESOLVED

        # 각 아이템 변환
        result = []
        for item in payload:
            converted = self._convert_item(item, item_type)
            result.append(converted)
        return result

    def _convert_item(self, item: Any, target_type: type) -> Any:
        """개별 아이템을 타겟 타입으로 변환"""
        # Pydantic 모델
        if hasattr(target_type, "model_validate"):
            return target_type.model_validate(item)  # type: ignore

        # dataclass
        if hasattr(target_type, "__dataclass_fields__"):
            if isinstance(item, dict):
                return target_type(**item)  # type: ignore
            return item

        # dict나 기본 타입
        return item


class OptionalPayloadResolver(MessageParameterResolver):
    """
    Optional[T] 형태의 페이로드를 처리하는 리졸버

    Optional[BaseModel], Optional[dataclass], T | None 등을 지원합니다.
    payload가 None이면 None을 반환합니다.

    사용법:
        @MessageMapping("/optional")
        def handle(self, data: ChatMessage | None) -> dict:
            if data is None:
                return {"error": "no data"}
            return {"text": data.text}
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        if not is_optional(param_type):
            return False

        inner_type = unwrap_optional(param_type)

        # Pydantic 모델
        if hasattr(inner_type, "model_validate"):
            return True
        # dataclass
        if hasattr(inner_type, "__dataclass_fields__"):
            return True
        # dict
        if inner_type is dict:
            return True

        return False

    async def resolve_message(
        self,
        param_name: str,
        param_type: type,
        context: MessageResolverContext,
    ) -> Any:
        inner_type = unwrap_optional(param_type)
        message = context.stomp_message

        if message is None or message.payload is None:
            return None

        payload = message.payload

        # Pydantic 모델
        if hasattr(inner_type, "model_validate"):
            return inner_type.model_validate(payload)  # type: ignore

        # dataclass
        if hasattr(inner_type, "__dataclass_fields__"):
            if isinstance(payload, dict):
                return inner_type(**payload)  # type: ignore
            return payload

        # dict
        return payload
