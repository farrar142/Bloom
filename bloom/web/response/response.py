"""bloom.web.response - HTTP Response Objects"""

from __future__ import annotations

import json
from typing import (
    Any,
    AsyncIterable,
    Callable,
    Iterable,
    Mapping,
    TYPE_CHECKING,
    Self,
    TypeGuard,
)

from ..types import Receive, Scope, Send


def is_callable(obj: Any) -> TypeGuard[Callable]:
    return callable(obj)


def is_async_iterable[T](
    obj: AsyncIterable[T] | Iterable[T] | Callable,
) -> TypeGuard[AsyncIterable[T]]:
    return hasattr(obj, "__aiter__")


def is_iterable[T](
    obj: AsyncIterable[T] | Iterable[T] | Callable,
) -> TypeGuard[Iterable[T]]:
    return hasattr(obj, "__iter__")


class HttpResponse:
    """
    HTTP Response 기본 클래스.

    사용 예:
        response = Response(content=b"Hello", status_code=200)
        await response(scope, receive, send)
    """

    media_type: str | None = None
    charset: str = "utf-8"

    def __init__(
        self,
        content: bytes | str | None = None,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._headers: dict[str, str] = dict(headers) if headers else {}

        if media_type is not None:
            self.media_type = media_type

        self.body = self._encode_body(content)
        self._set_content_headers()

    def _encode_body(self, content: bytes | str | None) -> bytes:
        """본문 인코딩"""
        if content is None:
            return b""
        if isinstance(content, bytes):
            return content
        if isinstance(content, str):
            return content.encode(self.charset)
        raise TypeError("Content must be bytes, str, or None")

    def _set_content_headers(self) -> None:
        """Content-Type, Content-Length 헤더 설정"""
        if self.body:
            self._headers.setdefault("content-length", str(len(self.body)))

        if self.media_type is not None:
            content_type = self.media_type
            if self.media_type.startswith("text/") and "charset" not in self.media_type:
                content_type = f"{self.media_type}; charset={self.charset}"
            self._headers.setdefault("content-type", content_type)

    @property
    def headers(self) -> dict[str, str]:
        """응답 헤더"""
        return self._headers

    def set_header(self, name: str, value: str) -> Self:
        """헤더 설정"""
        self._headers[name.lower()] = value
        return self

    def set_cookie(
        self,
        key: str,
        value: str = "",
        max_age: int | None = None,
        expires: str | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: str | None = "lax",
    ) -> Self:
        """쿠키 설정"""
        cookie = f"{key}={value}"

        if max_age is not None:
            cookie += f"; Max-Age={max_age}"
        if expires is not None:
            cookie += f"; Expires={expires}"
        if path:
            cookie += f"; Path={path}"
        if domain:
            cookie += f"; Domain={domain}"
        if secure:
            cookie += "; Secure"
        if httponly:
            cookie += "; HttpOnly"
        if samesite:
            cookie += f"; SameSite={samesite}"

        # 여러 쿠키 지원을 위해 기존 Set-Cookie에 추가
        existing = self._headers.get("set-cookie", "")
        if existing:
            self._headers["set-cookie"] = f"{existing}, {cookie}"
        else:
            self._headers["set-cookie"] = cookie

        return self

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        """ASGI 형식 헤더 빌드"""
        return [
            (key.encode("latin-1"), value.encode("latin-1"))
            for key, value in self._headers.items()
        ]

    async def __call__(self, scope: Any, receive: Any, send: "Send") -> None:
        """ASGI 응답 전송"""
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": self.body,
            }
        )

    def __repr__(self) -> str:
        return f"<Response {self.status_code}>"


class JSONResponse(HttpResponse):
    """JSON 응답"""

    media_type = "application/json"

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        body = json.dumps(content, ensure_ascii=False) if content is not None else ""
        super().__init__(
            content=body,
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
        )


class HTMLResponse(HttpResponse):
    """HTML 응답"""

    media_type = "text/html"

    def __init__(
        self,
        content: str = "",
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
        )


class PlainTextResponse(HttpResponse):
    """Plain Text 응답"""

    media_type = "text/plain"

    def __init__(
        self,
        content: str = "",
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
        )


class RedirectResponse(HttpResponse):
    """리다이렉트 응답"""

    def __init__(
        self,
        url: str,
        status_code: int = 307,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            content=b"",
            status_code=status_code,
            headers=headers,
        )
        self.set_header("location", url)


