"""bloom.testing.client - 테스트 클라이언트"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, AsyncMock


class TestResponse:
    """
    HTTP 응답 래퍼.

    TestClient의 응답을 감싸서 편리한 인터페이스를 제공합니다.

    Attributes:
        status_code: HTTP 상태 코드
        headers: 응답 헤더
        content: 응답 본문 (bytes)
    """

    def __init__(
        self,
        status_code: int,
        headers: dict[str, str],
        content: bytes,
    ):
        self.status_code = status_code
        self.headers = headers
        self.content = content

    @property
    def text(self) -> str:
        """응답 본문을 텍스트로 반환"""
        return self.content.decode("utf-8")

    def json(self) -> Any:
        """응답 본문을 JSON으로 파싱"""
        return json.loads(self.content)

    def raise_for_status(self) -> None:
        """4xx/5xx 응답이면 예외 발생"""
        if 400 <= self.status_code < 600:
            raise HTTPStatusError(self.status_code, self.text)


class HTTPStatusError(Exception):
    """HTTP 상태 에러"""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class TestClient:
    """
    HTTP 테스트 클라이언트.

    ASGI 애플리케이션을 직접 호출하여 HTTP 요청을 테스트합니다.

    사용 예:
        async with TestClient(app) as client:
            response = await client.get("/api/users")
            assert response.status_code == 200

    Args:
        app: ASGI 애플리케이션
        base_url: 기본 URL (기본값: "http://testserver")
    """

    def __init__(self, app, base_url: str = "http://testserver"):
        self.app = app
        self.base_url = base_url
        self._default_headers: dict[str, str] = {}

    async def __aenter__(self) -> "TestClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def set_default_headers(self, headers: dict[str, str]) -> None:
        """기본 헤더 설정"""
        self._default_headers.update(headers)

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: bytes | str | None = None,
        content_type: str | None = None,
    ) -> TestResponse:
        """
        HTTP 요청 실행.

        Args:
            method: HTTP 메서드
            path: 요청 경로
            headers: 요청 헤더
            params: 쿼리 파라미터
            json: JSON 본문
            data: 원시 본문
            content_type: Content-Type 헤더

        Returns:
            TestResponse 객체
        """
        # 쿼리 스트링 빌드
        query_string = ""
        if params:
            query_parts = []
            for key, value in params.items():
                if isinstance(value, list):
                    for v in value:
                        query_parts.append(f"{key}={v}")
                else:
                    query_parts.append(f"{key}={value}")
            query_string = "&".join(query_parts)

        # 헤더 병합
        request_headers = {**self._default_headers}
        if headers:
            request_headers.update(headers)

        # 본문 준비
        body = b""
        if json is not None:
            import json as json_module

            body = json_module.dumps(json).encode("utf-8")
            if "content-type" not in {h.lower() for h in request_headers}:
                request_headers["content-type"] = "application/json"
        elif data is not None:
            body = data.encode("utf-8") if isinstance(data, str) else data
            if content_type:
                request_headers["content-type"] = content_type

        # ASGI scope 생성
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": path,
            "query_string": query_string.encode("utf-8"),
            "root_path": "",
            "headers": [
                (k.lower().encode("utf-8"), v.encode("utf-8"))
                for k, v in request_headers.items()
            ],
            "server": ("testserver", 80),
        }

        # 응답 수집
        response_started = False
        response_status = 0
        response_headers: dict[str, str] = {}
        response_body: list[bytes] = []

        async def receive():
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }

        async def send(message):
            nonlocal response_started, response_status, response_headers

            if message["type"] == "http.response.start":
                response_started = True
                response_status = message["status"]
                for key, value in message.get("headers", []):
                    response_headers[key.decode("utf-8")] = value.decode("utf-8")
            elif message["type"] == "http.response.body":
                body_data = message.get("body", b"")
                if body_data:
                    response_body.append(body_data)

        # ASGI 앱 호출
        await self.app(scope, receive, send)

        return TestResponse(
            status_code=response_status,
            headers=response_headers,
            content=b"".join(response_body),
        )

    async def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> TestResponse:
        """GET 요청"""
        return await self.request("GET", path, headers=headers, params=params)

    async def post(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        data: bytes | str | None = None,
    ) -> TestResponse:
        """POST 요청"""
        return await self.request("POST", path, headers=headers, json=json, data=data)

    async def put(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        data: bytes | str | None = None,
    ) -> TestResponse:
        """PUT 요청"""
        return await self.request("PUT", path, headers=headers, json=json, data=data)

    async def patch(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        json: Any | None = None,
        data: bytes | str | None = None,
    ) -> TestResponse:
        """PATCH 요청"""
        return await self.request("PATCH", path, headers=headers, json=json, data=data)

    async def delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """DELETE 요청"""
        return await self.request("DELETE", path, headers=headers)


class WebSocketTestClient:
    """
    WebSocket 테스트 클라이언트.

    ASGI 애플리케이션의 WebSocket 엔드포인트를 테스트합니다.

    사용 예:
        async with WebSocketTestClient(app, "/ws") as ws:
            await ws.send_json({"action": "ping"})
            data = await ws.receive_json()
            assert data["action"] == "pong"
    """

    def __init__(
        self,
        app,
        path: str,
        headers: dict[str, str] | None = None,
    ):
        self.app = app
        self.path = path
        self.headers = headers or {}
        self._send_queue: list = []
        self._receive_queue: list = []
        self._closed = False
        self._task = None

    async def __aenter__(self) -> "WebSocketTestClient":
        import asyncio

        # WebSocket scope 생성
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "path": self.path,
            "query_string": b"",
            "root_path": "",
            "headers": [
                (k.lower().encode("utf-8"), v.encode("utf-8"))
                for k, v in self.headers.items()
            ],
            "server": ("testserver", 80),
            "subprotocols": [],
        }

        # 메시지 큐
        self._client_to_server: asyncio.Queue = asyncio.Queue()
        self._server_to_client: asyncio.Queue = asyncio.Queue()

        # 연결 요청
        await self._client_to_server.put({"type": "websocket.connect"})

        async def receive():
            return await self._client_to_server.get()

        async def send(message):
            if message["type"] == "websocket.accept":
                pass  # 연결 수락
            elif message["type"] == "websocket.close":
                self._closed = True
            else:
                await self._server_to_client.put(message)

        # ASGI 앱 실행 (백그라운드)
        self._task = asyncio.create_task(self.app(scope, receive, send))

        # 연결 수락 대기 (짧은 시간)
        await asyncio.sleep(0.01)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        import asyncio

        if not self._closed:
            await self._client_to_server.put({"type": "websocket.disconnect"})

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def send_text(self, data: str) -> None:
        """텍스트 메시지 전송"""
        await self._client_to_server.put({
            "type": "websocket.receive",
            "text": data,
        })

    async def send_json(self, data: Any) -> None:
        """JSON 메시지 전송"""
        await self.send_text(json.dumps(data))

    async def send_bytes(self, data: bytes) -> None:
        """바이너리 메시지 전송"""
        await self._client_to_server.put({
            "type": "websocket.receive",
            "bytes": data,
        })

    async def receive_text(self, timeout: float = 1.0) -> str:
        """텍스트 메시지 수신"""
        import asyncio

        try:
            message = await asyncio.wait_for(
                self._server_to_client.get(),
                timeout=timeout,
            )
            return message.get("text", "")
        except asyncio.TimeoutError:
            raise TimeoutError("WebSocket receive timeout")

    async def receive_json(self, timeout: float = 1.0) -> Any:
        """JSON 메시지 수신"""
        text = await self.receive_text(timeout)
        return json.loads(text)

    async def receive_bytes(self, timeout: float = 1.0) -> bytes:
        """바이너리 메시지 수신"""
        import asyncio

        try:
            message = await asyncio.wait_for(
                self._server_to_client.get(),
                timeout=timeout,
            )
            return message.get("bytes", b"")
        except asyncio.TimeoutError:
            raise TimeoutError("WebSocket receive timeout")

    async def close(self, code: int = 1000) -> None:
        """WebSocket 연결 종료"""
        await self._client_to_server.put({
            "type": "websocket.disconnect",
            "code": code,
        })
        self._closed = True
