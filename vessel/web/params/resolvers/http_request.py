"""HttpRequest 리졸버"""

from typing import Any

from vessel.web.http import HttpRequest

from ..base import ParameterResolver


class HttpRequestResolver(ParameterResolver):
    """
    HttpRequest 자체를 주입하는 리졸버
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        return param_type is HttpRequest

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        return request
