"""STOMP 메시징 파라미터 리졸버 패키지"""

from .base import (
    MessageParameterResolver,
    is_optional,
    unwrap_optional,
)

# MessageResolverContext는 공통 context 모듈에서 import
from bloom.web.params.context import MessageResolverContext

# 공용 리졸버 import (Authentication, PathParam)
from bloom.web.params.resolvers import AuthenticationResolver, PathParamResolver

from .registry import (
    UNRESOLVED,
    MessageParameterResolverRegistry,
    get_default_message_registry,
)
from .resolvers import (
    MessageResolver,
    PayloadResolver,
    WebSocketSessionResolver,
    MessageBodyResolver,
    ListPayloadResolver,
    OptionalPayloadResolver,
)
from .types import MessageBody, MessageBodyType

# 기본 리졸버들 등록 (순서 중요: 더 구체적인 리졸버가 먼저)
_registry = get_default_message_registry()
_registry.register(AuthenticationResolver())  # Authentication (공용)
_registry.register(MessageResolver())  # Message
_registry.register(WebSocketSessionResolver())  # WebSocketSession
_registry.register(MessageBodyResolver())  # MessageBody[T]
_registry.register(ListPayloadResolver())  # list[T]
_registry.register(OptionalPayloadResolver())  # T | None (BaseModel, dataclass)
_registry.register(PathParamResolver())  # path params (공용)
_registry.register(PayloadResolver())  # payload (Pydantic/dataclass/dict) - 가장 마지막

__all__ = [
    # Base
    "MessageParameterResolver",
    "MessageResolverContext",
    "is_optional",
    "unwrap_optional",
    # Registry
    "UNRESOLVED",
    "MessageParameterResolverRegistry",
    "get_default_message_registry",
    # Types
    "MessageBody",
    "MessageBodyType",
    # Resolvers
    "AuthenticationResolver",
    "MessageResolver",
    "PayloadResolver",
    "PathParamResolver",
    "WebSocketSessionResolver",
    "MessageBodyResolver",
    "ListPayloadResolver",
    "OptionalPayloadResolver",
]
