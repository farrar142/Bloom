"""모델 파라미터 리졸버 (dataclass, BaseModel)"""

from dataclasses import is_dataclass
from typing import Any

from bloom.web.http import HttpRequest

from ..base import ParameterResolver, is_optional, unwrap_optional


def _is_model_type(t: type) -> bool:
    """dataclass 또는 pydantic BaseModel인지 확인"""
    if is_dataclass(t):
        return True
    if hasattr(t, "model_validate") and hasattr(t, "model_fields"):
        return True
    return False


class ModelParamResolver(ParameterResolver):
    """
    dataclass 또는 pydantic BaseModel 파라미터 리졸버

    RequestBody 마커 없이 선언된 dataclass/BaseModel 타입 파라미터의
    값을 request body에서 파라미터 이름을 키로 추출합니다.
    Optional[T] 지원: 값이 없으면 None 반환.

    사용법:
        @dataclass
        class UserData:
            name: str
            age: int

        @Post("/users")
        async def create(self, data: UserData) -> dict:
            return {"name": data.name}

        # POST body: {"data": {"name": "Alice", "age": 30}}
        # -> data = UserData(name="Alice", age=30)

        # Optional
        async def create(self, data: UserData | None) -> dict:
            if data is None:
                return {"error": "no data"}

    비교:
        - RequestBody[T]: body 전체를 T로 변환
        - T (마커 없음): body[param_name]을 T로 변환
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # Optional[T] 처리
        if is_optional(param_type):
            inner_type = unwrap_optional(param_type)
            return _is_model_type(inner_type)

        # Generic이 아닌 단순 타입만 처리
        if origin is not None:
            return False

        return _is_model_type(param_type)

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

        # body에서 파라미터 이름으로 값 추출
        body = request.json
        if body is None or not isinstance(body, dict):
            return None

        data = body.get(param_name)
        if data is None:
            return None

        return self._create_instance(actual_type, data)

    def _create_instance(self, param_type: type, data: Any) -> Any:
        """타입 인스턴스 생성"""
        if data is None:
            return None

        # pydantic BaseModel
        if hasattr(param_type, "model_validate"):
            return param_type.model_validate(data)

        # dataclass
        if is_dataclass(param_type) and isinstance(data, dict):
            return param_type(**data)

        return data
