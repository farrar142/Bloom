"""STOMP 메시징 파라미터 마커 타입들"""

from typing import Annotated, TypeVar

T = TypeVar("T")


class MessageBodyType[T]:
    """
    메시지 바디 마커 타입

    STOMP 메시지의 payload를 특정 타입으로 변환하여 주입합니다.

    사용법:
        @MessageMapping("/chat")
        def handle_chat(self, data: MessageBody[ChatMessage]) -> dict:
            # data는 ChatMessage 인스턴스
            return {"text": data.text}

        # Optional과 함께 사용
        @MessageMapping("/optional")
        def handle_optional(self, data: MessageBody[ChatMessage] | None) -> dict:
            if data is None:
                return {"error": "no data"}
            return {"text": data.text}
    """

    def __class_getitem__(cls, item: type[T]):
        """제네릭 타입 지원"""
        return Annotated[cls, item]


# 런타임 alias
MessageBody = MessageBodyType
