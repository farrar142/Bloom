"""응답(Response) 테스트"""

import pytest
import tempfile
import os
from pathlib import Path

from bloom.web.response import (
    Response,
    JSONResponse,
    HTMLResponse,
    PlainTextResponse,
    StreamingResponse,
    FileResponse,
    SSEResponse,
    SSEEvent,
)


# === Test Utilities ===


class MockSend:
    """테스트용 Send callable"""

    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def response_start(self):
        for msg in self.messages:
            if msg["type"] == "http.response.start":
                return msg
        return None

    @property
    def body(self) -> bytes:
        body_parts = []
        for msg in self.messages:
            if msg["type"] == "http.response.body":
                body_parts.append(msg.get("body", b""))
        return b"".join(body_parts)

    @property
    def status(self) -> int:
        start = self.response_start
        return start["status"] if start else 0

    def get_header(self, name: str) -> str | None:
        start = self.response_start
        if not start:
            return None
        headers = start.get("headers", [])
        name_bytes = name.lower().encode()
        for key, value in headers:
            if key.lower() == name_bytes:
                return value.decode() if isinstance(value, bytes) else value
        return None


# === StreamingResponse Tests ===


class TestStreamingResponse:
    """StreamingResponse 테스트"""

    @pytest.mark.asyncio
    async def test_sync_iterator(self):
        """동기 이터레이터"""

        def gen():
            yield b"Hello, "
            yield b"World!"

        response = StreamingResponse(gen())
        send = MockSend()
        await response(None, None, send)

        assert send.status == 200
        assert send.body == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_async_iterator(self):
        """비동기 이터레이터"""

        async def gen():
            yield b"Async "
            yield b"Stream"

        response = StreamingResponse(gen())
        send = MockSend()
        await response(None, None, send)

        assert send.status == 200
        assert send.body == b"Async Stream"

    @pytest.mark.asyncio
    async def test_custom_content_type(self):
        """커스텀 Content-Type"""

        async def gen():
            yield b"data"

        response = StreamingResponse(gen(), media_type="text/plain")
        send = MockSend()
        await response(None, None, send)

        assert send.get_header("content-type") == "text/plain"

    @pytest.mark.asyncio
    async def test_custom_headers(self):
        """커스텀 헤더"""

        async def gen():
            yield b"data"

        response = StreamingResponse(gen(), headers={"X-Custom": "value"})
        send = MockSend()
        await response(None, None, send)

        assert send.get_header("x-custom") == "value"


# === FileResponse Tests ===


class TestFileResponse:
    """FileResponse 테스트"""

    @pytest.mark.asyncio
    async def test_file_response(self):
        """파일 응답"""
        content = b"File content for testing"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(content)
            filepath = f.name

        try:
            response = FileResponse(filepath)
            send = MockSend()
            await response(None, None, send)

            assert send.status == 200
            assert send.body == content
            # content-length 헤더 확인
            assert send.get_header("content-length") == str(len(content))
        finally:
            os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_file_response_custom_filename(self):
        """커스텀 파일명"""
        content = b"Test content"

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            filepath = f.name

        try:
            response = FileResponse(filepath, filename="custom.txt")
            send = MockSend()
            await response(None, None, send)

            disposition = send.get_header("content-disposition") or ""
            assert "custom.txt" in disposition
        finally:
            os.unlink(filepath)

    @pytest.mark.asyncio
    async def test_file_response_media_type(self):
        """파일 미디어 타입"""
        content = b"Test content"

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(content)
            filepath = f.name

        try:
            response = FileResponse(filepath, media_type="text/plain")
            send = MockSend()
            await response(None, None, send)

            assert send.get_header("content-type") == "text/plain"
        finally:
            os.unlink(filepath)


# === SSEResponse Tests ===


class TestSSEResponse:
    """SSEResponse 테스트"""

    @pytest.mark.asyncio
    async def test_sse_response(self):
        """SSE 응답"""

        async def event_gen():
            yield SSEEvent(data="Hello")
            yield SSEEvent(data="World", event="message")

        response = SSEResponse(event_gen())
        send = MockSend()
        await response(None, None, send)

        assert send.status == 200
        assert send.get_header("content-type") == "text/event-stream"
        assert send.get_header("cache-control") == "no-cache"

        body = send.body.decode()
        assert "data: Hello" in body
        assert "data: World" in body
        assert "event: message" in body

    @pytest.mark.asyncio
    async def test_sse_event_id(self):
        """SSE 이벤트 ID"""

        async def event_gen():
            yield SSEEvent(data="test", id="123")

        response = SSEResponse(event_gen())
        send = MockSend()
        await response(None, None, send)

        body = send.body.decode()
        assert "id: 123" in body

    @pytest.mark.asyncio
    async def test_sse_event_retry(self):
        """SSE 재연결 시간"""

        async def event_gen():
            yield SSEEvent(data="test", retry=5000)

        response = SSEResponse(event_gen())
        send = MockSend()
        await response(None, None, send)

        body = send.body.decode()
        assert "retry: 5000" in body


# === SSEEvent Tests ===


class TestSSEEvent:
    """SSEEvent 테스트"""

    def test_event_simple(self):
        """단순 이벤트"""
        event = SSEEvent(data="Hello")
        assert event.encode() == b"data: Hello\n\n"

    def test_event_with_type(self):
        """이벤트 타입"""
        event = SSEEvent(data="Hello", event="greeting")
        encoded = event.encode().decode()
        assert "event: greeting\n" in encoded
        assert "data: Hello\n" in encoded

    def test_event_with_id(self):
        """이벤트 ID"""
        event = SSEEvent(data="Hello", id="123")
        encoded = event.encode().decode()
        assert "id: 123\n" in encoded

    def test_event_multiline_data(self):
        """여러 줄 데이터"""
        event = SSEEvent(data="Line1\nLine2\nLine3")
        encoded = event.encode().decode()
        assert "data: Line1\n" in encoded
        assert "data: Line2\n" in encoded
        assert "data: Line3\n" in encoded


# === Basic Response Tests ===


class TestBasicResponses:
    """기본 응답 테스트"""

    @pytest.mark.asyncio
    async def test_json_response(self):
        """JSON 응답"""
        response = JSONResponse({"message": "Hello"})
        send = MockSend()
        await response(None, None, send)

        assert send.status == 200
        assert send.get_header("content-type") == "application/json"
        assert b'"message"' in send.body
        assert b'"Hello"' in send.body

    @pytest.mark.asyncio
    async def test_html_response(self):
        """HTML 응답"""
        response = HTMLResponse("<h1>Hello</h1>")
        send = MockSend()
        await response(None, None, send)

        assert send.status == 200
        assert send.get_header("content-type") == "text/html; charset=utf-8"
        assert send.body == b"<h1>Hello</h1>"

    @pytest.mark.asyncio
    async def test_plain_text_response(self):
        """Plain Text 응답"""
        response = PlainTextResponse("Hello, World!")
        send = MockSend()
        await response(None, None, send)

        assert send.status == 200
        assert send.get_header("content-type") == "text/plain; charset=utf-8"
        assert send.body == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_response_status_code(self):
        """상태 코드"""
        response = JSONResponse({"error": "Not Found"}, status_code=404)
        send = MockSend()
        await response(None, None, send)

        assert send.status == 404

    @pytest.mark.asyncio
    async def test_response_custom_headers(self):
        """커스텀 헤더"""
        response = JSONResponse({"data": "test"}, headers={"X-Request-Id": "abc123"})
        send = MockSend()
        await response(None, None, send)

        assert send.get_header("x-request-id") == "abc123"
