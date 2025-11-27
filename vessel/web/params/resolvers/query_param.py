"""쿼리 파라미터 리졸버"""

from typing import Any

from vessel.web.http import HttpRequest

from ..base import ParameterResolver
from ..registry import UNRESOLVED


class QueryParamResolver(ParameterResolver):
    """
    쿼리 파라미터 리졸버

    query_params에서 값을 가져와 타입에 맞게 변환합니다.
    PathParamResolver보다 낮은 우선순위로 동작합니다.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # 기본 타입
        return origin is None and param_type in (str, int, float, bool)

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        # path_params에 있으면 UNRESOLVED (PathParamResolver가 처리해야 함)
        if param_name in path_params:
            return UNRESOLVED

        value = request.query_params.get(param_name)
        if value is None:
            return UNRESOLVED

        # 타입 변환
        if param_type is int:
            return int(value)
        elif param_type is float:
            return float(value)
        elif param_type is bool:
            return value.lower() in ("true", "1", "yes")

        return value
