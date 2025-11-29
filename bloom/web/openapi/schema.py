"""JSON Schema 생성기

Pydantic BaseModel 및 dataclass에서 JSON Schema를 생성합니다.
"""

from dataclasses import fields, is_dataclass
from typing import (
    Any,
    Annotated,
    Union,
    get_args,
    get_origin,
)
from types import NoneType, UnionType
import inspect


def _python_type_to_openapi(python_type: type) -> dict[str, Any]:
    """Python 타입을 OpenAPI 타입으로 변환"""
    # NoneType 처리
    if python_type is NoneType or python_type is type(None):
        return {"nullable": True}

    # 기본 타입 매핑
    type_mapping: dict[type, dict[str, str]] = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        bytes: {"type": "string", "format": "binary"},
    }

    if python_type in type_mapping:
        return type_mapping[python_type]

    # Any 타입
    if python_type is Any:
        return {}

    return {"type": "object"}


class SchemaGenerator:
    """
    JSON Schema 생성기

    Pydantic BaseModel, dataclass, 기본 타입에서 JSON Schema를 생성합니다.
    생성된 스키마는 OpenAPI components/schemas에 등록됩니다.
    """

    def __init__(self):
        # 스키마 캐시: type -> (schema_name, schema_dict)
        self._schemas: dict[type, tuple[str, dict[str, Any]]] = {}
        # $ref로 참조할 스키마 목록
        self._components: dict[str, dict[str, Any]] = {}

    @property
    def components(self) -> dict[str, dict[str, Any]]:
        """생성된 모든 스키마 (components/schemas용)"""
        return self._components

    def get_schema(self, python_type: type) -> dict[str, Any]:
        """
        Python 타입에서 JSON Schema 생성

        Args:
            python_type: 변환할 Python 타입

        Returns:
            JSON Schema dict ($ref 또는 인라인 스키마)
        """
        origin = get_origin(python_type)
        args = get_args(python_type)

        # None 타입
        if python_type is NoneType or python_type is type(None):
            return {"nullable": True}

        # Annotated 타입 처리
        if origin is Annotated:
            # Annotated[T, ...] -> T의 스키마 반환
            if args:
                return self.get_schema(args[0])
            return {}

        # Optional / Union 처리
        if origin is Union or origin is UnionType:
            non_none_types = [
                t for t in args if t is not NoneType and t is not type(None)
            ]
            if len(non_none_types) == 1:
                # Optional[T] -> T + nullable
                schema = self.get_schema(non_none_types[0])
                if "$ref" not in schema:
                    schema["nullable"] = True
                return schema
            else:
                # Union[A, B, ...] -> oneOf
                return {"oneOf": [self.get_schema(t) for t in non_none_types]}

        # list / List[T]
        if origin is list:
            item_schema = self.get_schema(args[0]) if args else {}
            return {"type": "array", "items": item_schema}

        # dict / Dict[K, V]
        if origin is dict:
            value_schema = self.get_schema(args[1]) if len(args) > 1 else {}
            return {
                "type": "object",
                "additionalProperties": value_schema if value_schema else True,
            }

        # 기본 타입
        if python_type in (str, int, float, bool, bytes):
            return _python_type_to_openapi(python_type)

        # Pydantic BaseModel
        if hasattr(python_type, "model_json_schema"):
            return self._get_pydantic_schema(python_type)

        # dataclass
        if is_dataclass(python_type):
            return self._get_dataclass_schema(python_type)

        # 알 수 없는 타입
        return {"type": "object"}

    def _get_pydantic_schema(self, model: type) -> dict[str, Any]:
        """Pydantic 모델에서 스키마 생성"""
        schema_name = model.__name__

        # 이미 캐시에 있으면 $ref 반환
        if model in self._schemas:
            return {"$ref": f"#/components/schemas/{schema_name}"}

        # Pydantic의 model_json_schema 사용
        try:
            json_schema = model.model_json_schema()  # type: ignore

            # $defs가 있으면 components에 추가하고 $ref 경로 변환
            if "$defs" in json_schema:
                for def_name, def_schema in json_schema.pop("$defs").items():
                    # 중첩된 $ref 경로도 변환
                    self._convert_refs(def_schema)
                    self._components[def_name] = def_schema

            # 메인 스키마의 $ref 경로 변환
            self._convert_refs(json_schema)

            # 메인 스키마 등록
            self._schemas[model] = (schema_name, json_schema)
            self._components[schema_name] = json_schema

            return {"$ref": f"#/components/schemas/{schema_name}"}
        except Exception:
            return {"type": "object"}

    def _convert_refs(self, schema: dict[str, Any]) -> None:
        """$defs 참조를 components/schemas 참조로 변환"""
        if not isinstance(schema, dict):
            return

        # $ref 경로 변환
        if "$ref" in schema:
            ref = schema["$ref"]
            if ref.startswith("#/$defs/"):
                schema["$ref"] = ref.replace("#/$defs/", "#/components/schemas/")

        # 중첩된 스키마도 처리
        for key, value in schema.items():
            if isinstance(value, dict):
                self._convert_refs(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._convert_refs(item)

    def _get_dataclass_schema(self, dc: type) -> dict[str, Any]:
        """dataclass에서 스키마 생성"""
        schema_name = dc.__name__

        # 이미 캐시에 있으면 $ref 반환
        if dc in self._schemas:
            return {"$ref": f"#/components/schemas/{schema_name}"}

        # dataclass 필드 분석
        properties: dict[str, Any] = {}
        required: list[str] = []

        for dc_field in fields(dc):
            field_schema = self.get_schema(dc_field.type)  # type: ignore
            properties[dc_field.name] = field_schema

            # 기본값이 없으면 required
            if dc_field.default is dc_field.default_factory:  # type: ignore
                # default와 default_factory 모두 없는 경우
                if dc_field.default is getattr(dc_field, "default", dc_field):
                    required.append(dc_field.name)

        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required

        self._schemas[dc] = (schema_name, schema)
        self._components[schema_name] = schema

        return {"$ref": f"#/components/schemas/{schema_name}"}

    def get_request_body_schema(self, param_type: type) -> dict[str, Any]:
        """RequestBody용 스키마 생성"""
        origin = get_origin(param_type)
        args = get_args(param_type)

        # Annotated[RequestBodyType, T] 처리
        if origin is Annotated and len(args) >= 2:
            actual_type = args[1]
            return self.get_schema(actual_type)

        return self.get_schema(param_type)

    def get_response_schema(self, return_type: type | None) -> dict[str, Any]:
        """응답 타입에서 스키마 생성"""
        if return_type is None or return_type is type(None):
            return {}

        # inspect.Parameter.empty 처리
        if return_type is inspect.Parameter.empty:
            return {}

        return self.get_schema(return_type)
