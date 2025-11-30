"""WebSocket 테스트 클라이언트

WebSocketTestClient와 StompTestClient는 WebSocket 및 STOMP 프로토콜을 테스트합니다.

사용 예시:
    ```python
    from bloom import Application
    from bloom.tests import WebSocketTestClient, StompTestClient

    app = Application("test").scan(__name__).ready()

    # 기본 WebSocket 테스트
    async with WebSocketTestClient(app, "/ws") as ws:
        await ws.send_text("hello")
        response = await ws.receive_text()
        assert response == "world"

    # STOMP 프로토콜 테스트
    async with StompTestClient(app, "/ws") as stomp:
        await stomp.connect()
        await stomp.subscribe("/topic/chat")
        await stomp.send("/app/chat", {"text": "hello"})
        message = await stomp.receive()
        assert message.payload["text"] == "hello"
    ```
"""

from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TYPE_CHECKING
from contextlib import asynccontextmanager

if TYPE_CHECKING:
    from bloom.application import Application


@dataclass
class WebSocketMessage:
    """WebSocket 메시지"""

    type: str  # "text" | "bytes" | "close"
    data: str | bytes | None = None
    close_code: int = 1000
    close_reason: str = ""


class WebSocketTestClient:
    """
    WebSocket 테스트 클라이언트

    ASGI WebSocket 엔드포인트를 직접 호출합니다.

    사용법:
        ```python
        async with WebSocketTestClient(app, "/ws") as ws:
            await ws.send_text("hello")
            msg = await ws.receive_text()
        ```
    """

    def __init__(
        self,
        app: "Application",
        path: str,
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ):
        self.app = app
        self.path = path
        self.headers = headers or {}
        self.query_params = query_params or {}

        self._send_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._receive_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._accepted = False
        self._closed = False
        self._task: asyncio.Task | None = None
        self._subprotocol: str | None = None

    async def __aenter__(self) -> "WebSocketTestClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def connect(self) -> None:
        """WebSocket 연결 시작"""
        # ASGI scope 구성
        query_string = "&".join(f"{k}={v}" for k, v in self.query_params.items())
        headers: list[tuple[bytes, bytes]] = [
            (k.lower().encode(), v.encode()) for k, v in self.headers.items()
        ]
        headers.append((b"host", b"testserver"))

        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "path": self.path,
            "query_string": query_string.encode(),
            "root_path": "",
            "headers": headers,
            "server": ("testserver", 80),
            "subprotocols": [],
        }

        # 연결 요청 큐에 추가
        await self._send_queue.put({"type": "websocket.connect"})

        async def receive() -> dict[str, Any]:
            return await self._send_queue.get()

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "websocket.accept":
                self._accepted = True
                self._subprotocol = message.get("subprotocol")
            elif message["type"] == "websocket.close":
                self._closed = True
            await self._receive_queue.put(message)

        # ASGI 앱을 백그라운드 태스크로 실행
        self._task = asyncio.create_task(self.app.asgi(scope, receive, send))

        # accept 대기
        msg = await self._receive_queue.get()
        if msg["type"] != "websocket.accept":
            raise RuntimeError(f"WebSocket connection not accepted: {msg}")

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """WebSocket 연결 종료"""
        if self._closed:
            return

        await self._send_queue.put(
            {
                "type": "websocket.disconnect",
                "code": code,
            }
        )
        self._closed = True

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=1.0)
            except asyncio.TimeoutError:
                self._task.cancel()

    async def send_text(self, data: str) -> None:
        """텍스트 메시지 전송"""
        if not self._accepted or self._closed:
            raise RuntimeError("WebSocket not connected")

        await self._send_queue.put(
            {
                "type": "websocket.receive",
                "text": data,
            }
        )

    async def send_bytes(self, data: bytes) -> None:
        """바이너리 메시지 전송"""
        if not self._accepted or self._closed:
            raise RuntimeError("WebSocket not connected")

        await self._send_queue.put(
            {
                "type": "websocket.receive",
                "bytes": data,
            }
        )

    async def send_json(self, data: Any) -> None:
        """JSON 메시지 전송"""
        await self.send_text(json.dumps(data))

    async def receive(self, timeout: float = 5.0) -> WebSocketMessage:
        """메시지 수신"""
        try:
            msg = await asyncio.wait_for(self._receive_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError("WebSocket receive timeout")

        if msg["type"] == "websocket.send":
            if "text" in msg:
                return WebSocketMessage(type="text", data=msg["text"])
            elif "bytes" in msg:
                return WebSocketMessage(type="bytes", data=msg["bytes"])
        elif msg["type"] == "websocket.close":
            return WebSocketMessage(
                type="close",
                close_code=msg.get("code", 1000),
                close_reason=msg.get("reason", ""),
            )

        return WebSocketMessage(type="unknown")

    async def receive_text(self, timeout: float = 5.0) -> str:
        """텍스트 메시지 수신"""
        msg = await self.receive(timeout)
        if msg.type != "text":
            raise ValueError(f"Expected text message, got {msg.type}")
        return msg.data  # type: ignore

    async def receive_bytes(self, timeout: float = 5.0) -> bytes:
        """바이너리 메시지 수신"""
        msg = await self.receive(timeout)
        if msg.type != "bytes":
            raise ValueError(f"Expected bytes message, got {msg.type}")
        return msg.data  # type: ignore

    async def receive_json(self, timeout: float = 5.0) -> Any:
        """JSON 메시지 수신"""
        text = await self.receive_text(timeout)
        return json.loads(text)

    @property
    def subprotocol(self) -> str | None:
        """협상된 서브프로토콜"""
        return self._subprotocol


@dataclass
class StompMessage:
    """STOMP 메시지"""

    command: str
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @property
    def destination(self) -> str:
        """목적지 헤더"""
        return self.headers.get("destination", "")

    @property
    def payload(self) -> Any:
        """JSON 페이로드"""
        if self.body:
            try:
                return json.loads(self.body)
            except json.JSONDecodeError:
                return self.body
        return None

    @classmethod
    def parse(cls, raw: str) -> "StompMessage":
        """STOMP 프레임 파싱"""
        lines = raw.split("\n")
        if not lines:
            raise ValueError("Empty STOMP frame")

        command = lines[0].strip()
        headers: dict[str, str] = {}
        body_start = 1

        for i, line in enumerate(lines[1:], 1):
            line = line.strip()
            if not line:
                body_start = i + 1
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip()] = value.strip()

        body = "\n".join(lines[body_start:]).rstrip("\x00").strip()
        return cls(command=command, headers=headers, body=body)

    def encode(self) -> str:
        """STOMP 프레임 인코딩"""
        lines = [self.command]
        for key, value in self.headers.items():
            lines.append(f"{key}:{value}")
        lines.append("")
        if self.body:
            lines.append(self.body)
        lines.append("\x00")
        return "\n".join(lines)


