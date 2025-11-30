"""OpenAPI 생성기

RouteManager에서 라우트 정보를 수집하여 OpenAPI 스펙을 생성합니다.
"""

from enum import Enum
from typing import Any, TYPE_CHECKING, get_origin, get_args, Annotated
import inspect

if TYPE_CHECKING:
    from bloom.web.routing import RouteManager
    from bloom.web.handler import HttpMethodHandlerContainer

from .config import OpenAPIConfig
from .schema import SchemaGenerator


# HTTP 메서드별 상태 코드 기본값
DEFAULT_STATUS_CODES = {
    "GET": "200",
    "POST": "201",
    "PUT": "200",
    "PATCH": "200",
    "DELETE": "204",
}


class OpenAPIGenerator:
    """
    OpenAPI 스펙 생성기

    RouteManager의 라우트 정보를 분석하여 OpenAPI 3.0 스펙을 생성합니다.

    사용 예시:
        generator = OpenAPIGenerator(config)
        spec = generator.generate(route_manager)
    """

    def __init__(self, config: OpenAPIConfig | None = None):
        self.config = config or OpenAPIConfig()
        self.schema_generator = SchemaGenerator()

    def generate(self, route_manager: "RouteManager") -> dict[str, Any]:
        """
        OpenAPI 스펙 생성

        Args:
            route_manager: 라우트 정보를 담고 있는 RouteManager

        Returns:
            OpenAPI 3.0 스펙 딕셔너리
        """
        paths = self._generate_paths(route_manager)
        tags = self._collect_tags(route_manager)

        spec: dict[str, Any] = {
            "openapi": self.config.openapi_version,
            "info": self.config.get_info(),
            "paths": paths,
        }

        # 서버 정보
        if self.config.servers:
            spec["servers"] = self.config.get_servers()

        # 태그 정보 (config에서 + 자동 수집)
        all_tags = {t["name"]: t for t in self.config.get_tags()}
        for tag in tags:
            if tag["name"] not in all_tags:
                all_tags[tag["name"]] = tag
        if all_tags:
            spec["tags"] = list(all_tags.values())

        # 스키마 컴포넌트
        if self.schema_generator.components:
            spec["components"] = {"schemas": self.schema_generator.components}

        return spec

    def _generate_paths(self, route_manager: "RouteManager") -> dict[str, Any]:
        """경로별 operations 생성"""
        paths: dict[str, Any] = {}

        # RouteRegistry에서 모든 라우트 수집
        registry = route_manager.registry
        if not registry:
            return paths

        for entry in registry.all():
            path = self._convert_path_to_openapi(entry.path)
            method = entry.method.lower()
            handler = entry.handler

            if path not in paths:
                paths[path] = {}

            paths[path][method] = self._generate_operation(handler, entry.path)

        return paths

    def _convert_path_to_openapi(self, path: str) -> str:
        """
        Bloom 경로 형식을 OpenAPI 형식으로 변환

        /users/{id} -> /users/{id} (동일)
        /users/<id> -> /users/{id} (Flask 스타일 변환)
        """
        # Bloom은 이미 {param} 형식 사용
        return path

    def _generate_operation(
        self, handler: "HttpMethodHandlerContainer", path: str
    ) -> dict[str, Any]:
        """핸들러에서 operation 객체 생성"""
        operation: dict[str, Any] = {}

        # 핸들러 메서드 정보
        method_func = handler.handler_method
        method = handler.get_metadata("http_method")

        # 설명/요약 (docstring에서 추출)
        if method_func.__doc__:
            doc = method_func.__doc__.strip()
            lines = doc.split("\n")
            operation["summary"] = lines[0]
            if len(lines) > 1:
                operation["description"] = "\n".join(lines[1:]).strip()

        # operationId
        operation["operationId"] = self._generate_operation_id(handler)

        # 태그 (Controller 이름에서)
        tag = self._get_tag_from_handler(handler)
        if tag:
            operation["tags"] = [tag]

        # 파라미터 분석
        parameters, request_body = self._analyze_parameters(handler, path)
        if parameters:
            operation["parameters"] = parameters
        if request_body:
            operation["requestBody"] = request_body

        # 응답
        operation["responses"] = self._generate_responses(handler, method)

        return operation

    def _generate_operation_id(self, handler: "HttpMethodHandlerContainer") -> str:
        """operationId 생성"""
        method_name = handler.handler_method.__name__

        # owner_cls가 있으면 Controller 이름 포함
        if handler.owner_cls:
            controller_name = handler.owner_cls.__name__
            # Controller 접미사 제거
            if controller_name.endswith("Controller"):
                controller_name = controller_name[:-10]
            return f"{controller_name}_{method_name}"

        return method_name

    def _get_tag_from_handler(
        self, handler: "HttpMethodHandlerContainer"
    ) -> str | None:
        """핸들러에서 태그 추출 (Controller 이름)"""
        if handler.owner_cls:
            name = handler.owner_cls.__name__
            # Controller 접미사 제거
            if name.endswith("Controller"):
                name = name[:-10]
            return name
        return None

    def _collect_tags(self, route_manager: "RouteManager") -> list[dict[str, Any]]:
        """모든 핸들러에서 태그 수집"""
        tags: dict[str, dict[str, Any]] = {}

        registry = route_manager.registry
        if not registry:
            return []

        for entry in registry.all():
            handler = entry.handler
            tag = self._get_tag_from_handler(handler)
            if tag and tag not in tags:
                tags[tag] = {"name": tag}

                # Controller의 docstring에서 설명 추출
                if handler.owner_cls and handler.owner_cls.__doc__:
                    tags[tag]["description"] = handler.owner_cls.__doc__.strip()

        return list(tags.values())

    def _analyze_parameters(
        self, handler: "HttpMethodHandlerContainer", path: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """
        핸들러 파라미터 분석

        Returns:
            (parameters, request_body): OpenAPI parameters와 requestBody
        """
        parameters: list[dict[str, Any]] = []
        request_body: dict[str, Any] | None = None

        method_func = handler.handler_method
        sig = inspect.signature(method_func)

        # path에서 path parameter 추출
        path_params = self._extract_path_params(path)

        for param_name, param in sig.parameters.items():
            # self, cls 제외
            if param_name in ("self", "cls"):
                continue

            param_type = param.annotation
            if param_type is inspect.Parameter.empty:
                param_type = str

            # 특수 타입 확인
            origin = get_origin(param_type)
            args = get_args(param_type)

            # HttpRequest, HttpResponse 등 제외
            if self._is_special_type(param_type):
                continue

            # RequestBody 처리
            if self._is_request_body(param_type):
                request_body = self._generate_request_body(param_type)
                continue

            # Path parameter
            if param_name in path_params:
                parameters.append(
                    self._generate_path_parameter(param_name, param_type, param)
                )
                continue

            # Query parameter (기본)
            parameters.append(
                self._generate_query_parameter(param_name, param_type, param)
            )

        return parameters, request_body

    def _extract_path_params(self, path: str) -> set[str]:
        """경로에서 path parameter 이름 추출"""
        import re

        return set(re.findall(r"\{(\w+)\}", path))

    def _is_special_type(self, param_type: type) -> bool:
        """특수 타입인지 확인 (HttpRequest 등)"""
        type_name = getattr(param_type, "__name__", str(param_type))
        special_types = {
            "HttpRequest",
            "HttpResponse",
            "StreamingResponse",
            "FileResponse",
            "Authentication",
            "WebSocketSession",
        }
        return type_name in special_types

    def _is_request_body(self, param_type: type) -> bool:
        """RequestBody[T] 타입인지 확인"""
        origin = get_origin(param_type)
        args = get_args(param_type)

        if origin is Annotated and args:
            inner_type_name = getattr(args[0], "__name__", "")
            if inner_type_name == "RequestBodyType":
                return True

        return False

    def _generate_request_body(self, param_type: type) -> dict[str, Any]:
        """RequestBody 스키마 생성"""
        schema = self.schema_generator.get_request_body_schema(param_type)

        return {
            "required": True,
            "content": {"application/json": {"schema": schema}},
        }

    def _generate_path_parameter(
        self, name: str, param_type: type, param: inspect.Parameter
    ) -> dict[str, Any]:
        """Path parameter 생성"""
        schema = self._get_simple_schema(param_type)

        return {
            "name": name,
            "in": "path",
            "required": True,
            "schema": schema,
        }

    def _generate_query_parameter(
        self, name: str, param_type: type, param: inspect.Parameter
    ) -> dict[str, Any]:
        """Query parameter 생성"""
        schema = self._get_simple_schema(param_type)

        # Optional 확인
        required = param.default is inspect.Parameter.empty

        result: dict[str, Any] = {
            "name": name,
            "in": "query",
            "schema": schema,
        }

        if required:
            result["required"] = True

        return result

    def _get_simple_schema(self, param_type: type) -> dict[str, Any]:
        """기본 타입의 간단한 스키마 생성"""
        origin = get_origin(param_type)
        args = get_args(param_type)

        # Optional[T] 처리
        from types import NoneType, UnionType
        from typing import Union

        if origin is Union or origin is UnionType:
            non_none = [t for t in args if t is not NoneType and t is not type(None)]
            if non_none:
                param_type = non_none[0]

        # Enum 처리
        if isinstance(param_type, type) and issubclass(param_type, Enum):
            # Enum 값 목록
            enum_values = [e.value for e in param_type]

            # int Enum인지 str Enum인지에 따라 타입 결정
            if issubclass(param_type, int):
                return {"type": "integer", "enum": enum_values}
            else:
                return {"type": "string", "enum": enum_values}

        type_map = {
            str: {"type": "string"},
            int: {"type": "integer"},
            float: {"type": "number"},
            bool: {"type": "boolean"},
        }

        return type_map.get(param_type, {"type": "string"})

    def _generate_responses(
        self, handler: "HttpMethodHandlerContainer", method: str
    ) -> dict[str, Any]:
        """응답 스키마 생성"""
        responses: dict[str, Any] = {}

        # 반환 타입에서 응답 스키마
        return_type = handler.get_metadata("response_type")

        # 메서드별 기본 상태 코드
        status_code = DEFAULT_STATUS_CODES.get(method, "200")

        if return_type:
            schema = self.schema_generator.get_response_schema(return_type)
            responses[status_code] = {
                "description": "Successful response",
                "content": {"application/json": {"schema": schema}},
            }
        else:
            # 반환 타입 힌트에서 추론
            method_func = handler.handler_method
            type_hints = getattr(method_func, "__annotations__", {})
            if "return" in type_hints:
                return_hint = type_hints["return"]
                schema = self.schema_generator.get_response_schema(return_hint)
                if schema:
                    responses[status_code] = {
                        "description": "Successful response",
                        "content": {"application/json": {"schema": schema}},
                    }
                else:
                    responses[status_code] = {"description": "Successful response"}
            else:
                responses[status_code] = {"description": "Successful response"}

        return responses
