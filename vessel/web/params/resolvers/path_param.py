"""경로 파라미터 리졸버"""

from typing import Any

from vessel.web.http import HttpRequest

from ..base import ParameterResolver
from ..registry import UNRESOLVED


class PathParamResolver(ParameterResolver):
    """
    경로 파라미터 리졸버

    path_params에 있는 값을 타입에 맞게 변환합니다.
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

        value = path_params[param_name]

        # 타입 변환
        if param_type is int:
            return int(value)
        elif param_type is float:
            return float(value)
        elif param_type is bool:
            return value.lower() in ("true", "1", "yes")

        return value