class StreamingResponse(HttpResponse):
    """
    스트리밍 응답.

    대용량 파일이나 실시간 데이터를 청크 단위로 전송합니다.

    사용 예:
        async def generate():
            for i in range(10):
                yield f"chunk {i}\\n".encode()
                await asyncio.sleep(0.1)

        return StreamingResponse(generate(), media_type="text/plain")
    """

    def __init__(
        self,
        content: AsyncIterable[bytes] | Iterable[bytes] | Callable,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        self.status_code = status_code
        self._headers = dict(headers) if headers else {}
        self.media_type = media_type
        self._content = content

        if self.media_type is not None:
            self._headers.setdefault("content-type", self.media_type)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 스트리밍 응답 전송"""
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )

        # Callable이면 호출
        content = self._content
        if is_callable(content):
            content = content()

        # AsyncIterable 처리
        if is_async_iterable(content):
            async for chunk in content:
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )
        elif is_iterable(content):
            # 동기 Iterable 처리
            for chunk in content:
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )

        await send(
            {
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            }
        )


class FileResponse(StreamingResponse):
    """
    파일 응답.

    파일을 청크 단위로 스트리밍합니다.

    사용 예:
        return FileResponse("/path/to/file.pdf")
        return FileResponse("/path/to/image.jpg", filename="download.jpg")
    """

    chunk_size: int = 64 * 1024  # 64KB

    def __init__(
        self,
        path: str,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        filename: str | None = None,
    ) -> None:
        import mimetypes
        import os

        self.path = path

        # 파일 존재 확인
        if not os.path.isfile(path):
            raise FileNotFoundError(f"File not found: {path}")

        # Content-Type 추론
        if media_type is None:
            media_type, _ = mimetypes.guess_type(path)
            if media_type is None:
                media_type = "application/octet-stream"

        # 파일 크기
        file_size = os.path.getsize(path)

        # 헤더 설정
        _headers = dict(headers) if headers else {}
        _headers["content-length"] = str(file_size)

        # Content-Disposition (다운로드 파일명)
        if filename:
            _headers["content-disposition"] = f'attachment; filename="{filename}"'

        super().__init__(
            content=self._file_iterator,
            status_code=status_code,
            headers=_headers,
            media_type=media_type,
        )

    async def _file_iterator(self):
        """파일 청크 반복자"""
        with open(self.path, "rb") as f:
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                yield chunk


class SSEResponse(HttpResponse):
    """
    Server-Sent Events (SSE) 응답.

    실시간 이벤트 스트리밍을 위한 응답입니다.

    사용 예:
        async def event_stream():
            for i in range(10):
                yield SSEEvent(data=f"count: {i}", event="counter")
                await asyncio.sleep(1)

        return SSEResponse(event_stream())

        # 또는 간단히
        async def simple_stream():
            for i in range(10):
                yield {"count": i}  # 자동으로 JSON 직렬화
                await asyncio.sleep(1)

        return SSEResponse(simple_stream())
    """

    def __init__(
        self,
        content: AsyncIterable[SSEEvent | dict | str],
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._headers = dict(headers) if headers else {}
        self._content = content

        # SSE 필수 헤더
        self._headers["content-type"] = "text/event-stream"
        self._headers["cache-control"] = "no-cache"
        self._headers["connection"] = "keep-alive"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI SSE 응답 전송"""
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )

        # Callable이면 호출
        content = self._content
        if callable(content):
            content = content()

        async for event in content:
            # 이벤트 직렬화
            data = self._serialize_event(event)
            await send(
                {
                    "type": "http.response.body",
                    "body": data,
                    "more_body": True,
                }
            )

        await send(
            {
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            }
        )

    def _serialize_event(self, event: Any) -> bytes:
        """이벤트를 SSE 형식으로 직렬화"""
        if isinstance(event, SSEEvent):
            return event.encode()
        elif isinstance(event, dict):
            # dict는 data로 JSON 직렬화
            return SSEEvent(data=json.dumps(event, ensure_ascii=False)).encode()
        elif isinstance(event, str):
            return SSEEvent(data=event).encode()
        else:
            return SSEEvent(data=str(event)).encode()


class SSEEvent:
    """
    Server-Sent Event 데이터 객체.

    SSE 프로토콜에 따른 이벤트를 표현합니다.

    사용 예:
        event = SSEEvent(
            data="Hello, World!",
            event="message",
            id="1",
            retry=3000,
        )
    """

    def __init__(
        self,
        data: str = "",
        event: str | None = None,
        id: str | None = None,
        retry: int | None = None,
    ) -> None:
        self.data = data
        self.event = event
        self.id = id
        self.retry = retry

    def encode(self) -> bytes:
        """SSE 형식으로 인코딩"""
        lines: list[str] = []

        if self.id is not None:
            lines.append(f"id: {self.id}")

        if self.event is not None:
            lines.append(f"event: {self.event}")

        if self.retry is not None:
            lines.append(f"retry: {self.retry}")

        # 데이터는 여러 줄일 수 있음
        for line in self.data.split("\n"):
            lines.append(f"data: {line}")

        # 이벤트 종료 (빈 줄)
        lines.append("")
        lines.append("")

        return "\n".join(lines).encode("utf-8")

    def __repr__(self) -> str:
        return f"<SSEEvent event={self.event!r} data={self.data[:50]!r}...>"
