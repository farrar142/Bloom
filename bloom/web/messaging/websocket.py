"""WebSocket 세션 및 핸들러

ASGI WebSocket 프로토콜을 추상화하여 사용하기 쉬운 인터페이스를 제공합니다.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Awaitable, TYPE_CHECKING


class WebSocketState(Enum):
    """WebSocket 연결 상태"""

    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()
    DISCONNECTED = auto()


@dataclass
class WebSocketSession:
    """WebSocket 세션

    ASGI WebSocket 연결을 래핑하여 메시지 송수신을 추상화합니다.

    Examples:
        async def websocket_handler(session: WebSocketSession):
            await session.accept()

            async for message in session:
                await session.send_text(f"Echo: {message}")

            await session.close()
    """

    scope: dict[str, Any]
    receive: Callable[[], Awaitable[Any]]
    send: Callable[[dict[str, Any]], Awaitable[Any]]
    state: WebSocketState = WebSocketState.CONNECTING

    # 세션 메타데이터
    session_id: str = ""
    user_id: Any = None
    attributes: dict[str, Any] = field(default_factory=dict)

    # 내부 상태
    _accepted: bool = False
    _closed: bool = False

    @property
    def path(self) -> str:
        """요청 경로"""
        return self.scope.get("path", "/")

    @property
    def query_string(self) -> bytes:
        """쿼리 스트링"""
        return self.scope.get("query_string", b"")

    @property
    def headers(self) -> dict[str, str]:
        """HTTP 헤더"""
        raw_headers = self.scope.get("headers", [])
        return {k.decode(): v.decode() for k, v in raw_headers}

    @property
    def subprotocols(self) -> list[str]:
        """요청된 서브프로토콜 목록"""
        return self.scope.get("subprotocols", [])

    @property
    def client(self) -> tuple[str, int] | None:
        """클라이언트 주소 (host, port)"""
        return self.scope.get("client")

    async def accept(
        self,
        subprotocol: str | None = None,
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        """WebSocket 연결 수락

        Args:
            subprotocol: 선택된 서브프로토콜
            headers: 추가 응답 헤더
        """
        if self._accepted:
            return

        message: dict[str, Any] = {"type": "websocket.accept"}
        if subprotocol:
            message["subprotocol"] = subprotocol
        if headers:
            message["headers"] = headers

        await self.send(message)
        self._accepted = True
        self.state = WebSocketState.CONNECTED

    async def send_text(self, data: str) -> None:
        """텍스트 메시지 전송"""
        if self._closed:
            raise RuntimeError("WebSocket is closed")
        await self.send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        """바이너리 메시지 전송"""
        if self._closed:
            raise RuntimeError("WebSocket is closed")
        await self.send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any) -> None:
        """JSON 메시지 전송"""
        await self.send_text(json.dumps(data, ensure_ascii=False))

    async def receive_message(self) -> dict[str, Any]:
        """메시지 수신 (raw ASGI 메시지)"""
        return await self.receive()

    async def receive_text(self) -> str | None:
        """텍스트 메시지 수신

        Returns:
            텍스트 메시지 또는 연결 종료시 None
        """
        message = await self.receive()

        if message["type"] == "websocket.disconnect":
            self.state = WebSocketState.DISCONNECTED
            self._closed = True
            return None

        if message["type"] == "websocket.receive":
            return message.get("text", "")

        return None

    async def receive_bytes(self) -> bytes | None:
        """바이너리 메시지 수신

        Returns:
            바이너리 메시지 또는 연결 종료시 None
        """
        message = await self.receive()

        if message["type"] == "websocket.disconnect":
            self.state = WebSocketState.DISCONNECTED
            self._closed = True
            return None

        if message["type"] == "websocket.receive":
            return message.get("bytes", b"")

        return None

    async def receive_json(self) -> Any | None:
        """JSON 메시지 수신"""
        text = await self.receive_text()
        if text is None:
            return None
        return json.loads(text)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """WebSocket 연결 종료

        Args:
            code: 종료 코드 (기본 1000 = 정상 종료)
            reason: 종료 사유
        """
        if self._closed:
            return

        self.state = WebSocketState.DISCONNECTING
        await self.send(
            {
                "type": "websocket.close",
                "code": code,
                "reason": reason,
            }
        )
        self._closed = True
        self.state = WebSocketState.DISCONNECTED

    async def __aiter__(self):
        """비동기 이터레이터로 메시지 수신

        Examples:
            async for message in session:
                print(message)
        """
        while not self._closed:
            message = await self.receive_text()
            if message is None:
                break
            yield message

    def __repr__(self) -> str:
        return (
            f"WebSocketSession(path={self.path!r}, "
            f"session_id={self.session_id!r}, state={self.state.name})"
        )


class WebSocketHandler(ABC):
    """WebSocket 핸들러 베이스 클래스

    WebSocket 연결의 라이프사이클을 처리합니다.

    Examples:
        class EchoHandler(WebSocketHandler):
            async def on_connect(self, session: WebSocketSession) -> bool:
                return True  # 연결 수락

            async def on_message(self, session: WebSocketSession, message: str):
                await session.send_text(f"Echo: {message}")

            async def on_disconnect(self, session: WebSocketSession, code: int):
                print(f"Disconnected: {code}")
    """

    @abstractmethod
    async def on_connect(self, session: WebSocketSession) -> bool:
        """연결 시 호출

        Returns:
            True면 연결 수락, False면 거부
        """
        pass

    @abstractmethod
    async def on_message(self, session: WebSocketSession, message: str) -> None:
        """메시지 수신 시 호출"""
        pass

    async def on_disconnect(self, session: WebSocketSession, code: int) -> None:
        """연결 종료 시 호출"""
        pass

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[dict[str, Any]], Awaitable[Any]],
    ) -> None:
        """ASGI 앱으로 동작"""
        session = WebSocketSession(scope=scope, receive=receive, send=send)

        # 연결 수락 여부 확인
        if not await self.on_connect(session):
            await session.close(code=4000, reason="Connection rejected")
            return

        await session.accept()

        try:
            async for message in session:
                await self.on_message(session, message)
        except Exception:
            await session.close(code=1011, reason="Internal error")
            raise
        finally:
            await self.on_disconnect(session, 1000)


class WebSocketEndpoint:
    """WebSocket 엔드포인트

    함수 기반 WebSocket 핸들러를 위한 래퍼입니다.

    Examples:
        @app.websocket("/ws")
        async def websocket_handler(session: WebSocketSession):
            await session.accept()
            async for message in session:
                await session.send_text(f"Echo: {message}")
    """

    def __init__(
        self,
        path: str,
        handler: Callable[[WebSocketSession], Awaitable[None]],
    ):
        self.path = path
        self.handler = handler

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[dict[str, Any]], Awaitable[Any]],
    ) -> None:
        """ASGI 앱으로 동작"""
        session = WebSocketSession(scope=scope, receive=receive, send=send)
        await self.handler(session)
