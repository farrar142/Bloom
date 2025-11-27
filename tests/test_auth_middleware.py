"""AuthMiddleware 테스트"""

import pytest
from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.web import Authenticator, Authentication, Controller, Get, HttpRequest
from bloom.web.auth import AuthMiddleware
from bloom.web.middleware import MiddlewareChain

from .conftest import Module


class TestAuthMiddleware:
    """AuthMiddleware 기본 테스트"""

    @pytest.mark.asyncio
    async def test_authenticator_chain_execution_order(self):
        """Authenticator 체인 실행 순서 테스트"""
        execution_order: list[str] = []

        class M:
            pass

        @Module(M)
        @Component
        class FirstAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_order.append("first")
                return None

            def supports(self, request: HttpRequest) -> bool:
                return True

        class SecondAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_order.append("second")
                if request.headers.get("X-Auth") == "valid":
                    return Authentication(user_id="user", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def second_authenticator(self) -> SecondAuthenticator:
                return SecondAuthenticator()

            @Factory
            def auth_middleware(self, *authenticators: Authenticator) -> AuthMiddleware:
                middleware = AuthMiddleware()
                for authenticator in authenticators:
                    middleware.register(authenticator)
                return middleware

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class TestController:
            @Get("/test")
            async def test_endpoint(self) -> str:
                return "success"

        app = Application("test").scan(M).ready()

        # 인증 실패 케이스
        request = HttpRequest(method="GET", path="/test")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert execution_order == ["first", "second"]

    @pytest.mark.asyncio
    async def test_authentication_success(self):
        """인증 성공 시 request.auth에 저장"""

        class M:
            pass

        class TokenAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("Authorization") == "Bearer valid-token":
                    return Authentication(
                        user_id="user123",
                        authenticated=True,
                        authorities=["read", "write"],
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(TokenAuthenticator())

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/test")
            async def test_endpoint(self, request: HttpRequest) -> dict:
                captured_auth.append(request.auth)
                return {"user": request.auth.user_id if request.auth else None}

        app = Application("test").scan(M).ready()

        # 인증 성공
        request = HttpRequest(
            method="GET",
            path="/test",
            headers={"Authorization": "Bearer valid-token"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert captured_auth[0] is not None
        assert captured_auth[0].user_id == "user123"
        assert captured_auth[0].is_authenticated()
        assert captured_auth[0].has_authority("read")

    @pytest.mark.asyncio
    async def test_require_auth_returns_401(self):
        """require_auth=True일 때 인증 실패 시 401 반환"""

        class M:
            pass

        class AlwaysFailAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                return None

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware().register(AlwaysFailAuthenticator()).require(True)
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class TestController:
            @Get("/test")
            async def test_endpoint(self) -> str:
                return "success"

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/test")
        response = await app.router.dispatch(request)

        assert response.status_code == 401
        assert "Unauthorized" in str(response.body)

    @pytest.mark.asyncio
    async def test_exclude_paths(self):
        """exclude_paths로 특정 경로 인증 제외"""

        class M:
            pass

        class StrictAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                return None  # 항상 실패

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    .register(StrictAuthenticator())
                    .require(True)
                    .exclude("/public", "/health")
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class TestController:
            @Get("/public/data")
            async def public_endpoint(self) -> str:
                return "public"

            @Get("/private/data")
            async def private_endpoint(self) -> str:
                return "private"

        app = Application("test").scan(M).ready()

        # 제외 경로 - 인증 없이 통과
        request1 = HttpRequest(method="GET", path="/public/data")
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 200

        # 비제외 경로 - 401 반환
        request2 = HttpRequest(method="GET", path="/private/data")
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 401

    @pytest.mark.asyncio
    async def test_supports_filters_authenticator(self):
        """supports()가 False면 해당 인증기 건너뛰기"""
        execution_log: list[str] = []

        class M:
            pass

        class HeaderAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("header")
                return Authentication(user_id="header-user", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return "X-Custom-Auth" in request.headers

        class DefaultAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("default")
                return Authentication(user_id="default-user", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(
                    HeaderAuthenticator(), DefaultAuthenticator()
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/test")
            async def test_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "success"

        app = Application("test").scan(M).ready()

        # X-Custom-Auth 없음 - DefaultAuthenticator만 실행
        request = HttpRequest(method="GET", path="/test")
        await app.router.dispatch(request)

        assert execution_log == ["default"]
        assert captured_auth[0].user_id == "default-user"

    @pytest.mark.asyncio
    async def test_first_successful_auth_wins(self):
        """첫 번째 성공한 인증기의 결과 사용"""
        execution_log: list[str] = []

        class M:
            pass

        class FirstAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("first")
                return Authentication(user_id="first-user", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return True

        class SecondAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("second")
                return Authentication(user_id="second-user", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(
                    FirstAuthenticator(), SecondAuthenticator()
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/test")
            async def test_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "success"

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/test")
        await app.router.dispatch(request)

        # 첫 번째 인증기만 실행되고 두 번째는 건너뜀
        assert execution_log == ["first"]
        assert captured_auth[0].user_id == "first-user"

    @pytest.mark.asyncio
    async def test_async_authenticator(self):
        """비동기 인증기 지원"""

        class M:
            pass

        class AsyncAuthenticator(Authenticator):
            async def authenticate(self, request: HttpRequest) -> Authentication | None:
                # 비동기 작업 시뮬레이션
                return Authentication(user_id="async-user", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(AsyncAuthenticator())

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/test")
            async def test_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "success"

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/test")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert captured_auth[0].user_id == "async-user"


class TestAuthMiddlewareGroups:
    """AuthMiddleware 그룹 기능 테스트"""

    @pytest.mark.asyncio
    async def test_group_based_authentication(self):
        """그룹별로 다른 인증기 사용"""

        class M:
            pass

        class ApiKeyAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("X-API-Key") == "secret":
                    return Authentication(user_id="api-user", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "X-API-Key" in request.headers

        class JwtAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("Authorization") == "Bearer jwt-token":
                    return Authentication(user_id="jwt-user", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    .group("api")
                    .register(ApiKeyAuthenticator())
                    .include("/api/")
                    .require()
                    .group("admin")
                    .register(JwtAuthenticator())
                    .include("/admin/")
                    .require()
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/api/data")
            async def api_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "api"

            @Get("/admin/dashboard")
            async def admin_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "admin"

        app = Application("test").scan(M).ready()

        # API 그룹 - API 키로 인증
        request1 = HttpRequest(
            method="GET", path="/api/data", headers={"X-API-Key": "secret"}
        )
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 200
        assert captured_auth[0].user_id == "api-user"

        captured_auth.clear()

        # Admin 그룹 - JWT로 인증
        request2 = HttpRequest(
            method="GET",
            path="/admin/dashboard",
            headers={"Authorization": "Bearer jwt-token"},
        )
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 200
        assert captured_auth[0].user_id == "jwt-user"

    @pytest.mark.asyncio
    async def test_group_require_only_affects_that_group(self):
        """각 그룹의 require 설정이 독립적으로 동작"""

        class M:
            pass

        class AlwaysFailAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                return None

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    .group("strict")
                    .register(AlwaysFailAuthenticator())
                    .include("/strict/")
                    .require(True)
                    .group("optional")
                    .register(AlwaysFailAuthenticator())
                    .include("/optional/")
                    .require(False)
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class TestController:
            @Get("/strict/data")
            async def strict_endpoint(self) -> str:
                return "strict"

            @Get("/optional/data")
            async def optional_endpoint(self) -> str:
                return "optional"

        app = Application("test").scan(M).ready()

        # strict 그룹 - 401
        request1 = HttpRequest(method="GET", path="/strict/data")
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 401

        # optional 그룹 - 200
        request2 = HttpRequest(method="GET", path="/optional/data")
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 200

    @pytest.mark.asyncio
    async def test_group_exclude_paths(self):
        """그룹별 exclude 설정"""

        class M:
            pass

        class StrictAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                return None

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    .group("api")
                    .register(StrictAuthenticator())
                    .include("/api/")
                    .exclude("/api/public/", "/api/health")
                    .require(True)
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class TestController:
            @Get("/api/private")
            async def private_endpoint(self) -> str:
                return "private"

            @Get("/api/public/info")
            async def public_endpoint(self) -> str:
                return "public"

            @Get("/api/health")
            async def health_endpoint(self) -> str:
                return "healthy"

        app = Application("test").scan(M).ready()

        # 제외되지 않은 경로 - 401
        request1 = HttpRequest(method="GET", path="/api/private")
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 401

        # 제외된 경로 - 200
        request2 = HttpRequest(method="GET", path="/api/public/info")
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 200

        request3 = HttpRequest(method="GET", path="/api/health")
        response3 = await app.router.dispatch(request3)
        assert response3.status_code == 200

    @pytest.mark.asyncio
    async def test_default_group_fallback(self):
        """include가 없는 default 그룹은 모든 경로에 적용"""

        class M:
            pass

        class DefaultAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                return Authentication(user_id="default", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                # default 그룹 사용 (group() 호출 없이 바로 register)
                return AuthMiddleware().register(DefaultAuthenticator())

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/any/path")
            async def any_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "success"

        app = Application("test").scan(M).ready()

        request = HttpRequest(method="GET", path="/any/path")
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert captured_auth[0].user_id == "default"

    @pytest.mark.asyncio
    async def test_specific_group_takes_priority(self):
        """include가 설정된 그룹이 default 그룹보다 우선"""
        execution_log: list[str] = []

        class M:
            pass

        class ApiAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("api")
                return Authentication(user_id="api", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return True

        class DefaultAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("default")
                return Authentication(user_id="default", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    # default 그룹
                    .register(DefaultAuthenticator())
                    # api 그룹 (include 설정)
                    .group("api")
                    .register(ApiAuthenticator())
                    .include("/api/")
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/api/data")
            async def api_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "api"

            @Get("/other/data")
            async def other_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "other"

        app = Application("test").scan(M).ready()

        # /api/ 경로 - api 그룹 사용
        request1 = HttpRequest(method="GET", path="/api/data")
        await app.router.dispatch(request1)
        assert execution_log == ["api"]
        assert captured_auth[0].user_id == "api"

        execution_log.clear()
        captured_auth.clear()

        # 다른 경로 - default 그룹 사용
        request2 = HttpRequest(method="GET", path="/other/data")
        await app.router.dispatch(request2)
        assert execution_log == ["default"]
        assert captured_auth[0].user_id == "default"

    @pytest.mark.asyncio
    async def test_no_matching_group_allows_request(self):
        """매칭되는 그룹이 없으면 인증 없이 통과"""

        class M:
            pass

        class StrictAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                return None

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    .group("api")
                    .register(StrictAuthenticator())
                    .include("/api/")
                    .require(True)
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class TestController:
            @Get("/public/data")
            async def public_endpoint(self) -> str:
                return "public"

        app = Application("test").scan(M).ready()

        # /public/ 경로 - 어떤 그룹에도 매칭되지 않음
        request = HttpRequest(method="GET", path="/public/data")
        response = await app.router.dispatch(request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_multiple_authenticators_per_group(self):
        """그룹에 여러 인증기 등록 시 순서대로 시도"""
        execution_log: list[str] = []

        class M:
            pass

        class PrimaryAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("primary")
                if request.headers.get("X-Primary") == "valid":
                    return Authentication(user_id="primary-user", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return True

        class FallbackAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("fallback")
                if request.headers.get("X-Fallback") == "valid":
                    return Authentication(user_id="fallback-user", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    .group("api")
                    .register(PrimaryAuthenticator(), FallbackAuthenticator())
                    .include("/api/")
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/api/data")
            async def api_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "success"

        app = Application("test").scan(M).ready()

        # Primary 인증 성공 - Fallback은 실행 안됨
        request1 = HttpRequest(
            method="GET", path="/api/data", headers={"X-Primary": "valid"}
        )
        await app.router.dispatch(request1)
        assert execution_log == ["primary"]
        assert captured_auth[0].user_id == "primary-user"

        execution_log.clear()
        captured_auth.clear()

        # Primary 실패, Fallback 성공
        request2 = HttpRequest(
            method="GET", path="/api/data", headers={"X-Fallback": "valid"}
        )
        await app.router.dispatch(request2)
        assert execution_log == ["primary", "fallback"]
        assert captured_auth[0].user_id == "fallback-user"

    @pytest.mark.asyncio
    async def test_group_with_different_auth_types(self):
        """그룹별로 다른 인증 타입 사용 (API Key vs JWT vs Session)"""

        class M:
            pass

        class ApiKeyAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                key = request.headers.get("X-API-Key")
                if key == "api-secret-123":
                    return Authentication(
                        user_id="api-client",
                        authenticated=True,
                        authorities=["api:read", "api:write"],
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "X-API-Key" in request.headers

        class JwtAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                auth_header = request.headers.get("Authorization", "")
                if auth_header == "Bearer admin-jwt-token":
                    return Authentication(
                        user_id="admin",
                        authenticated=True,
                        authorities=["admin:full"],
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return request.headers.get("Authorization", "").startswith("Bearer ")

        class SessionAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                session_id = request.headers.get("Cookie", "")
                if "session=user-session-abc" in session_id:
                    return Authentication(
                        user_id="web-user",
                        authenticated=True,
                        authorities=["user:read"],
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Cookie" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    # API 그룹 - API Key 인증
                    .group("api")
                    .register(ApiKeyAuthenticator())
                    .include("/api/v1/")
                    .require()
                    # Admin 그룹 - JWT 인증
                    .group("admin")
                    .register(JwtAuthenticator())
                    .include("/admin/")
                    .require()
                    # Web 그룹 - Session 인증
                    .group("web")
                    .register(SessionAuthenticator())
                    .include("/web/")
                    .require()
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/api/v1/resources")
            async def api_endpoint(self, request: HttpRequest) -> dict:
                captured_auth.append(request.auth)
                return {"user": request.auth.user_id if request.auth else None}

            @Get("/admin/dashboard")
            async def admin_endpoint(self, request: HttpRequest) -> dict:
                captured_auth.append(request.auth)
                return {"user": request.auth.user_id if request.auth else None}

            @Get("/web/profile")
            async def web_endpoint(self, request: HttpRequest) -> dict:
                captured_auth.append(request.auth)
                return {"user": request.auth.user_id if request.auth else None}

        app = Application("test").scan(M).ready()

        # API 인증 - API Key
        request1 = HttpRequest(
            method="GET",
            path="/api/v1/resources",
            headers={"X-API-Key": "api-secret-123"},
        )
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 200
        assert captured_auth[0].user_id == "api-client"
        assert captured_auth[0].has_authority("api:read")

        captured_auth.clear()

        # Admin 인증 - JWT
        request2 = HttpRequest(
            method="GET",
            path="/admin/dashboard",
            headers={"Authorization": "Bearer admin-jwt-token"},
        )
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 200
        assert captured_auth[0].user_id == "admin"
        assert captured_auth[0].has_authority("admin:full")

        captured_auth.clear()

        # Web 인증 - Session
        request3 = HttpRequest(
            method="GET",
            path="/web/profile",
            headers={"Cookie": "session=user-session-abc"},
        )
        response3 = await app.router.dispatch(request3)
        assert response3.status_code == 200
        assert captured_auth[0].user_id == "web-user"
        assert captured_auth[0].has_authority("user:read")

    @pytest.mark.asyncio
    async def test_group_wrong_auth_type_returns_401(self):
        """그룹에 맞지 않는 인증 타입 사용 시 401"""

        class M:
            pass

        class ApiKeyAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("X-API-Key") == "valid":
                    return Authentication(user_id="api", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "X-API-Key" in request.headers

        class JwtAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("Authorization") == "Bearer valid":
                    return Authentication(user_id="jwt", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    .group("api")
                    .register(ApiKeyAuthenticator())
                    .include("/api/")
                    .require()
                    .group("admin")
                    .register(JwtAuthenticator())
                    .include("/admin/")
                    .require()
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class TestController:
            @Get("/api/data")
            async def api_endpoint(self) -> str:
                return "api"

            @Get("/admin/data")
            async def admin_endpoint(self) -> str:
                return "admin"

        app = Application("test").scan(M).ready()

        # API 경로에 JWT 토큰 사용 - 401 (ApiKeyAuthenticator가 supports=False)
        request1 = HttpRequest(
            method="GET", path="/api/data", headers={"Authorization": "Bearer valid"}
        )
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 401

        # Admin 경로에 API Key 사용 - 401 (JwtAuthenticator가 supports=False)
        request2 = HttpRequest(
            method="GET", path="/admin/data", headers={"X-API-Key": "valid"}
        )
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 401

    @pytest.mark.asyncio
    async def test_overlapping_groups_first_match_wins(self):
        """경로가 여러 그룹에 매칭될 수 있을 때 첫 번째 매칭 그룹 사용"""
        execution_log: list[str] = []

        class M:
            pass

        class SpecificAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("specific")
                return Authentication(user_id="specific", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return True

        class GeneralAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                execution_log.append("general")
                return Authentication(user_id="general", authenticated=True)

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    # 더 구체적인 경로 그룹
                    .group("specific")
                    .register(SpecificAuthenticator())
                    .include("/api/v2/")
                    # 일반적인 경로 그룹
                    .group("general")
                    .register(GeneralAuthenticator())
                    .include("/api/")
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        captured_auth: list[Authentication | None] = []

        @Module(M)
        @Controller
        class TestController:
            @Get("/api/v2/data")
            async def specific_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "specific"

            @Get("/api/v1/data")
            async def general_endpoint(self, request: HttpRequest) -> str:
                captured_auth.append(request.auth)
                return "general"

        app = Application("test").scan(M).ready()

        # /api/v2/ - specific 그룹 매칭 (먼저 등록됨)
        request1 = HttpRequest(method="GET", path="/api/v2/data")
        await app.router.dispatch(request1)
        assert execution_log == ["specific"]
        assert captured_auth[0].user_id == "specific"

        execution_log.clear()
        captured_auth.clear()

        # /api/v1/ - general 그룹 매칭
        request2 = HttpRequest(method="GET", path="/api/v1/data")
        await app.router.dispatch(request2)
        assert execution_log == ["general"]
        assert captured_auth[0].user_id == "general"


class TestAuthenticationResolver:
    """AuthenticationResolver 테스트 - 핸들러 파라미터로 Authentication 주입"""

    @pytest.mark.asyncio
    async def test_authentication_injection_via_resolver(self):
        """AuthMiddleware + AuthenticationResolver 통합 - 핸들러에서 auth 파라미터로 받기"""

        class M:
            pass

        class TokenAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("Authorization") == "Bearer valid-token":
                    return Authentication(
                        user_id="user123",
                        authenticated=True,
                        authorities=["read", "write"],
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(TokenAuthenticator())

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class UserController:
            @Get("/me")
            async def me(self, auth: Authentication) -> dict:
                """Authentication을 파라미터로 직접 주입받음"""
                if auth is None:
                    return {"authenticated": False}
                return {
                    "user_id": auth.user_id,
                    "authenticated": auth.authenticated,
                    "authorities": auth.authorities,
                }

        app = Application("test").scan(M).ready()

        # 인증 성공
        request = HttpRequest(
            method="GET",
            path="/me",
            headers={"Authorization": "Bearer valid-token"},
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["user_id"] == "user123"
        assert response.body["authenticated"] is True
        assert response.body["authorities"] == ["read", "write"]

    @pytest.mark.asyncio
    async def test_optional_authentication_resolver(self):
        """Optional[Authentication] 파라미터 주입"""

        class M:
            pass

        class OptionalAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                token = request.headers.get("Authorization")
                if token == "Bearer valid":
                    return Authentication(user_id="user1", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return True

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(OptionalAuthenticator())

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class UserController:
            @Get("/profile")
            async def profile(self, auth: Authentication | None) -> dict:
                """Optional Authentication - 인증 없어도 통과"""
                if auth is None or not auth.authenticated:
                    return {"guest": True}
                return {"user_id": auth.user_id, "guest": False}

        app = Application("test").scan(M).ready()

        # 인증 없이 요청
        request1 = HttpRequest(method="GET", path="/profile")
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 200
        assert response1.body == {"guest": True}

        # 인증 있는 요청
        request2 = HttpRequest(
            method="GET", path="/profile", headers={"Authorization": "Bearer valid"}
        )
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 200
        assert response2.body == {"user_id": "user1", "guest": False}

    @pytest.mark.asyncio
    async def test_authentication_with_path_params(self):
        """Authentication + path param 조합"""

        class M:
            pass

        class ApiKeyAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("X-API-Key") == "secret":
                    return Authentication(
                        user_id="api-user",
                        authenticated=True,
                        authorities=["admin"],
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "X-API-Key" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(ApiKeyAuthenticator()).require()

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class ResourceController:
            @Get("/resources/{id}")
            async def get_resource(self, id: str, auth: Authentication) -> dict:
                """path param + Authentication 동시 주입"""
                return {
                    "resource_id": id,
                    "accessed_by": auth.user_id,
                    "is_admin": "admin" in auth.authorities,
                }

        app = Application("test").scan(M).ready()

        request = HttpRequest(
            method="GET", path="/resources/42", headers={"X-API-Key": "secret"}
        )
        response = await app.router.dispatch(request)

        assert response.status_code == 200
        assert response.body["resource_id"] == "42"
        assert response.body["accessed_by"] == "api-user"
        assert response.body["is_admin"] is True

    @pytest.mark.asyncio
    async def test_authentication_authorities_check(self):
        """Authentication.has_authority() 체크"""

        class M:
            pass

        class RoleAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                role = request.headers.get("X-Role")
                if role == "admin":
                    return Authentication(
                        user_id="admin1",
                        authenticated=True,
                        authorities=["ADMIN", "USER"],
                    )
                elif role == "user":
                    return Authentication(
                        user_id="user1", authenticated=True, authorities=["USER"]
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "X-Role" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(RoleAuthenticator()).require()

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class AdminController:
            @Get("/admin/action")
            async def admin_action(self, auth: Authentication) -> dict:
                """권한 체크"""
                if not auth.has_authority("ADMIN"):
                    return {"error": "Forbidden", "status": 403}
                return {"action": "performed", "by": auth.user_id}

        app = Application("test").scan(M).ready()

        # Admin 권한
        request1 = HttpRequest(
            method="GET", path="/admin/action", headers={"X-Role": "admin"}
        )
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 200
        assert response1.body["action"] == "performed"

        # User 권한 - Forbidden
        request2 = HttpRequest(
            method="GET", path="/admin/action", headers={"X-Role": "user"}
        )
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 200  # 핸들러까지 도달
        assert response2.body["error"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_group_auth_with_resolver(self):
        """그룹별 인증 + AuthenticationResolver 통합"""

        class M:
            pass

        class ApiAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("X-API-Key") == "api-key":
                    return Authentication(
                        user_id="api-client",
                        authenticated=True,
                        details={"type": "api"},
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "X-API-Key" in request.headers

        class WebAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("Cookie") == "session=valid":
                    return Authentication(
                        user_id="web-user",
                        authenticated=True,
                        details={"type": "web"},
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Cookie" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    .group("api")
                    .register(ApiAuthenticator())
                    .include("/api/")
                    .require()
                    .group("web")
                    .register(WebAuthenticator())
                    .include("/web/")
                    .require()
                )

            @Factory
            def middleware_chain(
                self, auth_middleware: AuthMiddleware
            ) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth_middleware)
                return chain

        @Module(M)
        @Controller
        class MultiController:
            @Get("/api/info")
            async def api_info(self, auth: Authentication) -> dict:
                return {"user": auth.user_id, "type": auth.details.get("type")}

            @Get("/web/info")
            async def web_info(self, auth: Authentication) -> dict:
                return {"user": auth.user_id, "type": auth.details.get("type")}

        app = Application("test").scan(M).ready()

        # API 인증
        request1 = HttpRequest(
            method="GET", path="/api/info", headers={"X-API-Key": "api-key"}
        )
        response1 = await app.router.dispatch(request1)
        assert response1.status_code == 200
        assert response1.body == {"user": "api-client", "type": "api"}

        # Web 인증
        request2 = HttpRequest(
            method="GET", path="/web/info", headers={"Cookie": "session=valid"}
        )
        response2 = await app.router.dispatch(request2)
        assert response2.status_code == 200
        assert response2.body == {"user": "web-user", "type": "web"}


class TestAuthorizeDecorator:
    """@Authorize 데코레이터와 AuthMiddleware 결합 테스트"""

    @pytest.mark.asyncio
    async def test_authorize_authenticated_user_access(self):
        """인증된 사용자가 @Authorize 엔드포인트에 접근 성공"""
        from bloom.web.auth import Authorize

        class M:
            pass

        class TokenAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("Authorization") == "Bearer valid":
                    return Authentication(user_id="user1", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(TokenAuthenticator())

            @Factory
            def middleware_chain(self, auth: AuthMiddleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth)
                return chain

        @Module(M)
        @Controller
        class ProtectedController:
            @Authorize(Authentication, lambda auth: auth.is_authenticated())
            @Get("/protected")
            async def protected(self) -> str:
                return "protected content"

        app = Application("test").scan(M).ready()

        # 인증된 사용자 - 접근 성공
        request = HttpRequest(
            method="GET", path="/protected", headers={"Authorization": "Bearer valid"}
        )
        response = await app.router.dispatch(request)
        assert response.status_code == 200
        assert response.body == "protected content"

    @pytest.mark.asyncio
    async def test_authorize_unauthenticated_user_forbidden(self):
        """인증되지 않은 사용자가 @Authorize 엔드포인트에 접근 시 403"""
        from bloom.web.auth import Authorize

        class M:
            pass

        class TokenAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                if request.headers.get("Authorization") == "Bearer valid":
                    return Authentication(user_id="user1", authenticated=True)
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(TokenAuthenticator())

            @Factory
            def middleware_chain(self, auth: AuthMiddleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth)
                return chain

        @Module(M)
        @Controller
        class ProtectedController:
            @Get("/protected")
            @Authorize(Authentication, lambda auth: auth.is_authenticated())
            async def protected(self) -> str:
                return "protected content"

        app = Application("test").scan(M).ready()

        # 인증되지 않은 사용자 - 403 Forbidden
        request = HttpRequest(method="GET", path="/protected")
        response = await app.router.dispatch(request)
        assert response.status_code == 403
        assert response.body["error"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_authorize_with_authority_check(self):
        """권한 검사 - has_authority 사용"""
        from bloom.web.auth import Authorize

        class M:
            pass

        class TokenAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if token == "admin":
                    return Authentication(
                        user_id="admin", authenticated=True, authorities=["ADMIN"]
                    )
                elif token == "user":
                    return Authentication(
                        user_id="user", authenticated=True, authorities=["USER"]
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(TokenAuthenticator())

            @Factory
            def middleware_chain(self, auth: AuthMiddleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth)
                return chain

        @Module(M)
        @Controller
        class AdminController:
            @Get("/admin")
            @Authorize(Authentication, lambda auth: auth.has_authority("ADMIN"))
            async def admin_only(self) -> str:
                return "admin area"

        app = Application("test").scan(M).ready()

        # ADMIN 권한 있는 사용자 - 접근 성공
        admin_request = HttpRequest(
            method="GET", path="/admin", headers={"Authorization": "Bearer admin"}
        )
        admin_response = await app.router.dispatch(admin_request)
        assert admin_response.status_code == 200
        assert admin_response.body == "admin area"

        # USER 권한만 있는 사용자 - 403 Forbidden
        user_request = HttpRequest(
            method="GET", path="/admin", headers={"Authorization": "Bearer user"}
        )
        user_response = await app.router.dispatch(user_request)
        assert user_response.status_code == 403
        assert user_response.body["error"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_authorize_with_custom_predicate(self):
        """커스텀 predicate 사용"""
        from bloom.web.auth import Authorize

        class M:
            pass

        class TokenAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if token == "premium":
                    return Authentication(
                        user_id="premium_user",
                        authenticated=True,
                        details={"plan": "premium"},
                    )
                elif token == "free":
                    return Authentication(
                        user_id="free_user",
                        authenticated=True,
                        details={"plan": "free"},
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(TokenAuthenticator())

            @Factory
            def middleware_chain(self, auth: AuthMiddleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth)
                return chain

        @Module(M)
        @Controller
        class PremiumController:
            @Get("/premium")
            @Authorize(
                Authentication, lambda auth: auth.details.get("plan") == "premium"
            )
            async def premium_content(self) -> str:
                return "premium content"

        app = Application("test").scan(M).ready()

        # Premium 사용자 - 접근 성공
        premium_request = HttpRequest(
            method="GET", path="/premium", headers={"Authorization": "Bearer premium"}
        )
        premium_response = await app.router.dispatch(premium_request)
        assert premium_response.status_code == 200
        assert premium_response.body == "premium content"

        # Free 사용자 - 403 Forbidden
        free_request = HttpRequest(
            method="GET", path="/premium", headers={"Authorization": "Bearer free"}
        )
        free_response = await app.router.dispatch(free_request)
        assert free_response.status_code == 403

    @pytest.mark.asyncio
    async def test_authorize_with_require_auth_group(self):
        """require()로 인증 필수 그룹과 @Authorize 결합"""
        from bloom.web.auth import Authorize

        class M:
            pass

        class TokenAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if token == "admin":
                    return Authentication(
                        user_id="admin", authenticated=True, authorities=["ADMIN"]
                    )
                elif token == "user":
                    return Authentication(
                        user_id="user", authenticated=True, authorities=["USER"]
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return (
                    AuthMiddleware()
                    .group("api")
                    .register(TokenAuthenticator())
                    .include("/api/")
                    .require()  # 인증 필수
                )

            @Factory
            def middleware_chain(self, auth: AuthMiddleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth)
                return chain

        @Module(M)
        @Controller
        class ApiController:
            @Get("/api/admin")
            @Authorize(Authentication, lambda auth: auth.has_authority("ADMIN"))
            async def admin_api(self) -> str:
                return "admin api"

            @Get("/api/user")
            async def user_api(self) -> str:
                return "user api"

        app = Application("test").scan(M).ready()

        # 인증 없이 접근 - 401 Unauthorized (require() 때문)
        no_auth_request = HttpRequest(method="GET", path="/api/admin")
        no_auth_response = await app.router.dispatch(no_auth_request)
        assert no_auth_response.status_code == 401

        # USER로 admin API 접근 - 403 Forbidden (@Authorize 때문)
        user_request = HttpRequest(
            method="GET", path="/api/admin", headers={"Authorization": "Bearer user"}
        )
        user_response = await app.router.dispatch(user_request)
        assert user_response.status_code == 403

        # ADMIN으로 admin API 접근 - 성공
        admin_request = HttpRequest(
            method="GET", path="/api/admin", headers={"Authorization": "Bearer admin"}
        )
        admin_response = await app.router.dispatch(admin_request)
        assert admin_response.status_code == 200
        assert admin_response.body == "admin api"

        # USER로 user API 접근 - 성공 (@Authorize 없음)
        user_api_request = HttpRequest(
            method="GET", path="/api/user", headers={"Authorization": "Bearer user"}
        )
        user_api_response = await app.router.dispatch(user_api_request)
        assert user_api_response.status_code == 200
        assert user_api_response.body == "user api"

    @pytest.mark.asyncio
    async def test_authorize_multiple_decorators(self):
        """여러 @Authorize 데코레이터 사용"""
        from bloom.web.auth import Authorize

        class M:
            pass

        class TokenAuthenticator(Authenticator):
            def authenticate(self, request: HttpRequest) -> Authentication | None:
                token = request.headers.get("Authorization", "").replace("Bearer ", "")
                if token == "super":
                    return Authentication(
                        user_id="super",
                        authenticated=True,
                        authorities=["ADMIN", "MANAGER"],
                    )
                elif token == "admin":
                    return Authentication(
                        user_id="admin", authenticated=True, authorities=["ADMIN"]
                    )
                elif token == "manager":
                    return Authentication(
                        user_id="manager", authenticated=True, authorities=["MANAGER"]
                    )
                return None

            def supports(self, request: HttpRequest) -> bool:
                return "Authorization" in request.headers

        @Module(M)
        @Component
        class MiddlewareConfig:
            @Factory
            def auth_middleware(self) -> AuthMiddleware:
                return AuthMiddleware().register(TokenAuthenticator())

            @Factory
            def middleware_chain(self, auth: AuthMiddleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.default_group.add(auth)
                return chain

        @Module(M)
        @Controller
        class SuperController:
            @Get("/super")
            @Authorize(Authentication, lambda auth: auth.has_authority("ADMIN"))
            @Authorize(Authentication, lambda auth: auth.has_authority("MANAGER"))
            async def super_only(self) -> str:
                return "super area"

        app = Application("test").scan(M).ready()

        # ADMIN + MANAGER 권한 있는 사용자 - 접근 성공
        super_request = HttpRequest(
            method="GET", path="/super", headers={"Authorization": "Bearer super"}
        )
        super_response = await app.router.dispatch(super_request)
        assert super_response.status_code == 200
        assert super_response.body == "super area"

        # ADMIN만 있는 사용자 - 403 (MANAGER 없음)
        admin_request = HttpRequest(
            method="GET", path="/super", headers={"Authorization": "Bearer admin"}
        )
        admin_response = await app.router.dispatch(admin_request)
        assert admin_response.status_code == 403

        # MANAGER만 있는 사용자 - 403 (ADMIN 없음)
        manager_request = HttpRequest(
            method="GET", path="/super", headers={"Authorization": "Bearer manager"}
        )
        manager_response = await app.router.dispatch(manager_request)
        assert manager_response.status_code == 403
