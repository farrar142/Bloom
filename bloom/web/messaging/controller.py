"""메시지 컨트롤러"""

from typing import Any

from bloom.core.container import ComponentContainer
from bloom.core.container.element import Element


class MessageControllerElement(Element):
    """MessageController 메타데이터 Element"""

    key = "message_controller"

    def __init__(self, prefix: str = ""):
        self.prefix = prefix

    @property
    def value(self) -> str:
        return self.prefix


def MessageController(cls_or_prefix: type | str = ""):
    """
    메시지 핸들러 컨트롤러

    Spring의 @Controller + @MessageMapping을 하나로 합친 데코레이터.
    WebSocket/STOMP 세부사항을 숨기고 메시지 처리 로직에만 집중.

    사용 예시:
        @MessageController
        class ChatController:
            @MessageMapping("/chat.send")
            @SendTo("/topic/messages")
            def send_message(self, msg: ChatMessage) -> ChatMessage:
                return msg

        @MessageController("/v1")
        class ChatV1Controller:
            @MessageMapping("/chat.send")  # 실제: /v1/chat.send
            def send_message(self, msg: ChatMessage) -> ChatMessage:
                return msg

    prefix를 지정하면 모든 @MessageMapping 목적지에 prefix가 추가됨.
    """
    # @MessageController 형태 (인자 없이 사용)
    if isinstance(cls_or_prefix, type):
        cls = cls_or_prefix
        return _apply_message_controller(cls, "")

    # @MessageController("/v1") 형태 (prefix 지정)
    prefix = cls_or_prefix

    def decorator(cls: type) -> type:
        return _apply_message_controller(cls, prefix)

    return decorator


def _apply_message_controller(cls: type, prefix: str) -> type:
    """MessageController 데코레이터 적용"""
    # @Component로 등록
    container = ComponentContainer.get_or_create(cls)
    container.add_elements(MessageControllerElement(prefix))

    # 클래스에 메타데이터 저장
    setattr(
        cls,
        "_message_controller_meta",
        {
            "prefix": prefix,
        },
    )

    return cls


def is_message_controller(cls: type) -> bool:
    """주어진 클래스가 MessageController인지 확인"""
    return hasattr(cls, "_message_controller_meta")


def get_prefix(cls: type) -> str:
    """MessageController의 prefix 반환"""
    meta = getattr(cls, "_message_controller_meta", {})
    return meta.get("prefix", "")
