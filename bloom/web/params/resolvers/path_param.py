"""경로 파라미터 리졸버"""

from typing import Any

from bloom.web.http import HttpRequest
from bloom.web.params.context import ResolverContext

from ..base import ParameterResolver
from ..registry import UNRESOLVED


class PathParamResolver(ParameterResolver):
    """
    경로 파라미터 리졸버

    path_params에 있는 값을 타입에 맞게 변환합니다.
    HTTP와 WebSocket 컨텍스트 모두에서 동작합니다.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # 기본 타입이고 origin이 없을 때 (str, int, float 등)
        return origin is None and param_type in (str, int, float, bool)

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        # path_params에 없으면 UNRESOLVED 반환하여 다음 리졸버 시도
        if param_name not in path_params:
            return UNRESOLVED

        return self._convert_value(path_params[param_name], param_type)

    async def resolve_with_context(
        self,
        param_name: str,
        param_type: type,
        context: ResolverContext,
    ) -> Any:
        """통합 컨텍스트를 사용한 경로 파라미터 해석 (HTTP/WebSocket 모두 지원)"""
        path_params = context.path_params

        if param_name not in path_params:
            return UNRESOLVED

        return self._convert_value(path_params[param_name], param_type)

    def _convert_value(self, value: str, param_type: type) -> Any:
        """문자열 값을 지정된 타입으로 변환"""
        if param_type is int:
            return int(value)
        elif param_type is float:
            return float(value)
        elif param_type is bool:
            return value.lower() in ("true", "1", "yes")
        return value
