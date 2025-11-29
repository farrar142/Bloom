"""RouteEntry - HTTP 라우트 정보

HttpMethodHandlerContainer와 라우트 정보(method, full path)를 담는 값 객체입니다.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bloom.web.handler import HttpMethodHandlerContainer


@dataclass
class RouteEntry:
    """
    HTTP 라우트 정보

    HttpMethodHandlerContainer와 라우트 정보를 담는 값 객체입니다.

    Attributes:
        method: HTTP 메서드 (GET, POST, PUT, DELETE 등)
        path: 전체 경로 (Controller prefix + handler path)
        handler: HttpMethodHandlerContainer 인스턴스

    사용 예시:
        entry = RouteEntry("GET", "/api/users/{id}", handler)
        print(entry.method)  # "GET"
        print(entry.path)    # "/api/users/{id}"
    """

    method: str
    path: str
    handler: "HttpMethodHandlerContainer"

    def __repr__(self) -> str:
        return f"RouteEntry({self.method} {self.path})"


__all__ = ["RouteEntry"]
