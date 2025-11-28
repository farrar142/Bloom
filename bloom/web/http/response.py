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
