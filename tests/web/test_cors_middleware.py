"""CorsMiddleware 테스트"""

import pytest

from bloom.web.http import HttpRequest, HttpResponse
from bloom.web.middleware import CorsMiddleware


class TestCorsMiddleware:
    """CorsMiddleware 단위 테스트"""

    # ===========================================
    # Preflight (OPTIONS) 요청 테스트
    # ===========================================

    @pytest.mark.asyncio
    async def test_preflight_request_returns_204(self):
        """OPTIONS 요청 시 204 No Content 응답 반환"""
        middleware = CorsMiddleware()
        request = HttpRequest(
            method="OPTIONS",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )

        response = await middleware.process_request(request)

        assert response is not None
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_preflight_includes_cors_headers(self):
        """OPTIONS 요청 응답에 CORS 헤더 포함"""
        middleware = CorsMiddleware(
            allow_origins=["http://example.com"],
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "Authorization"],
        )
        request = HttpRequest(
            method="OPTIONS",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )

        response = await middleware.process_request(request)

        assert response is not None
        assert response.headers["Access-Control-Allow-Origin"] == "http://example.com"
        assert "GET" in response.headers["Access-Control-Allow-Methods"]
        assert "POST" in response.headers["Access-Control-Allow-Methods"]
        assert "Content-Type" in response.headers["Access-Control-Allow-Headers"]
        assert "Authorization" in response.headers["Access-Control-Allow-Headers"]

    @pytest.mark.asyncio
    async def test_preflight_includes_max_age(self):
        """OPTIONS 요청 응답에 Max-Age 헤더 포함"""
        middleware = CorsMiddleware(max_age=3600)
        request = HttpRequest(
            method="OPTIONS",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )

        response = await middleware.process_request(request)

        assert response is not None
        assert response.headers["Access-Control-Max-Age"] == "3600"

    @pytest.mark.asyncio
    async def test_non_options_request_passes_through(self):
        """OPTIONS가 아닌 요청은 None 반환 (통과)"""
        middleware = CorsMiddleware()
        request = HttpRequest(
            method="GET",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )

        response = await middleware.process_request(request)

        assert response is None

    # ===========================================
    # Origin 검증 테스트
    # ===========================================

    @pytest.mark.asyncio
    async def test_wildcard_origin_allows_all(self):
        """allow_origins=['*']는 모든 origin 허용"""
        middleware = CorsMiddleware(allow_origins=["*"])
        request = HttpRequest(
            method="GET",
            path="/api/users",
            headers={"Origin": "http://any-domain.com"},
        )
        original_response = HttpResponse.ok({"data": "test"})

        response = await middleware.process_response(request, original_response)

        assert response.headers["Access-Control-Allow-Origin"] == "*"

    @pytest.mark.asyncio
    async def test_specific_origin_allowed(self):
        """특정 origin만 허용"""
        middleware = CorsMiddleware(allow_origins=["http://allowed.com"])
        request = HttpRequest(
            method="GET",
            path="/api/users",
            headers={"Origin": "http://allowed.com"},
        )
        original_response = HttpResponse.ok({"data": "test"})

        response = await middleware.process_response(request, original_response)

        assert response.headers["Access-Control-Allow-Origin"] == "http://allowed.com"

    @pytest.mark.asyncio
    async def test_disallowed_origin_no_cors_headers(self):
        """허용되지 않은 origin은 CORS 헤더 없음"""
        middleware = CorsMiddleware(allow_origins=["http://allowed.com"])
        request = HttpRequest(
            method="GET",
            path="/api/users",
            headers={"Origin": "http://not-allowed.com"},
        )
        original_response = HttpResponse.ok({"data": "test"})

        response = await middleware.process_response(request, original_response)

        assert "Access-Control-Allow-Origin" not in response.headers

    @pytest.mark.asyncio
    async def test_multiple_allowed_origins(self):
        """여러 origin 허용 목록"""
        middleware = CorsMiddleware(
            allow_origins=["http://first.com", "http://second.com", "http://third.com"]
        )

        # 첫 번째 origin
        request1 = HttpRequest(
            method="GET", path="/api", headers={"Origin": "http://first.com"}
        )
        response1 = await middleware.process_response(request1, HttpResponse.ok("test"))
        assert response1.headers["Access-Control-Allow-Origin"] == "http://first.com"

        # 두 번째 origin
        request2 = HttpRequest(
            method="GET", path="/api", headers={"Origin": "http://second.com"}
        )
        response2 = await middleware.process_response(request2, HttpResponse.ok("test"))
        assert response2.headers["Access-Control-Allow-Origin"] == "http://second.com"

    @pytest.mark.asyncio
    async def test_no_origin_header_no_cors_headers(self):
        """Origin 헤더 없으면 CORS 헤더 추가 안함"""
        middleware = CorsMiddleware()
        request = HttpRequest(method="GET", path="/api/users", headers={})
        original_response = HttpResponse.ok({"data": "test"})

        response = await middleware.process_response(request, original_response)

        assert "Access-Control-Allow-Origin" not in response.headers

    # ===========================================
    # Credentials 테스트
    # ===========================================

    @pytest.mark.asyncio
    async def test_allow_credentials_true(self):
        """allow_credentials=True일 때 헤더 추가"""
        middleware = CorsMiddleware(
            allow_origins=["http://example.com"], allow_credentials=True
        )
        request = HttpRequest(
            method="GET",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )
        original_response = HttpResponse.ok({"data": "test"})

        response = await middleware.process_response(request, original_response)

        assert response.headers["Access-Control-Allow-Credentials"] == "true"

    @pytest.mark.asyncio
    async def test_allow_credentials_false_no_header(self):
        """allow_credentials=False일 때 헤더 없음"""
        middleware = CorsMiddleware(
            allow_origins=["http://example.com"], allow_credentials=False
        )
        request = HttpRequest(
            method="GET",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )
        original_response = HttpResponse.ok({"data": "test"})

        response = await middleware.process_response(request, original_response)

        assert "Access-Control-Allow-Credentials" not in response.headers

    # ===========================================
    # Expose Headers 테스트
    # ===========================================

    @pytest.mark.asyncio
    async def test_expose_headers(self):
        """expose_headers 설정 시 헤더 노출"""
        middleware = CorsMiddleware(
            allow_origins=["http://example.com"],
            expose_headers=["X-Custom-Header", "X-Request-Id"],
        )
        request = HttpRequest(
            method="GET",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )
        original_response = HttpResponse.ok({"data": "test"})

        response = await middleware.process_response(request, original_response)

        exposed = response.headers["Access-Control-Expose-Headers"]
        assert "X-Custom-Header" in exposed
        assert "X-Request-Id" in exposed

    @pytest.mark.asyncio
    async def test_no_expose_headers_no_header(self):
        """expose_headers 비어있으면 헤더 없음"""
        middleware = CorsMiddleware(
            allow_origins=["http://example.com"], expose_headers=[]
        )
        request = HttpRequest(
            method="GET",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )
        original_response = HttpResponse.ok({"data": "test"})

        response = await middleware.process_response(request, original_response)

        assert "Access-Control-Expose-Headers" not in response.headers

    # ===========================================
    # 기본값 테스트
    # ===========================================

    @pytest.mark.asyncio
    async def test_default_allow_methods(self):
        """기본 allow_methods: GET, POST, PUT, PATCH, DELETE, OPTIONS"""
        middleware = CorsMiddleware()
        request = HttpRequest(
            method="OPTIONS",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )

        response = await middleware.process_request(request)

        assert response is not None
        methods = response.headers["Access-Control-Allow-Methods"]
        for method in ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]:
            assert method in methods

    @pytest.mark.asyncio
    async def test_default_allow_headers(self):
        """기본 allow_headers: * (모든 헤더 허용)"""
        middleware = CorsMiddleware()
        request = HttpRequest(
            method="OPTIONS",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )

        response = await middleware.process_request(request)

        assert response is not None
        headers = response.headers["Access-Control-Allow-Headers"]
        assert headers == "*"

    @pytest.mark.asyncio
    async def test_default_max_age(self):
        """기본 max_age: 600초"""
        middleware = CorsMiddleware()
        request = HttpRequest(
            method="OPTIONS",
            path="/api/users",
            headers={"Origin": "http://example.com"},
        )

        response = await middleware.process_request(request)

        assert response is not None
        assert response.headers["Access-Control-Max-Age"] == "600"

    # ===========================================
    # 통합 시나리오 테스트
    # ===========================================

    @pytest.mark.asyncio
    async def test_full_cors_configuration(self):
        """모든 CORS 옵션 활성화 시나리오"""
        middleware = CorsMiddleware(
            allow_origins=["http://frontend.example.com"],
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Content-Type", "X-Auth-Token"],
            expose_headers=["X-Rate-Limit", "X-Request-Id"],
            allow_credentials=True,
            max_age=7200,
        )

        # Preflight 요청
        preflight_request = HttpRequest(
            method="OPTIONS",
            path="/api/resource",
            headers={"Origin": "http://frontend.example.com"},
        )
        preflight_response = await middleware.process_request(preflight_request)

        assert preflight_response is not None
        assert preflight_response.status_code == 204
        assert (
            preflight_response.headers["Access-Control-Allow-Origin"]
            == "http://frontend.example.com"
        )
        assert preflight_response.headers["Access-Control-Allow-Credentials"] == "true"
        assert preflight_response.headers["Access-Control-Max-Age"] == "7200"

        # 실제 요청
        actual_request = HttpRequest(
            method="GET",
            path="/api/resource",
            headers={"Origin": "http://frontend.example.com"},
        )
        original_response = HttpResponse.ok({"id": 1, "name": "Resource"})
        actual_response = await middleware.process_response(
            actual_request, original_response
        )

        assert (
            actual_response.headers["Access-Control-Allow-Origin"]
            == "http://frontend.example.com"
        )
        assert actual_response.headers["Access-Control-Allow-Credentials"] == "true"
        assert (
            "X-Rate-Limit" in actual_response.headers["Access-Control-Expose-Headers"]
        )
        assert actual_response.body == {"id": 1, "name": "Resource"}
