"""RouteEntry - HTTP 라우트 Entry

HttpMethodHandler를 감싸는 Entry 클래스입니다.
"""

from typing import TYPE_CHECKING

from bloom.core.abstract import Entry

if TYPE_CHECKING:
    from bloom.web.handler import HttpMethodHandler


class RouteEntry(Entry["HttpMethodHandler"]):
    """
    HTTP 라우트 Entry

    HttpMethodHandler를 감싸고, 라우트 정보(method, path)를 포함합니다.

    Attributes:
        method: HTTP 메서드 (GET, POST, PUT, DELETE 등)
        path: 전체 경로 (prefix + handler path)
        handler: HttpMethodHandler 인스턴스

    사용 예시:
        entry = RouteEntry("GET", "/api/users", handler)
        print(entry.method)  # "GET"
        print(entry.path)    # "/api/users"
        print(entry.value)   # HttpMethodHandler
    """

    def __init__(
        self,
        method: str,
        path: str,
        handler: "HttpMethodHandler",
    ):
        super().__init__(handler)
        self._method = method
        self._path = path

    @property
    def method(self) -> str:
        """HTTP 메서드"""
        return self._method

    @property
    def path(self) -> str:
        """전체 경로"""
        return self._path

    @property
    def handler(self) -> "HttpMethodHandler":
        """HttpMethodHandler (value의 별칭)"""
        return self._value

    def __repr__(self) -> str:
        return f"RouteEntry({self._method} {self._path})"
