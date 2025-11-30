"""경로 파라미터 리졸버"""

from enum import Enum
from typing import Any

from bloom.core.exceptions import TypeConversionError
from bloom.web.http import HttpRequest
from bloom.web.params.context import ResolverContext

from ..base import ParameterResolver
from ..registry import UNRESOLVED


class PathParamResolver(ParameterResolver):
    """
    경로 파라미터 리졸버

    path_params에 있는 값을 타입에 맞게 변환합니다.
    HTTP와 WebSocket 컨텍스트 모두에서 동작합니다.
    Enum 타입도 지원합니다.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # 기본 타입이고 origin이 없을 때 (str, int, float 등)
        if origin is None and param_type in (str, int, float, bool):
            return True
        # Enum 타입 지원
        if isinstance(param_type, type) and issubclass(param_type, Enum):
            return True
        return False

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

        return self._convert_value(path_params[param_name], param_type, param_name)

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

        return self._convert_value(path_params[param_name], param_type, param_name)

    def _convert_value(self, value: str, param_type: type, param_name: str = "") -> Any:
        """문자열 값을 지정된 타입으로 변환"""
        try:
            if param_type is int:
                return int(value)
            elif param_type is float:
                return float(value)
            elif param_type is bool:
                return value.lower() in ("true", "1", "yes")
            elif isinstance(param_type, type) and issubclass(param_type, Enum):
                # Enum: 값 또는 이름으로 변환 시도
                # int Enum인 경우 int로 먼저 변환
                if issubclass(param_type, int):
                    try:
                        return param_type(int(value))
                    except (ValueError, KeyError):
                        return param_type[value]
                # str Enum 또는 일반 Enum
                try:
                    return param_type(value)
                except ValueError:
                    # value로 실패하면 name으로 시도
                    return param_type[value]
            return value
        except (ValueError, KeyError) as e:
            raise TypeConversionError(param_name, param_type, value) from e
