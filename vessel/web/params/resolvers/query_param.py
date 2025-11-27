"""쿼리 파라미터 리졸버"""

from typing import Any

from vessel.web.http import HttpRequest

from ..base import ParameterResolver, is_optional, unwrap_optional
from ..registry import UNRESOLVED


class QueryParamResolver(ParameterResolver):
    """
    쿼리 파라미터 및 바디 필드 리졸버

    다음 순서로 값을 찾습니다:
    1. query_params에서 검색
    2. body(JSON)에서 파라미터 이름으로 검색

    PathParamResolver보다 낮은 우선순위로 동작합니다.
    Optional[T] 지원: 값이 없으면 None 반환.

    사용법:
        @Post("/users")
        async def create(self, name: str, age: int) -> dict:
            return {"name": name, "age": age}

        # body: {"name": "Alice", "age": 30}
    """

    _SUPPORTED_TYPES = (str, int, float, bool)

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # Optional[T] 처리
        if is_optional(param_type):
            inner_type = unwrap_optional(param_type)
            return inner_type in self._SUPPORTED_TYPES

        # 기본 타입
        return origin is None and param_type in self._SUPPORTED_TYPES

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

        # Optional 처리
        optional = is_optional(param_type)
        actual_type = unwrap_optional(param_type) if optional else param_type

        # 1. query_params에서 찾기
        value = request.query_params.get(param_name)

        # 2. body(JSON)에서 찾기
        if value is None:
            body = request.json
            if isinstance(body, dict):
                value = body.get(param_name)

        if value is None:
            return None if optional else UNRESOLVED

        # 타입 변환
        return self._convert_value(value, actual_type)

    def _convert_value(self, value: Any, target_type: type) -> Any:
        """값을 타겟 타입으로 변환"""
        # 이미 올바른 타입이면 그대로 반환
        if isinstance(value, target_type):
            return value

        # 문자열에서 변환
        if target_type is int:
            return int(value)
        elif target_type is float:
            return float(value)
        elif target_type is bool:
            if isinstance(value, bool):
                return value
            return str(value).lower() in ("true", "1", "yes")

        return value
