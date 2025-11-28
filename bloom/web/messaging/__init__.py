"""bloom.web.messaging 패키지 - STOMP 기반 WebSocket 메시징"""

# 메시지 모델
from .session import Message, StompFrame, StompCommand

# 컨트롤러 데코레이터
from .controller import (
    MessageController,
    MessageControllerElement,
    is_message_controller,
    get_prefix,
)

# 핸들러 데코레이터
from .decorators import (
    MessageMapping,
    SendTo,
    SendToUser,
    SubscribeMapping,
    MessageExceptionHandler,
    MessageMappingElement,
    SendToElement,
    SendToUserElement,
    SubscribeMappingElement,
    MessageExceptionElement,
)

# WebSocket 활성화 데코레이터
from .manager import (
    EnableWebSocket,
    EnableWebSocketElement,
    is_websocket_enabled,
    get_websocket_configurer,
    WebSocketManager,
)

# 메시징 템플릿
from .template import SimpMessagingTemplate

# 세션/브로커
from .session import (
    WebSocketSession,
    WebSocketDisconnect,
    WebSocketSessionManager,
    SimpleBroker,
    Subscription,
)

# 프로토콜 핸들러
from .handler import StompProtocolHandler

# Entry 클래스들
from .entry import (
    StompEndpointEntry,
    MessageHandlerEntry,
    SubscribeHandlerEntry,
    MessageExceptionHandlerEntry,
)

# Registry 클래스들
from .registry import (
    StompEndpointRegistry as NewStompEndpointRegistry,
    StompEndpointBuilder,
    MessageHandlerRegistry,
    SubscribeHandlerRegistry,
    MessageExceptionHandlerRegistry,
)
from .registry import MessageBrokerRegistry, MessageBrokerConfig

# 별칭
StompEndpointRegistry = NewStompEndpointRegistry
StompEndpoint = StompEndpointEntry

__all__ = [
    "Message",
    "StompFrame",
    "StompCommand",
    "MessageController",
    "MessageControllerElement",
    "is_message_controller",
    "get_prefix",
    "MessageMapping",
    "SendTo",
    "SendToUser",
    "SubscribeMapping",
    "MessageExceptionHandler",
    "MessageMappingElement",
    "SendToElement",
    "SendToUserElement",
    "SubscribeMappingElement",
    "MessageExceptionElement",
    "EnableWebSocket",
    "EnableWebSocketElement",
    "is_websocket_enabled",
    "get_websocket_configurer",
    "WebSocketManager",
    "SimpMessagingTemplate",
    "WebSocketSession",
    "WebSocketDisconnect",
    "WebSocketSessionManager",
    "SimpleBroker",
    "Subscription",
    "StompProtocolHandler",
    "StompEndpointEntry",
    "MessageHandlerEntry",
    "SubscribeHandlerEntry",
    "MessageExceptionHandlerEntry",
    "NewStompEndpointRegistry",
    "StompEndpointRegistry",
    "StompEndpoint",
    "StompEndpointBuilder",
    "MessageHandlerRegistry",
    "SubscribeHandlerRegistry",
    "MessageExceptionHandlerRegistry",
    "MessageBrokerRegistry",
    "MessageBrokerConfig",
]
