"""
CORS (Cross-Origin Resource Sharing) 미들웨어

브라우저의 Same-Origin Policy를 우회하여
다른 도메인에서의 API 요청을 허용합니다.

사용 예시:
    ```python
    from bloom import Component
    from bloom.core.decorators import Factory
    from bloom.web.middleware import CorsMiddleware

    @Component
    class CorsConfiguration:
        @Factory
        def cors_middleware(self) -> CorsMiddleware:
            # 모든 origin 허용 (개발용)
            return CorsMiddleware(allow_origins=["*"])

    @Component
    class ProdCorsConfiguration:
        @Factory
        def cors_middleware(self) -> CorsMiddleware:
            # 특정 origin만 허용 (프로덕션)
            return CorsMiddleware(
                allow_origins=["https://example.com", "https://api.example.com"],
                allow_credentials=True,
            )

    @Component
    class CustomCorsConfiguration:
        @Factory
        def cors_middleware(self) -> CorsMiddleware:
            # 커스텀 설정
            return CorsMiddleware(
                allow_origins=["https://example.com"],
                allow_methods=["GET", "POST", "PUT", "DELETE"],
                allow_headers=["Authorization", "Content-Type", "X-Custom-Header"],
                expose_headers=["X-Request-Id"],
                max_age=86400,  # 24시간 캐시
            )
    ```

Preflight 요청:
    브라우저는 실제 요청 전에 OPTIONS 요청을 보내서 CORS 정책을 확인합니다.
    이 미들웨어는 OPTIONS 요청을 자동으로 처리합니다.
"""

from typing import Any, Optional

from ...http import HttpRequest, HttpResponse
from ...middleware.base import Middleware


class CorsMiddleware(Middleware):
    """
    CORS 미들웨어

    Cross-Origin 요청을 처리하고 적절한 CORS 헤더를 추가합니다.

    Attributes:
        allow_origins: 허용할 origin 목록 (["*"]이면 모든 origin 허용)
        allow_methods: 허용할 HTTP 메서드 목록
        allow_headers: 허용할 요청 헤더 목록
        expose_headers: 브라우저에 노출할 응답 헤더 목록
        allow_credentials: 쿠키/인증 정보 포함 허용 여부
        max_age: Preflight 응답 캐시 시간 (초)

    사용 예시:
        ```python
        @Component
        class CorsConfig:
            @Factory
            def cors_middleware(self) -> CorsMiddleware:
                return CorsMiddleware(
                    allow_origins=["https://frontend.example.com"],
                    allow_credentials=True,
                    max_age=3600,
                )
        ```

    주의사항:
        - allow_origins = ["*"]와 allow_credentials = True는 함께 사용 불가
        - 프로덕션에서는 구체적인 origin을 지정하세요
    """

    def __init__(
        self,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        expose_headers: list[str] | None = None,
        allow_credentials: bool = False,
        max_age: int = 600,
    ):
        """
        CorsMiddleware 생성자

        Args:
            allow_origins: 허용할 origin 목록 (기본: ["*"])
            allow_methods: 허용할 HTTP 메서드 (기본: GET, POST, PUT, PATCH, DELETE, OPTIONS)
            allow_headers: 허용할 요청 헤더 (기본: ["*"])
            expose_headers: 브라우저에 노출할 응답 헤더 (기본: [])
            allow_credentials: 쿠키/인증 정보 포함 허용 (기본: False)
            max_age: Preflight 응답 캐시 시간 - 초 (기본: 600)
        """
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or [
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ]
        self.allow_headers = allow_headers or ["*"]
        self.expose_headers = expose_headers or []
        self.allow_credentials = allow_credentials
        self.max_age = max_age

        # 성능 최적화: 자주 사용되는 문자열 미리 캐싱
        self._methods_str = ", ".join(self.allow_methods)
        self._headers_str = (
            ", ".join(self.allow_headers) if self.allow_headers != ["*"] else ""
        )
        self._expose_headers_str = (
            ", ".join(self.expose_headers) if self.expose_headers else ""
        )
        self._max_age_str = str(self.max_age)

    async def process_request(self, request: HttpRequest) -> HttpResponse | None:
        """
        Preflight (OPTIONS) 요청 처리

        브라우저의 preflight 요청에 대해 CORS 헤더가 포함된 응답을 반환합니다.
        """
        # Preflight 요청 처리
        if request.method == "OPTIONS":
            response = HttpResponse(status_code=204)
            self._add_cors_headers(request, response)
            return response

        return None

    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """
        모든 응답에 CORS 헤더 추가
        """
        self._add_cors_headers(request, response)
        return response

    def _add_cors_headers(self, request: HttpRequest, response: HttpResponse) -> None:
        """CORS 헤더 추가 (캐싱된 문자열 사용)"""
        origin = request.headers.get("Origin", "")

        # Origin 검증
        if self._is_origin_allowed(origin):
            # allow_origins가 ["*"]이고 credentials가 False일 때만 "*" 사용
            if self.allow_origins == ["*"] and not self.allow_credentials:
                response.headers["Access-Control-Allow-Origin"] = "*"
            else:
                response.headers["Access-Control-Allow-Origin"] = origin

        # 메서드 허용 (캐싱된 문자열)
        response.headers["Access-Control-Allow-Methods"] = self._methods_str

        # 헤더 허용
        if self.allow_headers == ["*"]:
            # 요청의 Access-Control-Request-Headers를 그대로 반환
            requested_headers = request.headers.get(
                "Access-Control-Request-Headers", ""
            )
            if requested_headers:
                response.headers["Access-Control-Allow-Headers"] = requested_headers
            else:
                response.headers["Access-Control-Allow-Headers"] = "*"
        else:
            response.headers["Access-Control-Allow-Headers"] = self._headers_str

        # 노출 헤더 (캐싱된 문자열)
        if self._expose_headers_str:
            response.headers["Access-Control-Expose-Headers"] = self._expose_headers_str

        # 인증 정보 허용
        if self.allow_credentials:
            response.headers["Access-Control-Allow-Credentials"] = "true"

        # Preflight 캐시 (캐싱된 문자열)
        if request.method == "OPTIONS":
            response.headers["Access-Control-Max-Age"] = self._max_age_str

    def _is_origin_allowed(self, origin: str) -> bool:
        """Origin이 허용되는지 확인"""
        if not origin:
            return False

        if self.allow_origins == ["*"]:
            return True

        return origin in self.allow_origins
