"""메시징 파라미터 타입

HTTP ParameterResolver와 동일한 패턴으로 메시징 파라미터를 정의합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar, TYPE_CHECKING, Annotated, get_origin, get_args

T = TypeVar("T")


# =============================================================================
# Parameter Markers (런타임 마커)
# =============================================================================


@dataclass(frozen=True)
class DestinationVariableMarker:
    """destination 경로에서 추출하는 변수 마커

    Examples:
        /chat/{room} 에서 {room} 추출
    """

    name: str | None = None


@dataclass(frozen=True)
class MessagePayloadMarker:
    """메시지 본문 마커"""

    pass


@dataclass(frozen=True)
class MessageHeadersMarker:
    """메시지 헤더 마커"""

    name: str | None = None  # None이면 전체 헤더


@dataclass(frozen=True)
class PrincipalMarker:
    """인증된 사용자 정보 마커"""

    pass


@dataclass(frozen=True)
class SessionIdMarker:
    """WebSocket 세션 ID 마커"""

    pass


@dataclass(frozen=True)
class WebSocketSessionMarker:
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
else:
    # 런타임용: 클래스
    DestinationVariable = _DestinationVariable
    MessagePayload = _MessagePayload
    MessageHeaders = _MessageHeaders
    Principal = _Principal
    SessionId = _SessionId


# =============================================================================
# Helper Functions
# =============================================================================


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
                if isinstance(
                    arg,
                    (
                        DestinationVariableMarker,
                        MessagePayloadMarker,
                        MessageHeadersMarker,
                        PrincipalMarker,
                        SessionIdMarker,
                        WebSocketSessionMarker,
                    ),
                ):
                    return arg
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
