"""HTTP 요청 모델"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bloom.web.auth import Authentication
    from bloom.web.params.types import UploadedFile


@dataclass
class HttpRequest:
    """HTTP 요청 객체"""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    files: dict[str, list[UploadedFile]] = field(default_factory=dict)
    auth: "Authentication | None" = None

    @property
    def json(self) -> Any:
        """JSON 바디 파싱"""
        import json

        if self.body:
            return json.loads(self.body.decode("utf-8"))
        return None

    @property
    def text(self) -> str:
        """텍스트 바디"""
        return self.body.decode("utf-8") if self.body else ""
