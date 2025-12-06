"""bloom.web.request - HTTP Request Object"""

import json
from typing import Any, TYPE_CHECKING
from urllib.parse import parse_qs, unquote

from .types import Scope, Receive


class HttpRequest:
    """
    HTTP Request 객체.

    ASGI scope에서 요청 정보를 추출하여 제공합니다.

    사용 예:
        request = Request(scope, receive)
        print(request.method)  # GET
        print(request.path)    # /users/123
        print(request.query_params)  # {"page": ["1"]}
    """

    def __init__(self, scope: "Scope", receive: "Receive") -> None:
        self._scope = scope
        self._receive = receive
        self._body: bytes | None = None
        self._json: Any = None
        self._form: dict[str, Any] | None = None

    # === Basic Properties ===

    @property
    def method(self) -> str:
        """HTTP 메서드 (GET, POST, PUT, DELETE 등)"""
        return self._scope.get("method", "GET")

    @property
    def path(self) -> str:
        """요청 경로 (예: /users/123)"""
        return self._scope.get("path", "/")

    @property
    def query_string(self) -> bytes:
        """쿼리 스트링 (raw bytes)"""
        return self._scope.get("query_string", b"")

    @property
    def query_params(self) -> dict[str, list[str]]:
        """쿼리 파라미터 (파싱된 딕셔너리)"""
        return parse_qs(self.query_string.decode("utf-8"))

    def query_param(self, name: str, default: str | None = None) -> str | None:
        """단일 쿼리 파라미터 값 조회"""
        values = self.query_params.get(name)
        if values:
            return values[0]
        return default

    # === Headers ===

    @property
    def headers(self) -> dict[str, str]:
        """HTTP 헤더 (소문자 키)"""
        raw_headers = self._scope.get("headers", [])
        return {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in raw_headers
        }

    def header(self, name: str, default: str | None = None) -> str | None:
        """단일 헤더 값 조회 (대소문자 무관)"""
        return self.headers.get(name.lower(), default)

    @property
    def content_type(self) -> str | None:
        """Content-Type 헤더"""
        return self.header("content-type")

    @property
    def content_length(self) -> int | None:
        """Content-Length 헤더"""
        length = self.header("content-length")
        return int(length) if length else None

    # === Cookies ===

    @property
    def cookies(self) -> dict[str, str]:
        """쿠키 딕셔너리"""
        cookie_header = self.header("cookie", "")
        if not cookie_header:
            return {}

        cookies: dict[str, str] = {}
        for item in cookie_header.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()
        return cookies

    def cookie(self, name: str, default: str | None = None) -> str | None:
        """단일 쿠키 값 조회"""
        return self.cookies.get(name, default)

    # === Client Info ===

    @property
    def client(self) -> tuple[str, int] | None:
        """클라이언트 (host, port)"""
        return self._scope.get("client")

    @property
    def client_host(self) -> str | None:
        """클라이언트 IP"""
        client = self.client
        return client[0] if client else None

    # === URL Components ===

    @property
    def scheme(self) -> str:
        """URL 스킴 (http, https)"""
        return self._scope.get("scheme", "http")

    @property
    def server(self) -> tuple[str, int] | None:
        """서버 (host, port)"""
        return self._scope.get("server")

    @property
    def url(self) -> str:
        """전체 URL"""
        scheme = self.scheme
        server = self.server
        path = self.path
        query = self.query_string.decode("utf-8")

        if server:
            host, port = server
            # 기본 포트는 생략
            if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
                url = f"{scheme}://{host}{path}"
            else:
                url = f"{scheme}://{host}:{port}{path}"
        else:
            url = path

        if query:
            url = f"{url}?{query}"

        return url

    # === Path Parameters ===

    @property
    def path_params(self) -> dict[str, str]:
        """경로 파라미터 (라우터에서 설정)"""
        return self._scope.get("path_params", {})

    def path_param(self, name: str, default: str | None = None) -> str | None:
        """단일 경로 파라미터 값 조회"""
        value = self.path_params.get(name, default)
        return unquote(value) if value else default

    # === Body ===

    async def body(self) -> bytes:
        """요청 본문 (raw bytes)"""
        if self._body is None:
            chunks: list[bytes] = []
            while True:
                message = await self._receive()
                body = message.get("body", b"")
                if body:
                    chunks.append(body)
                if not message.get("more_body", False):
                    break
            self._body = b"".join(chunks)
        return self._body

    async def text(self) -> str:
        """요청 본문 (문자열)"""
        body = await self.body()
        return body.decode("utf-8")

    async def json(self) -> Any:
        """요청 본문 (JSON 파싱)"""
        if self._json is None:
            text = await self.text()
            self._json = json.loads(text) if text else None
        return self._json

    # === State ===

    @property
    def state(self) -> dict[str, Any]:
        """요청 상태 (미들웨어에서 데이터 전달용)"""
        if "state" not in self._scope:
            self._scope["state"] = {}
        return self._scope["state"]

    # === ASGI Scope Access ===

    @property
    def scope(self) -> "Scope":
        """원본 ASGI scope"""
        return self._scope

    def __repr__(self) -> str:
        return f"<Request {self.method} {self.path}>"
