"""OpenAPI 컨트롤러

/openapi.json, /docs (Swagger UI), /redoc 엔드포인트를 제공합니다.
"""

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .config import OpenAPIConfig

from bloom.web.http import HttpResponse


# Swagger UI HTML 템플릿
SWAGGER_UI_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>{title} - Swagger UI</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
    <style>
        html {{ box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }}
        *, *:before, *:after {{ box-sizing: inherit; }}
        body {{ margin: 0; background: #fafafa; }}
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {{
            SwaggerUIBundle({{
                url: "{openapi_url}",
                dom_id: '#swagger-ui',
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                layout: "StandaloneLayout"
            }});
        }};
    </script>
</body>
</html>
"""

# ReDoc HTML 템플릿
REDOC_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>{title} - ReDoc</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
        body {{ margin: 0; padding: 0; }}
    </style>
</head>
<body>
    <redoc spec-url='{openapi_url}'></redoc>
    <script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body>
</html>
"""


class OpenAPIController:
    """
    OpenAPI 엔드포인트 컨트롤러

    OpenAPIConfig가 DI에 등록되면 자동으로 활성화됩니다.

    엔드포인트:
    - GET /openapi.json: OpenAPI 스펙 JSON
    - GET /docs: Swagger UI
    - GET /redoc: ReDoc

    사용법:
        from bloom.web.openapi import OpenAPIConfig

        @Component
        class Config:
            @Factory
            def openapi_config(self) -> OpenAPIConfig:
                return OpenAPIConfig(title="My API", version="1.0.0")

        # 엔드포인트 자동 등록됨
    """

    def __init__(self, spec: dict[str, Any], config: "OpenAPIConfig"):
        self._spec = spec
        self._config = config
        self._title = config.title
        self._openapi_url = config.openapi_url

    def get_openapi_json(self) -> HttpResponse:
        """OpenAPI 스펙 JSON 반환"""
        return HttpResponse.ok(self._spec)

    def get_swagger_ui(self) -> HttpResponse:
        """Swagger UI HTML 반환"""
        html = SWAGGER_UI_HTML.format(
            title=self._title,
            openapi_url=self._openapi_url,
        )
        return HttpResponse(
            status_code=200,
            body=html,
            content_type="text/html; charset=utf-8",
        )

    def get_redoc(self) -> HttpResponse:
        """ReDoc HTML 반환"""
        html = REDOC_HTML.format(
            title=self._title,
            openapi_url=self._openapi_url,
        )
        return HttpResponse(
            status_code=200,
            body=html,
            content_type="text/html; charset=utf-8",
        )
