"""list[T] 리졸버"""

from dataclasses import is_dataclass
from typing import Any, get_args, get_origin

from bloom.web.http import HttpRequest

from ..base import ParameterResolver, is_optional, unwrap_optional


class ListBodyResolver(ParameterResolver):
    """
    list[T] 파라미터 리졸버 (바디에서)

    요청 바디가 배열일 때 list[T]로 변환합니다.
    Optional[list[T]] 지원.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # Optional[list[T]] 처리
        if is_optional(param_type):
            inner_type = unwrap_optional(param_type)
            return get_origin(inner_type) is list

        return origin is list

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        # Optional 처리
        optional = is_optional(param_type)
        actual_type = unwrap_optional(param_type) if optional else param_type

        args = get_args(actual_type)
        data = request.json

        if data is None:
            return None if optional else []

        if not isinstance(data, dict):
            # 바디 자체가 배열인 경우
            items = data if isinstance(data, list) else []
        else:
            # 바디에서 param_name 키로 찾기
            items = data.get(param_name)
            if items is None:
                return None if optional else []

        if not args:
            return items

        item_type = args[0]
        return [self._convert_item(item, item_type) for item in items]

    def _convert_item(self, item: Any, item_type: type) -> Any:
        """아이템을 타겟 타입으로 변환"""
        if hasattr(item_type, "model_validate"):
            return item_type.model_validate(item)

        if is_dataclass(item_type):
            return item_type(**item)

        return item
