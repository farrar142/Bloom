"""list[T] 리졸버"""

from dataclasses import is_dataclass
from typing import Any, get_args

from vessel.web.http import HttpRequest

from ..base import ParameterResolver


class ListBodyResolver(ParameterResolver):
    """
    list[T] 파라미터 리졸버 (바디에서)

    요청 바디가 배열일 때 list[T]로 변환합니다.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        return origin is list

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        args = get_args(param_type)
        data = request.json

        if not isinstance(data, dict):
            # 바디 자체가 배열인 경우
            items = data if isinstance(data, list) else []
        else:
            # 바디에서 param_name 키로 찾기
            items = data.get(param_name, [])

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
