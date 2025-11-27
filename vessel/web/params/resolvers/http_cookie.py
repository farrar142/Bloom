"""HTTP 쿠키 리졸버"""

from vessel.web.http import HttpRequest

from ..types import HttpCookie
from .key_value import KeyValueResolver


class HttpCookieResolver(KeyValueResolver[HttpCookie]):
    """
    HttpCookie 파라미터 리졸버

    사용법:
        # 파라미터 이름으로 쿠키 키 추론
        async def handler(self, session_id: HttpCookie) -> str:
            print(session_id.key)    # "session_id"
            print(session_id.value)  # "abc123"

        # 정확한 쿠키 키 지정
        async def handler(self, sid: HttpCookie["session_id"]) -> str:
            print(sid.key)    # "session_id"
            print(sid.value)  # "abc123"
    """

    @property
    def target_type(self) -> type[HttpCookie]:
        return HttpCookie

    def _extract_value(self, request: HttpRequest, key: str) -> str | None:
        """쿠키에서 값 추출"""
        cookies = self._parse_cookies(request)
        return cookies.get(key)

    def _parse_cookies(self, request: HttpRequest) -> dict[str, str]:
        """Cookie 헤더 파싱"""
        cookie_header = request.headers.get("cookie", "")
        if not cookie_header:
            return {}

        cookies = {}
        for item in cookie_header.split(";"):
            item = item.strip()
            if "=" in item:
                key, value = item.split("=", 1)
                cookies[key.strip()] = value.strip()

        return cookies
