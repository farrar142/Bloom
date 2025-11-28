"""메시지 핸들러 데코레이터"""

from typing import Callable, Any, TypeVar

from bloom.core.container import Element, HandlerContainer

T = TypeVar("T")


# ============================================================================
# Element 클래스들
# ============================================================================


class MessageMappingElement(Element[T]):
    """메시지 매핑 정보를 담는 Element"""

    def __init__(self, destination: str):
        super().__init__()
        self.metadata["message_mapping"] = destination


class SendToElement(Element[T]):
    """SendTo 목적지 정보를 담는 Element"""

    def __init__(self, destination: str):
        super().__init__()
        self.metadata["send_to"] = destination


class SendToUserElement(Element[T]):
    """SendToUser 목적지 정보를 담는 Element"""

    def __init__(self, destination: str):
        super().__init__()
        self.metadata["send_to_user"] = destination


class SubscribeMappingElement(Element[T]):
    """구독 매핑 정보를 담는 Element"""

    def __init__(self, destination: str):
        super().__init__()
        self.metadata["subscribe_mapping"] = destination


class MessageExceptionElement(Element[T]):
    """메시지 예외 핸들러 정보를 담는 Element"""

    def __init__(self, exception_type: type[Exception]):
        super().__init__()
        self.metadata["message_exception"] = exception_type


# ============================================================================
# 데코레이터 함수들
# ============================================================================


def MessageMapping(destination: str) -> Callable[[Callable], Callable]:
    """
    메시지 수신 핸들러 등록

    Spring의 @MessageMapping과 동일한 역할.
    클라이언트가 /app/{destination}으로 보낸 메시지를 처리.

    사용 예시:
        @MessageController
        class ChatController:
            @MessageMapping("/chat.send")
            def handle_chat(self, message: ChatMessage) -> ChatMessage:
                return message

    클라이언트에서 destination: /app/chat.send 로 SEND 시 호출됨.

    Args:
        destination: 메시지 목적지 패턴 (예: "/chat.send", "/chat.{roomId}")
    """

    def decorator(method: Callable) -> Callable:
        container = HandlerContainer.get_or_create(method)
        container.add_elements(MessageMappingElement(destination))
        return method

    return decorator


def SendTo(destination: str) -> Callable[[Callable], Callable]:
    """
    핸들러 반환값을 특정 목적지로 발행

    Spring의 @SendTo와 동일한 역할.
    핸들러가 반환하는 값을 지정된 목적지의 구독자들에게 브로드캐스트.

    사용 예시:
        @MessageMapping("/chat.send")
        @SendTo("/topic/chat")
        def handle_chat(self, message: ChatMessage) -> ChatMessage:
            return message  # /topic/chat 구독자들에게 전송됨

    동적 목적지도 지원:
        @MessageMapping("/chat.send")
        @SendTo("/topic/chat.{room_id}")  # message.room_id로 치환
        def handle_chat(self, message: ChatMessage) -> ChatMessage:
            return message

    Args:
        destination: 발행 목적지 (예: "/topic/chat", "/topic/chat.{room_id}")
    """

    def decorator(method: Callable) -> Callable:
        container = HandlerContainer.get_or_create(method)
        container.add_elements(SendToElement(destination))
        return method

    return decorator


def SendToUser(destination: str) -> Callable[[Callable], Callable]:
    """
    핸들러 반환값을 특정 사용자에게 전송

    Spring의 @SendToUser와 동일한 역할.
    핸들러가 반환하는 값을 메시지를 보낸 사용자에게만 전송.

    사용 예시:
        @MessageMapping("/chat.private")
        @SendToUser("/queue/private")
        def private_message(self, message: PrivateMessage) -> PrivateMessage:
            return message  # 발신자에게만 전송

    내부적으로 /user/{userId}/queue/private 형식으로 변환됨.

    Args:
        destination: 사용자별 목적지 (예: "/queue/private", "/queue/errors")
    """

    def decorator(method: Callable) -> Callable:
        container = HandlerContainer.get_or_create(method)
        container.add_elements(SendToUserElement(destination))
        return method

    return decorator


def SubscribeMapping(destination: str) -> Callable[[Callable], Callable]:
    """
    구독 시 초기 데이터 전송

    Spring의 @SubscribeMapping과 동일한 역할.
    클라이언트가 특정 목적지를 구독할 때 초기 데이터를 전송.

    사용 예시:
        @MessageController
        class ChatController:
            @SubscribeMapping("/topic/chat.{room_id}")
            def on_subscribe(self, room_id: str) -> list[ChatMessage]:
                return self.get_recent_messages(room_id)

    클라이언트가 /topic/chat.room1을 SUBSCRIBE 시 최근 메시지 반환.

    Args:
        destination: 구독 목적지 패턴
    """

    def decorator(method: Callable) -> Callable:
        container = HandlerContainer.get_or_create(method)
        container.add_elements(SubscribeMappingElement(destination))
        return method

    return decorator


def MessageExceptionHandler(
    exception_type: type[Exception],
) -> Callable[[Callable], Callable]:
    """
    메시지 처리 중 예외 핸들러

    @ErrorHandler와 유사하지만 메시징 컨텍스트에서 동작.

    사용 예시:
        @MessageController
        class ChatController:
            @MessageExceptionHandler(ValueError)
            def handle_value_error(self, error: ValueError) -> ErrorMessage:
                return ErrorMessage(message=str(error))

    Args:
        exception_type: 처리할 예외 타입
    """

    def decorator(method: Callable) -> Callable:
        container = HandlerContainer.get_or_create(method)
        container.add_elements(MessageExceptionElement(exception_type))
        return method

    return decorator
