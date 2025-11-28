"""bloom.web.messaging 패키지 - STOMP 기반 WebSocket 메시징"""

from .message import Message, StompFrame, StompCommand
from .broker import SimpleBroker, Subscription
from .decorators import (
    MessageMapping,
    SendTo,
    SendToUser,
    SubscribeMapping,
    MessageExceptionHandler,
    # Element classes
    MessageMappingElement,
    SendToElement,
    SendToUserElement,
    SubscribeMappingElement,
    MessageExceptionElement,
)
from .controller import (
    MessageController,
    MessageControllerElement,
    is_message_controller,
    get_prefix,
)
from .template import SimpMessagingTemplate
from .session import WebSocketSession, WebSocketDisconnect, WebSocketSessionManager
from .handler import StompProtocolHandler

__all__ = [
    # 메시지 모델
    "Message",
    "StompFrame",
    "StompCommand",
    # 브로커
    "SimpleBroker",
    "Subscription",
    # 데코레이터 (개발자용)
    "MessageMapping",
    "SendTo",
    "SendToUser",
    "SubscribeMapping",
    "MessageExceptionHandler",
    # Element 클래스 (내부/고급 사용)
    "MessageMappingElement",
    "SendToElement",
    "SendToUserElement",
    "SubscribeMappingElement",
    "MessageExceptionElement",
    # 컨트롤러 (개발자용)
    "MessageController",
    "MessageControllerElement",
    "is_message_controller",
    "get_prefix",
    # 템플릿 (개발자용)
    "SimpMessagingTemplate",
    # 세션 (내부/고급 사용)
    "WebSocketSession",
    "WebSocketDisconnect",
    "WebSocketSessionManager",
    # 핸들러 (내부 사용)
    "StompProtocolHandler",
]
