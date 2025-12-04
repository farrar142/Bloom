"""메시징 파라미터 타입

HTTP ParameterResolver와 동일한 패턴으로 메시징 파라미터를 정의합니다.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, TYPE_CHECKING, Annotated, get_origin, get_args, List, Tuple

T = TypeVar("T")


# =============================================================================
# Base Marker Class
# =============================================================================


class MessageParamMarker(ABC):
    """메시지 파라미터 마커 기본 클래스"""
    pass


# =============================================================================
# Parameter Markers (런타임 마커)
# =============================================================================


@dataclass(frozen=True)
class DestinationVariableMarker(MessageParamMarker):
    """destination 경로에서 추출하는 변수 마커

    Examples:
        /chat/{room} 에서 {room} 추출
    """

    name: str | None = None


@dataclass(frozen=True)
class MessagePayloadMarker(MessageParamMarker):
    """메시지 본문 마커"""

    pass


@dataclass(frozen=True)
class MessageHeadersMarker(MessageParamMarker):
    """메시지 헤더 마커"""

    name: str | None = None  # None이면 전체 헤더


@dataclass(frozen=True)
class PrincipalMarker(MessageParamMarker):
    """인증된 사용자 정보 마커"""

    pass


@dataclass(frozen=True)
class SessionIdMarker(MessageParamMarker):
    """WebSocket 세션 ID 마커"""

    pass


@dataclass(frozen=True)
class WebSocketSessionMarker(MessageParamMarker):
    """WebSocket 세션 객체 마커"""

    pass


# =============================================================================
# Type Hint Classes (사용자 API)
# =============================================================================


class _DestinationVariable(Generic[T]):
    """destination 경로에서 추출하는 변수

    Usage:
        @MessageMapping("/chat/{room}")
        async def handler(room: DestinationVariable[str]): ...
    """

    def __class_getitem__(cls, item: type) -> Any:
        return Annotated[item, DestinationVariableMarker()]


class _MessagePayload(Generic[T]):
    """메시지 본문

    Usage:
        @MessageMapping("/chat/send")
        async def handler(message: MessagePayload[ChatMessage]): ...
    """

    def __class_getitem__(cls, item: type) -> Any:
        return Annotated[item, MessagePayloadMarker()]


class _MessageHeaders(Generic[T]):
    """메시지 헤더

    Usage:
        @MessageMapping("/chat/send")
        async def handler(headers: MessageHeaders[dict[str, str]]): ...
    """

    def __class_getitem__(cls, item: type) -> Any:
        return Annotated[item, MessageHeadersMarker()]


class _Principal(Generic[T]):
    """인증된 사용자 정보

    Usage:
        @MessageMapping("/chat/send")
        async def handler(user: Principal[User]): ...
    """

    def __class_getitem__(cls, item: type) -> Any:
        return Annotated[item, PrincipalMarker()]


class _SessionId:
    """WebSocket 세션 ID

    Usage:
        @MessageMapping("/chat/send")
        async def handler(session_id: SessionId): ...
    """

    pass


class _WebSocketSession:
    """WebSocket 세션 객체

    Usage:
        @MessageMapping("/chat/send")
        async def handler(session: WebSocketSession): ...
    """

    pass


# =============================================================================
# TYPE_CHECKING 분기
# =============================================================================

if TYPE_CHECKING:
    # 타입 체커용: 실제 타입 alias
    type DestinationVariable[T] = Annotated[T, DestinationVariableMarker]
    type MessagePayload[T] = Annotated[T, MessagePayloadMarker]
    type MessageHeaders[T] = Annotated[T, MessageHeadersMarker]
    type Principal[T] = Annotated[T, PrincipalMarker]
    type SessionId = Annotated[str, SessionIdMarker]
    type WebSocketSession = Annotated[Any, WebSocketSessionMarker]
else:
    # 런타임용: 클래스
    DestinationVariable = _DestinationVariable
    MessagePayload = _MessagePayload
    MessageHeaders = _MessageHeaders
    Principal = _Principal
    SessionId = _SessionId
    WebSocketSession = _WebSocketSession


# =============================================================================
# Parameter Factory Functions (FastAPI-style default value markers)
# =============================================================================


def Destination(name: str | None = None) -> Any:
    """Destination path variable marker (default value style)
    
    Usage:
        @MessageMapping("/chat/{room}")
        async def handler(room_id: str = Destination()): ...
    """
    return DestinationVariableMarker(name=name)


def Payload() -> Any:
    """Message payload marker (default value style)
    
    Usage:
        @MessageMapping("/chat/send")
        async def handler(data: dict = Payload()): ...
    """
    return MessagePayloadMarker()


def Headers(name: str | None = None) -> Any:
    """Message headers marker (default value style)
    
    Usage:
        @MessageMapping("/chat/send")
        async def handler(headers: dict = Headers()): ...
    """
    return MessageHeadersMarker(name=name)


def PrincipalParam() -> Any:
    """Principal marker (default value style)
    
    Usage:
        @MessageMapping("/chat/send")
        async def handler(user: Any = PrincipalParam()): ...
    """
    return PrincipalMarker()


def SessionIdParam() -> Any:
    """Session ID marker (default value style)
    
    Usage:
        @MessageMapping("/chat/send")
        async def handler(session_id: str = SessionIdParam()): ...
    """
    return SessionIdMarker()


def WebSocketSessionParam() -> Any:
    """WebSocket session marker (default value style)
    
    Usage:
        @MessageMapping("/chat/send")
        async def handler(ws: Any = WebSocketSessionParam()): ...
    """
    return WebSocketSessionMarker()


# =============================================================================
# Marker Extractor Registry
# =============================================================================


class MessageParamMarkerExtractor(ABC):
    """메시지 파라미터 마커 추출기 추상 클래스"""

    @abstractmethod
    def supports(self, param: inspect.Parameter) -> bool:
        """주어진 파라미터를 처리할 수 있는지 확인"""
        pass

    @abstractmethod
    def extract(self, param: inspect.Parameter) -> MessageParamMarker:
        """파라미터에서 마커 추출"""
        pass


class DestinationVariableExtractor(MessageParamMarkerExtractor):
    """DestinationVariable 마커 추출기"""

    def supports(self, param: inspect.Parameter) -> bool:
        # default value로 마커 사용
        if isinstance(param.default, DestinationVariableMarker):
            return True
        # Annotated로 마커 사용
        marker = get_message_param_marker(param.annotation)
        return isinstance(marker, DestinationVariableMarker)

    def extract(self, param: inspect.Parameter) -> MessageParamMarker:
        if isinstance(param.default, DestinationVariableMarker):
            return param.default
        marker = get_message_param_marker(param.annotation)
        if marker:
            return marker
        return DestinationVariableMarker(name=param.name)


class MessagePayloadExtractor(MessageParamMarkerExtractor):
    """MessagePayload 마커 추출기"""

    def supports(self, param: inspect.Parameter) -> bool:
        if isinstance(param.default, MessagePayloadMarker):
            return True
        marker = get_message_param_marker(param.annotation)
        return isinstance(marker, MessagePayloadMarker)

    def extract(self, param: inspect.Parameter) -> MessageParamMarker:
        if isinstance(param.default, MessagePayloadMarker):
            return param.default
        marker = get_message_param_marker(param.annotation)
        if marker:
            return marker
        return MessagePayloadMarker()


class MessageHeadersExtractor(MessageParamMarkerExtractor):
    """MessageHeaders 마커 추출기"""

    def supports(self, param: inspect.Parameter) -> bool:
        if isinstance(param.default, MessageHeadersMarker):
            return True
        marker = get_message_param_marker(param.annotation)
        return isinstance(marker, MessageHeadersMarker)

    def extract(self, param: inspect.Parameter) -> MessageParamMarker:
        if isinstance(param.default, MessageHeadersMarker):
            return param.default
        marker = get_message_param_marker(param.annotation)
        if marker:
            return marker
        return MessageHeadersMarker()


class PrincipalExtractor(MessageParamMarkerExtractor):
    """Principal 마커 추출기"""

    def supports(self, param: inspect.Parameter) -> bool:
        if isinstance(param.default, PrincipalMarker):
            return True
        marker = get_message_param_marker(param.annotation)
        return isinstance(marker, PrincipalMarker)

    def extract(self, param: inspect.Parameter) -> MessageParamMarker:
        if isinstance(param.default, PrincipalMarker):
            return param.default
        marker = get_message_param_marker(param.annotation)
        if marker:
            return marker
        return PrincipalMarker()


class SessionIdExtractor(MessageParamMarkerExtractor):
    """SessionId 마커 추출기"""

    def supports(self, param: inspect.Parameter) -> bool:
        if isinstance(param.default, SessionIdMarker):
            return True
        marker = get_message_param_marker(param.annotation)
        return isinstance(marker, SessionIdMarker)

    def extract(self, param: inspect.Parameter) -> MessageParamMarker:
        if isinstance(param.default, SessionIdMarker):
            return param.default
        marker = get_message_param_marker(param.annotation)
        if marker:
            return marker
        return SessionIdMarker()


class WebSocketSessionExtractor(MessageParamMarkerExtractor):
    """WebSocketSession 마커 추출기"""

    def supports(self, param: inspect.Parameter) -> bool:
        if isinstance(param.default, WebSocketSessionMarker):
            return True
        marker = get_message_param_marker(param.annotation)
        return isinstance(marker, WebSocketSessionMarker)

    def extract(self, param: inspect.Parameter) -> MessageParamMarker:
        if isinstance(param.default, WebSocketSessionMarker):
            return param.default
        marker = get_message_param_marker(param.annotation)
        if marker:
            return marker
        return WebSocketSessionMarker()


class MarkerExtractorRegistry:
    """마커 추출기 레지스트리"""

    def __init__(self):
        self._extractors: List[Tuple[int, MessageParamMarkerExtractor]] = []
        self._register_default_extractors()

    def _register_default_extractors(self):
        """기본 추출기 등록"""
        self.add_extractor(DestinationVariableExtractor(), priority=100)
        self.add_extractor(MessagePayloadExtractor(), priority=200)
        self.add_extractor(MessageHeadersExtractor(), priority=300)
        self.add_extractor(PrincipalExtractor(), priority=400)
        self.add_extractor(SessionIdExtractor(), priority=500)
        self.add_extractor(WebSocketSessionExtractor(), priority=600)

    def add_extractor(self, extractor: MessageParamMarkerExtractor, priority: int = 500):
        """추출기 추가 (낮은 priority가 우선)"""
        self._extractors.append((priority, extractor))
        self._extractors.sort(key=lambda x: x[0])

    def find_extractor(self, param: inspect.Parameter) -> MessageParamMarkerExtractor | None:
        """주어진 파라미터를 처리할 수 있는 추출기 찾기"""
        for _, extractor in self._extractors:
            if extractor.supports(param):
                return extractor
        return None

    def extract(self, param: inspect.Parameter) -> MessageParamMarker | None:
        """파라미터에서 마커 추출"""
        extractor = self.find_extractor(param)
        if extractor:
            return extractor.extract(param)
        return None


# 전역 레지스트리 인스턴스
_default_marker_registry = None


def get_marker_extractor_registry() -> MarkerExtractorRegistry:
    """기본 MarkerExtractorRegistry 인스턴스 반환"""
    global _default_marker_registry
    if _default_marker_registry is None:
        _default_marker_registry = MarkerExtractorRegistry()
    return _default_marker_registry


# =============================================================================
# Helper Functions
# =============================================================================


# 마커 타입과 런타임 클래스 매핑 레지스트리
_MARKER_TYPE_REGISTRY: List[Tuple[type, type, type]] = [
    # (마커 인스턴스 타입, 런타임 클래스, 마커 팩토리)
    (DestinationVariableMarker, _DestinationVariable, DestinationVariableMarker),
    (MessagePayloadMarker, _MessagePayload, MessagePayloadMarker),
    (MessageHeadersMarker, _MessageHeaders, MessageHeadersMarker),
    (PrincipalMarker, _Principal, PrincipalMarker),
    (SessionIdMarker, _SessionId, SessionIdMarker),
    (WebSocketSessionMarker, _WebSocketSession, WebSocketSessionMarker),
]


def get_message_param_marker(annotation: Any) -> Any | None:
    """파라미터 어노테이션에서 메시징 마커 추출

    Args:
        annotation: 파라미터 어노테이션

    Returns:
        마커 인스턴스 또는 None
    """
    # Annotated[T, Marker] 형태 확인
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        if len(args) >= 2:
            for arg in args[1:]:
                # 레지스트리를 순회하며 마커 확인
                for marker_type, runtime_class, marker_factory in _MARKER_TYPE_REGISTRY:
                    # 마커 인스턴스 확인
                    if isinstance(arg, marker_type):
                        return arg
                    # 런타임 클래스 자체 사용 지원 (예: Annotated[dict, MessagePayload])
                    if arg is runtime_class or (
                        isinstance(arg, type) and issubclass(arg, runtime_class)
                    ):
                        return marker_factory()
    return None


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
