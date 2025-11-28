"""OpenAPI 자동 생성

라우터에 등록된 핸들러들의 타입 힌트를 분석하여
OpenAPI 3.0 스펙을 자동으로 생성합니다.

사용 예시:
    from bloom import Application, Component
    from bloom.core.decorators import Factory
    from bloom.web.openapi import OpenAPIGenerator, OpenAPIConfig

    @Component
    class OpenAPIConfiguration:
        @Factory
        def openapi_config(self) -> OpenAPIConfig:
            return OpenAPIConfig(
                title="My API",
                version="1.0.0",
                description="My awesome API",
            )

    app = Application("my_app").scan(OpenAPIConfiguration, MyController).ready()
    # /openapi.json, /docs 엔드포인트 자동 등록
"""

from .config import OpenAPIConfig
from .generator import OpenAPIGenerator
from .schema import SchemaGenerator
from .controller import OpenAPIController

__all__ = [
    "OpenAPIConfig",
    "OpenAPIGenerator",
    "SchemaGenerator",
    "OpenAPIController",
]
