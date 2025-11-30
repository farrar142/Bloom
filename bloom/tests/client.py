"""HTTP 테스트 클라이언트

TestClient는 ASGI 애플리케이션을 직접 호출하여 HTTP 요청을 시뮬레이션합니다.
실제 네트워크 연결 없이 빠른 테스트가 가능합니다.

사용 예시:
    ```python
    from bloom import Application
    from bloom.tests import TestClient

    app = Application("test").scan(__name__).ready()

    async with TestClient(app) as client:
        response = await client.get("/users")
        assert response.status_code == 200
        assert response.json() == [{"id": 1, "name": "Alice"}]
    ```
"""

from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from urllib.parse import urlencode, urlparse, parse_qs

if TYPE_CHECKING:
    from bloom.application import Application


@dataclass
class TestResponse:
    """
    테스트 응답 래퍼

    Attributes:
        status_code: HTTP 상태 코드
        headers: 응답 헤더
        body: 원본 바이트 바디
    """

    # pytest가 테스트 클래스로 수집하지 않도록 설정
    __test__ = False

    status_code: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> Any:
        """JSON으로 파싱"""
        return json.loads(self.body.decode("utf-8"))

    def text(self) -> str:
        """텍스트로 디코딩"""
        return self.body.decode("utf-8")

    @property
    def content_type(self) -> str:
        """Content-Type 헤더"""
        return self.headers.get("content-type", "")

    @property
    def is_success(self) -> bool:
        """2xx 상태 코드 여부"""
        return 200 <= self.status_code < 300

    @property
    def is_redirect(self) -> bool:
        """3xx 상태 코드 여부"""
        return 300 <= self.status_code < 400

    @property
    def is_client_error(self) -> bool:
        """4xx 상태 코드 여부"""
        return 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        """5xx 상태 코드 여부"""
        return 500 <= self.status_code < 600


class TestClient:
    """
    ASGI 테스트 클라이언트

    실제 네트워크 없이 ASGI 애플리케이션을 직접 호출합니다.

    사용법:
        ```python
        # 컨텍스트 매니저 사용 (권장)
        async with TestClient(app) as client:
            response = await client.get("/api/users")
            assert response.status_code == 200

        # 직접 사용
        client = TestClient(app)
        response = await client.get("/api/users")
        ```

    Attributes:
        app: Bloom Application 인스턴스
        base_url: 기본 URL (기본: "http://testserver")
        default_headers: 모든 요청에 포함될 기본 헤더
    """

    # pytest가 테스트 클래스로 수집하지 않도록 설정
    __test__ = False

    def __init__(
        self,
        app: "Application",
        base_url: str = "http://testserver",
        default_headers: dict[str, str] | None = None,
    ):
        self.app = app
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {}
        self._cookies: dict[str, str] = {}

    async def __aenter__(self) -> "TestClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def set_cookie(self, key: str, value: str) -> None:
        """쿠키 설정"""
        self._cookies[key] = value

    def clear_cookies(self) -> None:
        """모든 쿠키 제거"""
        self._cookies.clear()

    async def request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
        json_body: Any = None,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> TestResponse:
        """
        HTTP 요청 전송

        Args:
            method: HTTP 메서드 (GET, POST, PUT, DELETE 등)
            path: 요청 경로
            headers: 추가 헤더
            query_params: 쿼리 파라미터
            json_body: JSON 바디 (자동으로 직렬화)
            body: 원시 바디 바이트
            content_type: Content-Type 헤더

        Returns:
            TestResponse 객체
        """
        # URL 파싱
        if path.startswith("http"):
            parsed = urlparse(path)
            path = parsed.path
            if parsed.query:
                existing_params = parse_qs(parsed.query)
                query_params = {
                    **(query_params or {}),
                    **{k: v[0] for k, v in existing_params.items()},
                }

        # 쿼리 스트링 구성
        query_string = ""
        if query_params:
            query_string = urlencode(query_params)

        # 헤더 구성
        request_headers: list[tuple[bytes, bytes]] = []

        # 기본 헤더
        all_headers = {**self.default_headers, **(headers or {})}

        # JSON 바디 처리
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            all_headers.setdefault("content-type", "application/json")

        # Content-Type 설정
        if content_type:
            all_headers["content-type"] = content_type

        # 쿠키 헤더
        if self._cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
            all_headers["cookie"] = cookie_str

        # 헤더 변환
        for key, value in all_headers.items():
            request_headers.append((key.lower().encode(), value.encode()))

        # Host 헤더 추가
        parsed_base = urlparse(self.base_url)
        host = parsed_base.netloc or "testserver"
        request_headers.append((b"host", host.encode()))

        # ASGI scope 구성
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method.upper(),
            "path": path,
            "query_string": query_string.encode(),
            "root_path": "",
            "headers": request_headers,
            "server": (host, 80),
        }

        # 응답 수집
        response_started = False
        status_code = 0
        response_headers: dict[str, str] = {}
        body_parts: list[bytes] = []

        async def receive():
            """요청 바디 전송"""
            return {
                "type": "http.request",
                "body": body or b"",
                "more_body": False,
            }

        async def send(message: dict[str, Any]):
            nonlocal response_started, status_code, response_headers

            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                for key, value in message.get("headers", []):
                    header_key = key.decode() if isinstance(key, bytes) else key
                    header_value = value.decode() if isinstance(value, bytes) else value
                    response_headers[header_key.lower()] = header_value

            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))

        # ASGI 앱 호출
        await self.app.asgi(scope, receive, send)

        # 응답 쿠키 저장
        if "set-cookie" in response_headers:
            cookie_header = response_headers["set-cookie"]
            # 간단한 쿠키 파싱 (name=value 부분만)
            parts = cookie_header.split(";")
            if parts:
                name_value = parts[0].strip()
                if "=" in name_value:
                    name, value = name_value.split("=", 1)
                    self._cookies[name] = value

        return TestResponse(
            status_code=status_code,
            headers=response_headers,
            body=b"".join(body_parts),
        )

    async def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> TestResponse:
        """GET 요청"""
        return await self.request(
            "GET", path, headers=headers, query_params=query_params
        )

    async def post(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
        json_body: Any = None,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> TestResponse:
        """POST 요청"""
        return await self.request(
            "POST",
            path,
            headers=headers,
            query_params=query_params,
            json_body=json_body,
            body=body,
            content_type=content_type,
        )

    async def put(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
        json_body: Any = None,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> TestResponse:
        """PUT 요청"""
        return await self.request(
            "PUT",
            path,
            headers=headers,
            query_params=query_params,
            json_body=json_body,
            body=body,
            content_type=content_type,
        )

    async def patch(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
        json_body: Any = None,
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> TestResponse:
        """PATCH 요청"""
        return await self.request(
            "PATCH",
            path,
            headers=headers,
            query_params=query_params,
            json_body=json_body,
            body=body,
            content_type=content_type,
        )

    async def delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> TestResponse:
        """DELETE 요청"""
        return await self.request(
            "DELETE", path, headers=headers, query_params=query_params
        )

    async def head(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """HEAD 요청"""
        return await self.request("HEAD", path, headers=headers)

    async def options(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """OPTIONS 요청"""
        return await self.request("OPTIONS", path, headers=headers)
