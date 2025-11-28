"""OpenAPI 자동 생성 테스트"""

import pytest
from dataclasses import dataclass
from pydantic import BaseModel

from bloom import Application
from bloom.core.decorators import Component, Factory
from bloom.web.controller import Controller, RequestMapping
from bloom.web.handler import Get, Post, Put, Delete
from bloom.web.http import HttpRequest, HttpResponse
from bloom.web.params.types import RequestBodyType as RequestBody
from bloom.web.openapi import OpenAPIConfig, OpenAPIGenerator, SchemaGenerator


# ============================================================================
# 테스트용 모델
# ============================================================================


class UserInput(BaseModel):
    """사용자 생성 요청"""

    username: str
    email: str
    age: int | None = None


class UserOutput(BaseModel):
    """사용자 응답"""

    id: int
    username: str
    email: str


@dataclass
class ItemData:
    """아이템 데이터 (dataclass)"""

    name: str
    price: float
    quantity: int = 0


# ============================================================================
# 테스트용 컨트롤러
# ============================================================================


@Controller
@RequestMapping("/api/users")
class UserController:
    """사용자 관리 API"""

    @Get("/{id}")
    def get_user(self, id: int) -> UserOutput:
        """사용자 조회"""
        return UserOutput(id=id, username="test", email="test@example.com")

    @Get
    def list_users(self, page: int = 1, size: int = 10) -> list[UserOutput]:
        """사용자 목록"""
        return []

    @Post
    def create_user(self, data: RequestBody[UserInput]) -> UserOutput:
        """사용자 생성"""
        return UserOutput(id=1, username=data.username, email=data.email)

    @Put("/{id}")
    def update_user(self, id: int, data: RequestBody[UserInput]) -> UserOutput:
        """사용자 수정"""
        return UserOutput(id=id, username=data.username, email=data.email)

    @Delete("/{id}")
    def delete_user(self, id: int) -> None:
        """사용자 삭제"""
        pass


@Controller
@RequestMapping("/api/items")
class ItemController:
    """아이템 관리 API"""

    @Get("/{id}")
    def get_item(self, id: str) -> ItemData:
        """아이템 조회"""
        return ItemData(name="Item", price=10.0)

    @Post
    def create_item(self, data: RequestBody[ItemData]) -> ItemData:
        """아이템 생성"""
        return data


# ============================================================================
# SchemaGenerator 테스트
# ============================================================================


class TestSchemaGenerator:
    """SchemaGenerator 단위 테스트"""

    def test_basic_types(self):
        """기본 타입 스키마 생성"""
        gen = SchemaGenerator()

        assert gen.get_schema(str) == {"type": "string"}
        assert gen.get_schema(int) == {"type": "integer"}
        assert gen.get_schema(float) == {"type": "number"}
        assert gen.get_schema(bool) == {"type": "boolean"}

    def test_list_type(self):
        """리스트 타입 스키마"""
        gen = SchemaGenerator()

        schema = gen.get_schema(list[str])
        assert schema == {"type": "array", "items": {"type": "string"}}

    def test_optional_type(self):
        """Optional 타입 스키마"""
        gen = SchemaGenerator()

        schema = gen.get_schema(str | None)
        assert schema.get("type") == "string"
        assert schema.get("nullable") is True

    def test_pydantic_model_schema(self):
        """Pydantic 모델 스키마 생성"""
        gen = SchemaGenerator()

        schema = gen.get_schema(UserOutput)
        assert "$ref" in schema
        assert schema["$ref"] == "#/components/schemas/UserOutput"
        assert "UserOutput" in gen.components

    def test_dataclass_schema(self):
        """dataclass 스키마 생성"""
        gen = SchemaGenerator()

        schema = gen.get_schema(ItemData)
        assert "$ref" in schema
        assert schema["$ref"] == "#/components/schemas/ItemData"
        assert "ItemData" in gen.components


# ============================================================================
# OpenAPIGenerator 테스트
# ============================================================================