class StompTestClient:
    """
    STOMP 프로토콜 테스트 클라이언트

    STOMP over WebSocket을 테스트합니다.

    사용법:
        ```python
        async with StompTestClient(app, "/ws") as stomp:
            await stomp.connect(login="user", passcode="pass")

            sub_id = await stomp.subscribe("/topic/chat")
            await stomp.send("/app/chat", {"text": "hello"})

            msg = await stomp.receive()
            assert msg.payload["text"] == "hello"

            await stomp.unsubscribe(sub_id)
        ```
    """

    def __init__(
        self,
        app: "Application",
        path: str,
        headers: dict[str, str] | None = None,
    ):
        self.app = app
        self.path = path
        self.headers = headers or {}

        self._ws: WebSocketTestClient | None = None
        self._connected = False
        self._subscription_counter = 0
        self._subscriptions: dict[str, str] = {}  # id -> destination

    async def __aenter__(self) -> "StompTestClient":
        self._ws = WebSocketTestClient(self.app, self.path, self.headers)
        await self._ws.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._connected:
            await self.disconnect()
        if self._ws:
            await self._ws.close()

    async def connect(
        self,
        login: str | None = None,
        passcode: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> StompMessage:
        """STOMP CONNECT"""
        if not self._ws:
            raise RuntimeError("WebSocket not connected")

        connect_headers = {
            "accept-version": "1.2",
            "host": "testserver",
        }
        if login:
            connect_headers["login"] = login
        if passcode:
            connect_headers["passcode"] = passcode
        if headers:
            connect_headers.update(headers)

        frame = StompMessage(command="CONNECT", headers=connect_headers)
        await self._ws.send_text(frame.encode())

        # CONNECTED 응답 대기
        response_text = await self._ws.receive_text()
        response = StompMessage.parse(response_text)

        if response.command == "CONNECTED":
            self._connected = True
        elif response.command == "ERROR":
            raise RuntimeError(f"STOMP connection failed: {response.body}")

        return response

    async def disconnect(self, receipt: str | None = None) -> None:
        """STOMP DISCONNECT"""
        if not self._ws or not self._connected:
            return

        headers = {}
        if receipt:
            headers["receipt"] = receipt

        frame = StompMessage(command="DISCONNECT", headers=headers)
        await self._ws.send_text(frame.encode())
        self._connected = False

    async def subscribe(
        self,
        destination: str,
        subscription_id: str | None = None,
        ack: str = "auto",
    ) -> str:
        """STOMP SUBSCRIBE"""
        if not self._ws or not self._connected:
            raise RuntimeError("STOMP not connected")

        self._subscription_counter += 1
        sub_id = subscription_id or f"sub-{self._subscription_counter}"

        frame = StompMessage(
            command="SUBSCRIBE",
            headers={
                "id": sub_id,
                "destination": destination,
                "ack": ack,
            },
        )
        await self._ws.send_text(frame.encode())

        self._subscriptions[sub_id] = destination
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> None:
        """STOMP UNSUBSCRIBE"""
        if not self._ws or not self._connected:
            raise RuntimeError("STOMP not connected")

        frame = StompMessage(
            command="UNSUBSCRIBE",
            headers={"id": subscription_id},
        )
        await self._ws.send_text(frame.encode())

        self._subscriptions.pop(subscription_id, None)

    async def send(
        self,
        destination: str,
        body: Any = None,
        headers: dict[str, str] | None = None,
        content_type: str = "application/json",
    ) -> None:
        """STOMP SEND"""
        if not self._ws or not self._connected:
            raise RuntimeError("STOMP not connected")

        send_headers = {
            "destination": destination,
            "content-type": content_type,
        }
        if headers:
            send_headers.update(headers)

        body_str = ""
        if body is not None:
            if isinstance(body, str):
                body_str = body
            else:
                body_str = json.dumps(body)

        frame = StompMessage(command="SEND", headers=send_headers, body=body_str)
        await self._ws.send_text(frame.encode())

    async def receive(self, timeout: float = 5.0) -> StompMessage:
        """STOMP 메시지 수신"""
        if not self._ws:
            raise RuntimeError("WebSocket not connected")

        text = await self._ws.receive_text(timeout)
        return StompMessage.parse(text)

    async def ack(self, message_id: str, subscription_id: str) -> None:
        """STOMP ACK"""
        if not self._ws or not self._connected:
            raise RuntimeError("STOMP not connected")

        frame = StompMessage(
            command="ACK",
            headers={
                "id": message_id,
                "subscription": subscription_id,
            },
        )
        await self._ws.send_text(frame.encode())

    async def nack(self, message_id: str, subscription_id: str) -> None:
        """STOMP NACK"""
        if not self._ws or not self._connected:
            raise RuntimeError("STOMP not connected")

        frame = StompMessage(
            command="NACK",
            headers={
                "id": message_id,
                "subscription": subscription_id,
            },
        )
        await self._ws.send_text(frame.encode())

    @property
    def is_connected(self) -> bool:
        """STOMP 연결 상태"""
        return self._connected
