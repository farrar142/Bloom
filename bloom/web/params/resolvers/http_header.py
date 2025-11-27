"""HTTP 헤더 리졸버"""

from bloom.web.http import HttpRequest

from ..types import HttpHeader
from .key_value import KeyValueResolver


class HttpHeaderResolver(KeyValueResolver[HttpHeader]):
    """
    HttpHeader 파라미터 리졸버

    사용법:
        # 파라미터 이름으로 헤더 키 추론 (user_agent -> user-agent)
        async def handler(self, user_agent: HttpHeader) -> str:
            print(user_agent.key)    # "user-agent"
            print(user_agent.value)  # "Mozilla/5.0..."

        # 정확한 헤더 키 지정
        async def handler(self, ua: HttpHeader["User-Agent"]) -> str:
            print(ua.key)    # "User-Agent"
            print(ua.value)  # "Mozilla/5.0..."
    """

    @property
    def target_type(self) -> type[HttpHeader]:
        return HttpHeader

    def _transform_param_name(self, param_name: str) -> str:
        """파라미터 이름을 헤더 키로 변환 (user_agent -> user-agent)"""
        return param_name.replace("_", "-")

    def _extract_value(self, request: HttpRequest, key: str) -> str | None:
        """헤더에서 값 추출 (대소문자 무시)"""
        return request.headers.get(key.lower())
