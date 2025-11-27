"""Authentication 리졸버"""

from typing import Any

from vessel.web.http import HttpRequest
from vessel.web.auth import Authentication

from ..base import ParameterResolver, is_optional, unwrap_optional


class AuthenticationResolver(ParameterResolver):
    """
    Authentication 객체를 주입하는 리졸버

    HttpRequest.auth 속성에서 Authentication을 추출하여 핸들러에 주입합니다.
    AuthMiddleware가 먼저 실행되어 request.auth가 설정되어 있어야 합니다.

    Optional[Authentication]인 경우 None을 허용합니다.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        if is_optional(param_type):
            return unwrap_optional(param_type) is Authentication
        return param_type is Authentication

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        return request.auth