class TestOpenAPIGenerator:
    """OpenAPIGenerator 통합 테스트"""

    def test_generate_basic_spec(self):
        """기본 OpenAPI 스펙 생성"""
        app = Application("test_openapi")
        app.scan(UserController).ready()

        config = OpenAPIConfig(
            title="Test API",
            version="1.0.0",
            description="Test API Description",
        )
        generator = OpenAPIGenerator(config)
        spec = generator.generate(app._router.route_manager)

        # 기본 구조 확인
        assert spec["openapi"] == "3.0.3"
        assert spec["info"]["title"] == "Test API"
        assert spec["info"]["version"] == "1.0.0"
        assert "paths" in spec

    def test_generate_paths(self):
        """경로 생성 테스트"""
        app = Application("test_paths")
        app.scan(UserController).ready()

        generator = OpenAPIGenerator()
        spec = generator.generate(app._router.route_manager)

        # 경로 확인
        assert "/api/users/{id}" in spec["paths"]
        assert "/api/users/list_users" in spec["paths"]

        # 메서드 확인
        assert "get" in spec["paths"]["/api/users/{id}"]
        assert "put" in spec["paths"]["/api/users/{id}"]
        assert "delete" in spec["paths"]["/api/users/{id}"]

    def test_generate_path_parameters(self):
        """경로 파라미터 추출 테스트"""
        app = Application("test_path_params")
        app.scan(UserController).ready()

        generator = OpenAPIGenerator()
        spec = generator.generate(app._router.route_manager)

        get_op = spec["paths"]["/api/users/{id}"]["get"]
        params = get_op.get("parameters", [])

        # id 파라미터 확인
        id_param = next((p for p in params if p["name"] == "id"), None)
        assert id_param is not None
        assert id_param["in"] == "path"
        assert id_param["required"] is True
        assert id_param["schema"]["type"] == "integer"

    def test_generate_query_parameters(self):
        """쿼리 파라미터 추출 테스트"""
        app = Application("test_query_params")
        app.scan(UserController).ready()

        generator = OpenAPIGenerator()
        spec = generator.generate(app._router.route_manager)

        list_op = spec["paths"]["/api/users/list_users"]["get"]
        params = list_op.get("parameters", [])

        # page, size 파라미터 확인
        param_names = [p["name"] for p in params]
        assert "page" in param_names
        assert "size" in param_names

    def test_generate_request_body(self):
        """RequestBody 스키마 생성 테스트"""
        app = Application("test_request_body")
        app.scan(UserController).ready()

        generator = OpenAPIGenerator()
        spec = generator.generate(app._router.route_manager)

        create_op = spec["paths"]["/api/users/create_user"]["post"]
        assert "requestBody" in create_op
        assert create_op["requestBody"]["required"] is True
        assert "application/json" in create_op["requestBody"]["content"]

    def test_generate_responses(self):
        """응답 스키마 생성 테스트"""
        app = Application("test_responses")
        app.scan(UserController).ready()

        generator = OpenAPIGenerator()
        spec = generator.generate(app._router.route_manager)

        get_op = spec["paths"]["/api/users/{id}"]["get"]
        assert "responses" in get_op
        assert "200" in get_op["responses"]

    def test_generate_tags(self):
        """태그 생성 테스트"""
        app = Application("test_tags")
        app.scan(UserController, ItemController).ready()

        generator = OpenAPIGenerator()
        spec = generator.generate(app._router.route_manager)

        # 태그 확인
        assert "tags" in spec
        tag_names = [t["name"] for t in spec["tags"]]
        assert "User" in tag_names
        assert "Item" in tag_names

    def test_generate_operation_id(self):
        """operationId 생성 테스트"""
        app = Application("test_operation_id")
        app.scan(UserController).ready()

        generator = OpenAPIGenerator()
        spec = generator.generate(app._router.route_manager)

        get_op = spec["paths"]["/api/users/{id}"]["get"]
        assert get_op["operationId"] == "User_get_user"

    def test_generate_summary_from_docstring(self):
        """docstring에서 summary 추출"""
        app = Application("test_summary")
        app.scan(UserController).ready()

        generator = OpenAPIGenerator()
        spec = generator.generate(app._router.route_manager)

        get_op = spec["paths"]["/api/users/{id}"]["get"]
        assert get_op.get("summary") == "사용자 조회"


