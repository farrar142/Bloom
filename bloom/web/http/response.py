"""HTTP 응답 모델"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HttpResponse:
    """HTTP 응답 객체"""

    status_code: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = "application/json"

    @classmethod
    def ok(cls, body: Any = None) -> "HttpResponse":
        """200 OK 응답"""
        return cls(status_code=200, body=body)

    @classmethod
    def created(cls, body: Any = None) -> "HttpResponse":
        """201 Created 응답"""
        return cls(status_code=201, body=body)

    @classmethod
    def no_content(cls) -> "HttpResponse":
        """204 No Content 응답"""
        return cls(status_code=204)

    @classmethod
    def bad_request(cls, message: str = "Bad Request") -> "HttpResponse":
        """400 Bad Request 응답"""
        return cls(status_code=400, body={"error": message})

    @classmethod
    def unauthorized(cls, message: str = "Unauthorized") -> "HttpResponse":
        """401 Unauthorized 응답"""
        return cls(status_code=401, body={"error": message})

    @classmethod
    def forbidden(cls, message: str = "Forbidden") -> "HttpResponse":
        """403 Forbidden 응답"""
        return cls(status_code=403, body={"error": message})

    @classmethod
    def not_found(cls, message: str = "Not Found") -> "HttpResponse":
        """404 Not Found 응답"""
        return cls(status_code=404, body={"error": message})

    @classmethod
    def internal_error(cls, message: str = "Internal Server Error") -> "HttpResponse":
        """500 Internal Server Error 응답"""
        return cls(status_code=500, body={"error": message})

    def to_json(self) -> bytes:
        """JSON 직렬화"""
        import json

        if self.body is None:
            return b""
        return json.dumps(self.body, ensure_ascii=False).encode("utf-8")

    def to_bytes(self) -> bytes:
        """응답 본문을 바이트로 변환

        content_type에 따라 적절한 직렬화 방법 사용:
        - application/json: JSON 직렬화
        - text/*, application/xml 등: 문자열 인코딩
        - 기타: 바이트 그대로 반환 또는 JSON 직렬화
        """
        import json

        if self.body is None:
            return b""

        # 이미 바이트인 경우
        if isinstance(self.body, bytes):
            return self.body

        # content_type에 따라 분기
        ct = self.content_type.lower()

        # text/* (text/html, text/plain, text/css 등) 또는 XML 계열
        if ct.startswith("text/") or "xml" in ct:
            if isinstance(self.body, str):
                return self.body.encode("utf-8")
            # 문자열이 아니면 str()로 변환
            return str(self.body).encode("utf-8")

        # application/json 또는 기타 (JSON 직렬화)
        return json.dumps(self.body, ensure_ascii=False).encode("utf-8")
