"""메시징 파라미터 타입

HTTP routing.params와 동일한 패턴으로 메시징 파라미터를 정의합니다.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import (
    Any,
    TypeVar,
    TYPE_CHECKING,
    Annotated,
    get_origin,
    get_args,
    List,
    Tuple,
)

T = TypeVar("T")


# =============================================================================
# Base Marker Class
# =============================================================================


@dataclass(frozen=True)
class MessageParamMarker:
    """메시지 파라미터 마커 베이스 클래스

    routing.params.ParamMarker와 동일한 패턴입니다.
    """

    name: str | None = None

    def __class_getitem__(cls, item: type):
        """DestinationVariable[str] → Annotated[str, DestinationVariableMarker()] 변환"""
        return Annotated[item, cls()]


# =============================================================================
# Parameter Markers
# =============================================================================


@dataclass(frozen=True)
class DestinationVariableMarker(MessageParamMarker):
    """destination 경로에서 추출하는 변수 마커

    Usage:
        @MessageMapping("/chat/{room}")
        async def handler(room: DestinationVariable[str]): ...

        # 커스텀 이름
        @MessageMapping("/chat/{room_id}")
        async def handler(room: Annotated[str, DestinationVariable(name="room_id")]): ...
    """

    pass


@dataclass(frozen=True)
class MessagePayloadMarker(MessageParamMarker):
    """메시지 본문 마커

    Usage:
        @MessageMapping("/chat/send")
        async def handler(message: MessagePayload[ChatMessage]): ...

        # dict로 받기
        @MessageMapping("/chat/send")
        async def handler(data: MessagePayload[dict]): ...
    """

    pass


@dataclass(frozen=True)
class MessageHeadersMarker(MessageParamMarker):
    """메시지 헤더 마커

    Usage:
        # 전체 헤더
        @MessageMapping("/chat/send")
        async def handler(headers: MessageHeaders[dict[str, str]]): ...

        # 특정 헤더
        @MessageMapping("/chat/send")
        async def handler(
            content_type: Annotated[str, MessageHeaders(name="content-type")]
        ): ...
    """

    pass


@dataclass(frozen=True)
class PrincipalMarker(MessageParamMarker):
    """인증된 사용자 정보 마커

    Usage:
        @MessageMapping("/chat/send")
        async def handler(user: Principal[User]): ...

        @MessageMapping("/chat/send")
        async def handler(user_id: Principal[int]): ...
    """

    pass


@dataclass(frozen=True)
class SessionIdMarker(MessageParamMarker):
    """WebSocket 세션 ID 마커

    Usage:
        @MessageMapping("/chat/send")
        async def handler(session_id: SessionId[str]): ...
    """

    pass


@dataclass(frozen=True)
class WebSocketSessionMarker(MessageParamMarker):
    """WebSocket 세션 객체 마커

    Usage:
        @MessageMapping("/chat/send")
        async def handler(session: WebSocketSession[Any]): ...
    """

    pass


# =============================================================================
# TYPE_CHECKING 분기 (routing.params와 동일한 패턴)
# =============================================================================

if TYPE_CHECKING:
    # 타입 체커용: 실제 타입 alias
    type DestinationVariable[T] = Annotated[T, DestinationVariableMarker]
    type MessagePayload[T] = Annotated[T, MessagePayloadMarker]
    type MessageHeaders[T] = Annotated[T, MessageHeadersMarker]
    type Principal[T] = Annotated[T, PrincipalMarker]
    type SessionId[T] = Annotated[T, SessionIdMarker]
    type WebSocketSession[T] = Annotated[T, WebSocketSessionMarker]
else:
    # 런타임용: 마커 클래스 직접 사용
    DestinationVariable = DestinationVariableMarker
    MessagePayload = MessagePayloadMarker
    MessageHeaders = MessageHeadersMarker
    Principal = PrincipalMarker
    SessionId = SessionIdMarker
    WebSocketSession = WebSocketSessionMarker


# =============================================================================
# Helper Functions
# =============================================================================


def get_message_param_marker(annotation: Any) -> tuple[type, MessageParamMarker | None]:
    """타입 어노테이션에서 메시징 마커 추출

    routing.params.get_param_marker와 동일한 패턴입니다.

    Returns:
        (actual_type, marker) 튜플
        마커가 없으면 (annotation, None)

    Examples:
        >>> get_message_param_marker(DestinationVariable[str])
        (str, DestinationVariableMarker())

        >>> get_message_param_marker(Annotated[dict, MessagePayload()])
        (dict, MessagePayloadMarker())

        >>> get_message_param_marker(str)
        (str, None)
    """
    origin = get_origin(annotation)

    # Annotated[T, ...] 형태인지 확인
    if origin is Annotated:
        args = get_args(annotation)
        if len(args) >= 2:
            actual_type = args[0]
            for arg in args[1:]:
                if isinstance(arg, MessageParamMarker):
                    return (actual_type, arg)
            return (actual_type, None)

    return (annotation, None)


def get_message_param_type(annotation: Any) -> type | None:
    """파라미터 어노테이션에서 실제 타입 추출

    Args:
        annotation: 파라미터 어노테이션

    Returns:
        실제 타입 또는 None
    """
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if args:
            return args[0]
    return annotation if isinstance(annotation, type) else None


# =============================================================================
# Parameter Info (routing.resolver.ParameterInfo와 동일한 패턴)
# =============================================================================


@dataclass
class MessageParameterInfo:
    """메시징 핸들러 파라미터 정보

    routing.resolver.ParameterInfo와 동일한 패턴입니다.
    """

    name: str
    annotation: type
    actual_type: type
    marker: MessageParamMarker | None
    default: Any
    has_default: bool

    @classmethod
    def from_parameter(cls, param: inspect.Parameter) -> "MessageParameterInfo":
        """inspect.Parameter에서 MessageParameterInfo 생성"""
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            annotation = Any

        actual_type, marker = get_message_param_marker(annotation)

        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else None

        # param.default가 MessageParamMarker인 경우
        if isinstance(default, MessageParamMarker):
            marker = default
            has_default = False
            default = None

        return cls(
            name=param.name,
            annotation=annotation,
            actual_type=actual_type,
            marker=marker,
            default=default,
            has_default=has_default,
        )


# =============================================================================
# Parameter Resolver Interface (routing.resolver와 동일한 패턴)
# =============================================================================


class MessageParameterResolver(ABC):
    """메시지 파라미터 리졸버 인터페이스

    routing.resolver.ParameterResolver와 동일한 패턴입니다.
    """

    @abstractmethod
    def supports(self, param: MessageParameterInfo) -> bool:
        """이 리졸버가 해당 파라미터를 처리할 수 있는지 확인"""
        pass

    @abstractmethod
    async def resolve(
        self,
        param: MessageParameterInfo,
        context: Any,
    ) -> Any:
        """파라미터 값을 추출"""
        pass


# =============================================================================
# Built-in Resolvers
# =============================================================================


class DestinationVariableResolver(MessageParameterResolver):
    """DestinationVariable 파라미터 리졸버"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, DestinationVariableMarker)

    async def resolve(self, param: MessageParameterInfo, context: Any) -> Any:
        path_vars = getattr(context, "path_variables", {})
        name = param.marker.name if param.marker and param.marker.name else param.name
        return path_vars.get(name)


