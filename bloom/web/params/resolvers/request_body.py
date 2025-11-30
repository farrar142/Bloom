"""RequestBody[T] 리졸버"""

from dataclasses import is_dataclass
from typing import Annotated, Any, get_args

from bloom.core.exceptions import ValidationError
from bloom.web.http import HttpRequest

from ..base import ParameterResolver


class RequestBodyResolver(ParameterResolver):
    """
    RequestBody[T] 파라미터 리졸버

    요청 바디를 JSON으로 파싱하여 T 타입으로 변환합니다.
    T가 pydantic BaseModel이면 model_validate 사용,
    dataclass면 필드 매핑으로 생성합니다.

    pydantic ValidationError 발생 시 Bloom ValidationError로 변환하여
    필드별 상세 에러 정보를 제공합니다.
    """

    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        # RequestBody[T]는 Annotated[RequestBodyType, T] 형태
        if origin is Annotated:
            args = get_args(param_type)
            # args[0]이 RequestBodyType인지 확인
            if args and hasattr(args[0], "__name__"):
                return args[0].__name__ == "RequestBodyType"
        return False

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> Any:
        # Annotated[RequestBodyType, T]에서 T 추출
        args = get_args(param_type)
        if not args or len(args) < 2:
            return request.json

        # args[1]이 실제 타입 (T)
        target_type = args[1]
        data = request.json

        return self._convert_to_type(data, target_type)

    def _convert_to_type(self, data: Any, target_type: type) -> Any:
        """데이터를 타겟 타입으로 변환

        pydantic ValidationError 발생 시 Bloom ValidationError로 변환합니다.
        """
        if data is None:
            return None

        # pydantic BaseModel 확인
        if hasattr(target_type, "model_validate"):
            try:
                return target_type.model_validate(data)
            except Exception as e:
                # pydantic.ValidationError인지 확인 (타입 import 없이)
                if type(e).__name__ == "ValidationError" and hasattr(e, "errors"):
                    raise ValidationError.from_pydantic(e, loc_prefix=("body",))
                raise

        # dataclass 확인
        if is_dataclass(target_type):
            try:
                return target_type(**data)
            except TypeError as e:
                # dataclass 생성 실패 시 ValidationError로 변환
                raise ValidationError(
                    detail=f"Failed to create {target_type.__name__}: {e}",
                    errors=[
                        {
                            "loc": ["body"],
                            "msg": str(e),
                            "type": "dataclass_error",
                        }
                    ],
                )

        # 기본 타입이면 그대로 반환
        return data
