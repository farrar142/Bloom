"""bloom.web.messaging - WebSocket + STOMP 메시징 시스템

Spring의 @MessageMapping과 유사한 WebSocket 메시징을 제공합니다.

Usage:
    from bloom.web.messaging import (
        # WebSocket
        WebSocketSession,
        WebSocketHandler,
        WebSocketEndpoint,

        # STOMP
        StompFrame,
        StompCommand,
        StompProtocol,

        # Decorators
        MessageMapping,
        SubscribeMapping,
        SendTo,
        MessageController,

        # Broker
        MessageBroker,
        SimpleBroker,

        # Parameters
        MessagePayload,
        DestinationVariable,
        MessageHeaders,
        Principal,
    )

    @MessageController
    class ChatController:
        @MessageMapping("/chat/{room}")
        @SendTo("/topic/chat/{room}")
        async def handle_message(
            self,
            room: DestinationVariable[str],
            message: MessagePayload[ChatMessage],
            user: Principal[User],
        ) -> ChatResponse:
            return ChatResponse(...)
"""

from .websocket import (
    WebSocketSession,
    WebSocketHandler,
    WebSocketEndpoint,
    WebSocketState,
)
from .stomp import (
    StompFrame,
    StompCommand,
    StompProtocol,
    StompError,
)
from .decorators import (
    MessageMapping,
    SubscribeMapping,
    SendTo,
    MessageController,
)
from .broker import (
    MessageBroker,
    SimpleBroker,
    Subscription,
)
from .params import (
    MessagePayload,
    DestinationVariable,
    MessageHeaders,
    Principal,
    SessionId,
    DestinationVariableMarker,
    MessagePayloadMarker,
    MessageHeadersMarker,
    PrincipalMarker,
    SessionIdMarker,
)
from .handler import (
    StompMessageHandler,
    MessageDispatcher,
)

__all__ = [
    # WebSocket
    "WebSocketSession",
    "WebSocketHandler",
    "WebSocketEndpoint",
    "WebSocketState",
    # STOMP
    "StompFrame",
    "StompCommand",
    "StompProtocol",
    "StompError",
    # Decorators
    "MessageMapping",
    "SubscribeMapping",
    "SendTo",
    "MessageController",
    # Broker
    "MessageBroker",
    "SimpleBroker",
    "Subscription",
    # Parameters
    "MessagePayload",
    "DestinationVariable",
    "MessageHeaders",
    "Principal",
    "SessionId",
    "DestinationVariableMarker",
    "MessagePayloadMarker",
    "MessageHeadersMarker",
    "PrincipalMarker",
    "SessionIdMarker",
    # Handler
    "StompMessageHandler",
    "MessageDispatcher",
]
