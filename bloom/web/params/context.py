"""파라미터 리졸버 컨텍스트 - 공통 인터페이스"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from bloom.web.http import HttpRequest
    from bloom.web.messaging.session import WebSocketSession, Message


class ResolverContext(ABC):
    """
    파라미터 리졸버를 위한 공통 컨텍스트 인터페이스

    HTTP와 WebSocket/STOMP 양쪽에서 사용 가능한 통합 컨텍스트입니다.
    각 구현체는 자신의 환경에 맞는 정보를 제공합니다.
    """

    # 서브클래스에서 구현/정의해야 하는 속성
    path_params: dict[str, str]

    @property
    @abstractmethod
    def is_http(self) -> bool:
        """HTTP 요청 컨텍스트인지 여부"""
        ...

    @property
    @abstractmethod
    def is_websocket(self) -> bool:
        """WebSocket/STOMP 메시지 컨텍스트인지 여부"""
        ...

    # HTTP 전용 속성 (WebSocket에서는 None)
    @property
    def http_request(self) -> "HttpRequest | None":
        """HTTP 요청 객체 (HTTP 컨텍스트에서만 사용 가능)"""
        return None

    # WebSocket/STOMP 전용 속성 (HTTP에서는 None)
    @property
    def websocket_session(self) -> "WebSocketSession | None":
        """WebSocket 세션 (WebSocket 컨텍스트에서만 사용 가능)"""
        return None

    @property
    def stomp_message(self) -> "Message | None":
        """STOMP 메시지 (WebSocket 컨텍스트에서만 사용 가능)"""
        return None

    # 공통 유틸리티
    def get_body(self) -> Any:
        """
        요청/메시지 본문 반환

        HTTP: request.body (bytes 또는 파싱된 데이터)
        WebSocket: message.payload (JSON 파싱된 데이터)
        """
        if self.is_http and self.http_request:
            return self.http_request.body
        if self.is_websocket and self.stomp_message:
            return self.stomp_message.payload
        return None

    def get_headers(self) -> dict[str, str]:
        """
        헤더 반환

        HTTP: request.headers
        WebSocket: message.headers (STOMP 헤더)
        """
        if self.is_http and self.http_request:
            return self.http_request.headers
        if self.is_websocket and self.stomp_message:
            return self.stomp_message.headers
        return {}


@dataclass
class HttpResolverContext(ResolverContext):
    """HTTP 요청을 위한 리졸버 컨텍스트"""

    request: "HttpRequest"
    path_params: dict[str, str]

    @property
    def is_http(self) -> bool:
        return True

    @property
    def is_websocket(self) -> bool:
        return False

    @property
    def http_request(self) -> "HttpRequest | None":
        return self.request


@dataclass
class MessageResolverContext(ResolverContext):
    """
    STOMP 메시지 핸들러 파라미터 해석을 위한 컨텍스트

    Attributes:
        session: WebSocket 세션
        message: STOMP 메시지 (없을 수도 있음)
        path_params: 목적지 패턴에서 추출된 경로 파라미터
    """

    session: "WebSocketSession"
    message: "Message | None"
    path_params: dict[str, str]

    @property
    def is_http(self) -> bool:
        return False

    @property
    def is_websocket(self) -> bool:
        return True

    @property
    def websocket_session(self) -> "WebSocketSession | None":
        return self.session

    @property
    def stomp_message(self) -> "Message | None":
        return self.message
