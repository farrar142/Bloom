"""Authentication 리졸버"""

from typing import Any, TYPE_CHECKING

from bloom.web.auth import Authentication

from ..base import ParameterResolver, is_optional, unwrap_optional

if TYPE_CHECKING:
    from bloom.web.http import HttpRequest
    from bloom.web.params.context import ResolverContext


class AuthenticationResolver(ParameterResolver):
    """
    Authentication 객체를 주입하는 리졸버

    HTTP: HttpRequest.auth 속성에서 Authentication을 추출
    WebSocket: WebSocketSession.authentication 속성에서 Authentication을 추출

    AuthMiddleware가 먼저 실행되어 인증이 설정되어 있어야 합니다.
    Optional[Authentication]인 경우 None을 허용합니다.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        if is_optional(param_type):
            return unwrap_optional(param_type) is Authentication
        return param_type is Authentication

    async def resolve_with_context(
        self,
        param_name: str,
        param_type: type,
        context: "ResolverContext",
    ) -> Any:
        """통합 컨텍스트에서 Authentication 추출"""
        if context.is_http and context.http_request:
            return context.http_request.auth
        if context.is_websocket and context.websocket_session:
            return context.websocket_session.authentication
        return None

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: "HttpRequest",
        path_params: dict[str, str],
    ) -> Any:
        return request.auth
