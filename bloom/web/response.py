"""bloom.web.response - HTTP Response Objects"""

from __future__ import annotations

import json
from typing import Any, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .types import Send


class Response:
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
        return content.encode(self.charset)

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

    def set_header(self, name: str, value: str) -> "Response":
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
    ) -> "Response":
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
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })
        await send({
            "type": "http.response.body",
            "body": self.body,
        })

    def __repr__(self) -> str:
        return f"<Response {self.status_code}>"


class JSONResponse(Response):
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


class HTMLResponse(Response):
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


class PlainTextResponse(Response):
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


class RedirectResponse(Response):
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


class StreamingResponse(Response):
    """스트리밍 응답"""

    def __init__(
        self,
        content: Any,  # AsyncIterable[bytes]
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

    async def __call__(self, scope: Any, receive: Any, send: "Send") -> None:
        """ASGI 스트리밍 응답 전송"""
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })
        
        async for chunk in self._content:
            await send({
                "type": "http.response.body",
                "body": chunk,
                "more_body": True,
            })
        
        await send({
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        })