class MessagePayloadResolver(MessageParameterResolver):
    """MessagePayload 파라미터 리졸버"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, MessagePayloadMarker)

    async def resolve(self, param: MessageParameterInfo, context: Any) -> Any:
        return getattr(context, "payload", None)


class MessageHeadersResolver(MessageParameterResolver):
    """MessageHeaders 파라미터 리졸버"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, MessageHeadersMarker)

    async def resolve(self, param: MessageParameterInfo, context: Any) -> Any:
        headers = getattr(context, "headers", {})
        if param.marker and param.marker.name:
            return headers.get(param.marker.name)
        return headers


class PrincipalResolver(MessageParameterResolver):
    """Principal 파라미터 리졸버"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, PrincipalMarker)

    async def resolve(self, param: MessageParameterInfo, context: Any) -> Any:
        return getattr(context, "principal", None)


class SessionIdResolver(MessageParameterResolver):
    """SessionId 파라미터 리졸버"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, SessionIdMarker)

    async def resolve(self, param: MessageParameterInfo, context: Any) -> Any:
        return getattr(context, "session_id", None)


class WebSocketSessionResolver(MessageParameterResolver):
    """WebSocketSession 파라미터 리졸버"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, WebSocketSessionMarker)

    async def resolve(self, param: MessageParameterInfo, context: Any) -> Any:
        return getattr(context, "websocket_session", None)


# =============================================================================
# Resolver Registry (routing.resolver.ResolverRegistry와 동일한 패턴)
# =============================================================================


class MessageResolverRegistry:
    """메시지 파라미터 리졸버 레지스트리

    routing.resolver.ResolverRegistry와 동일한 패턴입니다.
    """

    def __init__(self):
        self._resolvers: List[Tuple[int, MessageParameterResolver]] = []
        self._register_default_resolvers()

    def _register_default_resolvers(self):
        """기본 리졸버 등록"""
        self.add_resolver(DestinationVariableResolver(), priority=100)
        self.add_resolver(MessagePayloadResolver(), priority=200)
        self.add_resolver(MessageHeadersResolver(), priority=300)
        self.add_resolver(PrincipalResolver(), priority=400)
        self.add_resolver(SessionIdResolver(), priority=500)
        self.add_resolver(WebSocketSessionResolver(), priority=600)

    def add_resolver(self, resolver: MessageParameterResolver, priority: int = 500):
        """리졸버 추가 (낮은 priority가 우선)"""
        self._resolvers.append((priority, resolver))
        self._resolvers.sort(key=lambda x: x[0])

    def find_resolver(
        self, param: MessageParameterInfo
    ) -> MessageParameterResolver | None:
        """주어진 파라미터를 처리할 수 있는 리졸버 찾기"""
        for _, resolver in self._resolvers:
            if resolver.supports(param):
                return resolver
        return None

    async def resolve(self, param: MessageParameterInfo, context: Any) -> Any:
        """파라미터 값 추출"""
        resolver = self.find_resolver(param)
        if resolver:
            return await resolver.resolve(param, context)
        return param.default


# 전역 레지스트리 인스턴스
_default_resolver_registry = None


def get_message_resolver_registry() -> MessageResolverRegistry:
    """기본 MessageResolverRegistry 인스턴스 반환"""
    global _default_resolver_registry
    if _default_resolver_registry is None:
        _default_resolver_registry = MessageResolverRegistry()
    return _default_resolver_registry