# ============================================================================
# OpenAPI 엔드포인트 통합 테스트
# ============================================================================


class TestOpenAPIEndpoints:
    """OpenAPI 엔드포인트 통합 테스트"""

    def test_openapi_endpoints_registered(self):
        """OpenAPI 엔드포인트가 등록되는지 확인"""

        @Component
        class OpenAPIConfiguration:
            @Factory
            def openapi_config(self) -> OpenAPIConfig:
                return OpenAPIConfig(
                    title="Test API",
                    version="1.0.0",
                )

        app = Application("test_endpoints")
        app.scan(OpenAPIConfiguration, UserController).ready()

        # 라우트 목록 확인
        routes = app._router.get_routes()
        route_paths = [r[1] for r in routes]

        assert "/openapi.json" in route_paths
        assert "/docs" in route_paths
        assert "/redoc" in route_paths

    @pytest.mark.asyncio
    async def test_openapi_json_response(self):
        """OpenAPI JSON 응답 테스트"""

        @Component
        class Config:
            @Factory
            def openapi_config(self) -> OpenAPIConfig:
                return OpenAPIConfig(title="My API", version="2.0.0")

        app = Application("test_json")
        app.scan(Config, UserController).ready()

        # /openapi.json 요청
        request = HttpRequest(
            method="GET",
            path="/openapi.json",
            headers={},
            query_params={},
            body=b"",
        )
        response = await app._router.dispatch(request)

        assert response.status_code == 200
        assert response.body["openapi"] == "3.0.3"
        assert response.body["info"]["title"] == "My API"
        assert response.body["info"]["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_swagger_ui_response(self):
        """Swagger UI HTML 응답 테스트"""

        @Component
        class Config:
            @Factory
            def openapi_config(self) -> OpenAPIConfig:
                return OpenAPIConfig(title="My API")

        app = Application("test_swagger")
        app.scan(Config, UserController).ready()

        request = HttpRequest(
            method="GET",
            path="/docs",
            headers={},
            query_params={},
            body=b"",
        )
        response = await app._router.dispatch(request)

        assert response.status_code == 200
        assert response.content_type == "text/html; charset=utf-8"
        assert "swagger-ui" in response.body.lower()

    @pytest.mark.asyncio
    async def test_redoc_response(self):
        """ReDoc HTML 응답 테스트"""

        @Component
        class Config:
            @Factory
            def openapi_config(self) -> OpenAPIConfig:
                return OpenAPIConfig(title="My API")

        app = Application("test_redoc")
        app.scan(Config, UserController).ready()

        request = HttpRequest(
            method="GET",
            path="/redoc",
            headers={},
            query_params={},
            body=b"",
        )
        response = await app._router.dispatch(request)

        assert response.status_code == 200
        assert response.content_type == "text/html; charset=utf-8"
        assert "redoc" in response.body.lower()

    def test_custom_urls(self):
        """커스텀 URL 설정 테스트"""

        @Component
        class Config:
            @Factory
            def openapi_config(self) -> OpenAPIConfig:
                return OpenAPIConfig(
                    title="Custom API",
                    openapi_url="/api/openapi.json",
                    docs_url="/api/docs",
                    redoc_url="/api/redoc",
                )

        app = Application("test_custom_urls")
        app.scan(Config, UserController).ready()

        routes = app._router.get_routes()
        route_paths = [r[1] for r in routes]

        assert "/api/openapi.json" in route_paths
        assert "/api/docs" in route_paths
        assert "/api/redoc" in route_paths

    def test_no_openapi_without_config(self):
        """OpenAPIConfig 없으면 엔드포인트 미등록"""
        app = Application("test_no_config")
        app.scan(UserController).ready()

        routes = app._router.get_routes()
        route_paths = [r[1] for r in routes]

        assert "/openapi.json" not in route_paths
        assert "/docs" not in route_paths


# ============================================================================
# OpenAPIConfig 테스트
# ============================================================================


class TestOpenAPIConfig:
    """OpenAPIConfig 설정 테스트"""

    def test_default_config(self):
        """기본 설정 확인"""
        config = OpenAPIConfig()

        assert config.title == "Bloom API"
        assert config.version == "1.0.0"
        assert config.openapi_url == "/openapi.json"
        assert config.docs_url == "/docs"
        assert config.redoc_url == "/redoc"

    def test_get_info(self):
        """info 객체 생성"""
        from bloom.web.openapi.config import OpenAPIContact, OpenAPILicense

        config = OpenAPIConfig(
            title="My API",
            version="2.0.0",
            description="Test Description",
            contact=OpenAPIContact(name="Dev", email="dev@example.com"),
            license=OpenAPILicense(name="MIT"),
        )

        info = config.get_info()
        assert info["title"] == "My API"
        assert info["version"] == "2.0.0"
        assert info["description"] == "Test Description"
        assert info["contact"]["name"] == "Dev"
        assert info["license"]["name"] == "MIT"

    def test_servers(self):
        """서버 정보"""
        from bloom.web.openapi.config import OpenAPIServer

        config = OpenAPIConfig(
            servers=[
                OpenAPIServer(url="https://api.example.com", description="Production"),
                OpenAPIServer(url="https://staging.example.com", description="Staging"),
            ]
        )

        servers = config.get_servers()
        assert len(servers) == 2
        assert servers[0]["url"] == "https://api.example.com"


class TestHttpResponseToBytes:
    """HttpResponse.to_bytes() 메서드 테스트"""

    def test_html_content_preserves_newlines(self):
        """HTML 콘텐츠에서 개행문자가 보존되는지 테스트"""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Test</title>
</head>
<body>
    <h1>Hello</h1>
</body>
</html>"""
        response = HttpResponse(
            status_code=200,
            body=html,
            content_type="text/html; charset=utf-8",
        )

        body_bytes = response.to_bytes()

        # 바이트로 변환해도 실제 개행문자가 보존되어야 함
        assert b"\\n" not in body_bytes  # 이스케이프된 \n이 없어야 함
        assert b"\n" in body_bytes  # 실제 개행문자가 있어야 함
        assert body_bytes == html.encode("utf-8")

    def test_json_content_serializes_properly(self):
        """JSON 콘텐츠가 올바르게 직렬화되는지 테스트"""
        data = {"message": "Hello\nWorld", "count": 42}
        response = HttpResponse(
            status_code=200,
            body=data,
            content_type="application/json",
        )

        body_bytes = response.to_bytes()

        # JSON 직렬화 시 개행문자가 이스케이프되어야 함
        assert b"\\n" in body_bytes
        import json

        assert json.loads(body_bytes) == data

    def test_plain_text_content(self):
        """text/plain 콘텐츠 테스트"""
        text = "Line 1\nLine 2\nLine 3"
        response = HttpResponse(
            status_code=200,
            body=text,
            content_type="text/plain",
        )

        body_bytes = response.to_bytes()
        assert body_bytes == text.encode("utf-8")
        assert b"\n" in body_bytes
        assert b"\\n" not in body_bytes

    def test_bytes_passthrough(self):
        """바이트 콘텐츠가 그대로 전달되는지 테스트"""
        binary_data = b"\x00\x01\x02\x03"
        response = HttpResponse(
            status_code=200,
            body=binary_data,
            content_type="application/octet-stream",
        )

        body_bytes = response.to_bytes()
        assert body_bytes == binary_data

    def test_css_content(self):
        """CSS 콘텐츠 테스트"""
        css = """body {
    margin: 0;
    padding: 0;
}"""
        response = HttpResponse(
            status_code=200,
            body=css,
            content_type="text/css",
        )

        body_bytes = response.to_bytes()
        assert body_bytes == css.encode("utf-8")
