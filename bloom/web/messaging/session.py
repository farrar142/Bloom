"""WebSocket 세션 관리 (내부 사용)"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TYPE_CHECKING

if TYPE_CHECKING:
    from .message import Message, StompFrame

# ASGI 타입
Receive = Callable[[], Coroutine[Any, Any, dict[str, Any]]]
Send = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class WebSocketDisconnect(Exception):
    """WebSocket 연결 해제 예외"""

    def __init__(self, code: int = 1000, reason: str = ""):
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket disconnected: code={code}, reason={reason}")


@dataclass
class WebSocketSession:
    """
    WebSocket 세션 래퍼 (내부 사용)

    ASGI WebSocket 연결을 추상화.
    개발자는 이 클래스를 직접 사용하지 않고 Message를 통해 통신.

    Attributes:
        id: 고유 세션 ID
        path: WebSocket 연결 경로
        headers: HTTP 업그레이드 요청 헤더
        query_params: 쿼리 파라미터
        user: 인증된 사용자 (옵션)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    path: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    user: str | None = None
    _receive: Receive | None = field(default=None, repr=False)
    _send: Send | None = field(default=None, repr=False)
    _accepted: bool = field(default=False, repr=False)
    _closed: bool = field(default=False, repr=False)

    async def accept(self, subprotocol: str | None = None) -> None:
        """
        WebSocket 연결 수락

        Args:
            subprotocol: 서브프로토콜 (예: "stomp")
        """
        if self._accepted:
            raise RuntimeError("WebSocket already accepted")
        if self._closed:
            raise RuntimeError("WebSocket is closed")

        message: dict[str, Any] = {"type": "websocket.accept"}
        if subprotocol:
            message["subprotocol"] = subprotocol

        await self._send(message)  # type: ignore
        self._accepted = True

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        WebSocket 연결 종료

        Args:
            code: 종료 코드 (기본: 1000 정상 종료)
            reason: 종료 사유
        """
        if self._closed:
            return

        await self._send(  # type: ignore
            {
                "type": "websocket.close",
                "code": code,
                "reason": reason,
            }
        )
        self._closed = True

    async def send_text(self, data: str) -> None:
        """
        텍스트 메시지 전송

        Args:
            data: 전송할 텍스트
        """
        if not self._accepted:
            raise RuntimeError("WebSocket not accepted")
        if self._closed:
            raise RuntimeError("WebSocket is closed")

        await self._send(  # type: ignore
            {
                "type": "websocket.send",
                "text": data,
            }
        )

    async def send_bytes(self, data: bytes) -> None:
        """
        바이너리 메시지 전송

        Args:
            data: 전송할 바이트
        """
        if not self._accepted:
            raise RuntimeError("WebSocket not accepted")
        if self._closed:
            raise RuntimeError("WebSocket is closed")

        await self._send(  # type: ignore
            {
                "type": "websocket.send",
                "bytes": data,
            }
        )

    async def send_frame(self, frame: "StompFrame") -> None:
        """
        STOMP 프레임 전송

        Args:
            frame: STOMP 프레임
        """
        await self.send_text(frame.encode())

    async def receive(self) -> dict[str, Any]:
        """
        원시 ASGI 메시지 수신

        Returns:
            ASGI 메시지 딕셔너리

        Raises:
            WebSocketDisconnect: 연결 해제 시
        """
        message = await self._receive()  # type: ignore

        if message["type"] == "websocket.disconnect":
            self._closed = True
            raise WebSocketDisconnect(
                code=message.get("code", 1000),
                reason=message.get("reason", ""),
            )

        return message

    async def receive_text(self) -> str:
        """
        텍스트 메시지 수신

        Returns:
            수신된 텍스트

        Raises:
            WebSocketDisconnect: 연결 해제 시
        """
        message = await self.receive()
        return message.get("text", "")

    async def receive_bytes(self) -> bytes:
        """
        바이너리 메시지 수신

        Returns:
            수신된 바이트

        Raises:
            WebSocketDisconnect: 연결 해제 시
        """
        message = await self.receive()
        return message.get("bytes", b"")

    @property
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self._accepted and not self._closed


class WebSocketSessionManager:
    """
    WebSocket 세션 관리자

    모든 활성 세션을 추적하고 관리.
    """

    def __init__(self):
        self._sessions: dict[str, WebSocketSession] = {}

    def add(self, session: WebSocketSession) -> None:
        """세션 추가"""
        self._sessions[session.id] = session

    def remove(self, session_id: str) -> WebSocketSession | None:
        """세션 제거"""
        return self._sessions.pop(session_id, None)

    def get(self, session_id: str) -> WebSocketSession | None:
        """세션 조회"""
        return self._sessions.get(session_id)

    def get_all(self) -> list[WebSocketSession]:
        """모든 세션 조회"""
        return list(self._sessions.values())

    def get_by_user(self, user: str) -> list[WebSocketSession]:
        """특정 사용자의 세션들 조회"""
        return [s for s in self._sessions.values() if s.user == user]

    @property
    def count(self) -> int:
        """활성 세션 수"""
        return len(self._sessions)
