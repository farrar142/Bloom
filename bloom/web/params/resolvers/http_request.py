"""HttpRequest 리졸버"""

from typing import Any

from bloom.web.http import HttpRequest

from ..base import ParameterResolver, is_optional, unwrap_optional


class HttpRequestResolver(ParameterResolver):
    """
    HttpRequest 자체를 주입하는 리졸버
    Optional[HttpRequest] 지원 (항상 값 있음).
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        if is_optional(param_type):
            return unwrap_optional(param_type) is HttpRequest
        return param_type is HttpRequest

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        return request
