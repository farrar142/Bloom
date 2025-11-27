"""모델 파라미터 리졸버 (dataclass, BaseModel)"""

from dataclasses import is_dataclass
from typing import Any

from vessel.web.http import HttpRequest

from ..base import ParameterResolver


class ModelParamResolver(ParameterResolver):
    """
    dataclass 또는 pydantic BaseModel 파라미터 리졸버

    RequestBody 마커 없이 선언된 dataclass/BaseModel 타입 파라미터의
    값을 request body에서 파라미터 이름을 키로 추출합니다.

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

    비교:
        - RequestBody[T]: body 전체를 T로 변환
        - T (마커 없음): body[param_name]을 T로 변환
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # Generic이 아닌 단순 타입만 처리
        if origin is not None:
            return False

        # dataclass 확인
        if is_dataclass(param_type):
            return True

        # pydantic BaseModel 확인
        if hasattr(param_type, "model_validate") and hasattr(
            param_type, "model_fields"
        ):
            return True

        return False

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        # body에서 파라미터 이름으로 값 추출
        body = request.json
        if body is None or not isinstance(body, dict):
            return None

        data = body.get(param_name)
        if data is None:
            return None

        return self._create_instance(param_type, data)

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
