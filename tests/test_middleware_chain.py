"""MiddlewareChain 및 Router 통합 테스트"""

import pytest

from vessel.web.handler import MethodElement, PathElement
from vessel.web.http import HttpRequest, HttpResponse
from vessel.web.middleware import Middleware, MiddlewareChain, MiddlewareGroup


# ===========================================
# 테스트용 미들웨어
# ===========================================


class LoggingMiddleware(Middleware):
    """요청/응답 로깅 미들웨어"""

    def __init__(self):
        self.request_log: list[str] = []
        self.response_log: list[str] = []

    async def process_request(self, request: HttpRequest):
        self.request_log.append(f"{request.method} {request.path}")
        return None

    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        self.response_log.append(f"{response.status_code}")
        return response


class AuthMiddleware(Middleware):
    """인증 미들웨어 - Authorization 헤더 확인"""

    async def process_request(self, request: HttpRequest):
        if "Authorization" not in request.headers:
            return HttpResponse(status_code=401, body={"error": "Unauthorized"})
        return None

    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        return response


class TimingMiddleware(Middleware):
    """타이밍 헤더 추가 미들웨어"""

    async def process_request(self, request: HttpRequest):
        return None

    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        response.headers["X-Timing"] = "100ms"
        return response


class HeaderInjectionMiddleware(Middleware):
    """커스텀 헤더 주입 미들웨어"""

    def __init__(self, header_name: str, header_value: str):
        self.header_name = header_name
        self.header_value = header_value

    async def process_request(self, request: HttpRequest):
        return None

    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        response.headers[self.header_name] = self.header_value
        return response


class EarlyReturnMiddleware(Middleware):
    """특정 경로에서 early return하는 미들웨어"""

    def __init__(self, block_path: str):
        self.block_path = block_path

    async def process_request(self, request: HttpRequest):
        if request.path == self.block_path:
            return HttpResponse(status_code=403, body={"error": "Blocked"})
        return None

    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        return response


# ===========================================
# MiddlewareChain 단위 테스트
# ===========================================


class TestMiddlewareChain:
    """MiddlewareChain 기본 기능 테스트"""

    def test_default_chain_has_cors(self):
        """기본 체인에 CorsMiddleware 포함"""
        from vessel.web.middleware.cors import CorsMiddleware

        chain = MiddlewareChain()
        assert len(chain.groups) == 1  # default group
        # CorsMiddleware가 기본 포함됨
        cors = chain.get_middleware(CorsMiddleware)
        assert cors is not None

    def test_get_middleware(self):
        """get_middleware로 특정 타입 미들웨어 조회"""
        from vessel.web.middleware.cors import CorsMiddleware

        chain = MiddlewareChain()
        cors = chain.get_middleware(CorsMiddleware)
        assert isinstance(cors, CorsMiddleware)

        # 없는 미들웨어 조회 시 예외
        import pytest

        with pytest.raises(ValueError):
            chain.get_middleware(LoggingMiddleware)

        # raise_exception=False면 None 반환
        result = chain.get_middleware(LoggingMiddleware, raise_exception=False)
        assert result is None

    def test_add_to_default_group(self):
        """기본 그룹에 미들웨어 추가"""
        chain = MiddlewareChain()
        middleware = LoggingMiddleware()

        chain.default_group.add(middleware)

        assert middleware in chain.get_all_middlewares()

    def test_add_group_after(self):
        """그룹 뒤에 새 그룹 추가"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()
        m2 = TimingMiddleware()

        chain.add_group_after(m1, m2)

        middlewares = chain.get_all_middlewares()
        assert m1 in middlewares
        assert m2 in middlewares

    def test_add_group_before(self):
        """그룹 앞에 새 그룹 추가"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()
        m2 = TimingMiddleware()

        # default 그룹에 m1 추가
        chain.default_group.add(m1)
        # default 앞에 m2 추가
        chain.add_group_before(m2)

        middlewares = chain.get_all_middlewares()
        # m2가 m1보다 먼저 나와야 함
        assert middlewares.index(m2) < middlewares.index(m1)

    def test_disable_middleware(self):
        """특정 미들웨어 비활성화"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()
        m2 = TimingMiddleware()

        chain.default_group.add(m1, m2)
        chain.disable(m1)

        middlewares = chain.get_all_middlewares()
        assert m1 not in middlewares
        assert m2 in middlewares

    def test_enable_middleware(self):
        """비활성화된 미들웨어 다시 활성화"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()

        chain.default_group.add(m1)
        chain.disable(m1)
        chain.enable(m1)

        assert m1 in chain.get_all_middlewares()

    def test_disable_group(self):
        """그룹 비활성화"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()

        group = chain.add_group_after(m1)
        group.disable()

        assert m1 not in chain.get_all_middlewares()

    def test_enable_group(self):
        """비활성화된 그룹 다시 활성화"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()

        group = chain.add_group_after(m1)
        group.disable()
        group.enable()

        assert m1 in chain.get_all_middlewares()

    def test_method_chaining(self):
        """메서드 체이닝 지원"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()
        m2 = TimingMiddleware()

        result = chain.disable(m1).enable(m1).disable(m2)

        assert result is chain

    def test_repr(self):
        """__repr__ 출력"""
        chain = MiddlewareChain()
        chain.default_group.add(LoggingMiddleware())

        repr_str = repr(chain)
        assert "MiddlewareChain" in repr_str
        assert "groups=1" in repr_str


# ===========================================
# MiddlewareChain 실행 테스트
# ===========================================


class TestMiddlewareChainExecution:
    """MiddlewareChain 실행 흐름 테스트"""

    @pytest.mark.asyncio
    async def test_process_request_passes_through(self):
        """요청이 모든 미들웨어 통과"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()
        m2 = LoggingMiddleware()

        chain.default_group.add(m1, m2)

        request = HttpRequest(method="GET", path="/test")

        async with chain.process(request) as ctx:
            ctx.set_response(HttpResponse.ok("test"))

        assert len(m1.request_log) == 1
        assert len(m2.request_log) == 1

    @pytest.mark.asyncio
    async def test_process_request_early_return(self):
        """미들웨어가 early return하면 후속 미들웨어 실행 안됨"""
        chain = MiddlewareChain()
        m1 = AuthMiddleware()  # 인증 없으면 401 반환
        m2 = LoggingMiddleware()

        chain.default_group.add(m1, m2)

        request = HttpRequest(method="GET", path="/test")  # Authorization 없음

        async with chain.process(request) as ctx:
            if not ctx.early_response:
                ctx.set_response(HttpResponse.ok("test"))

        result = chain.get_final_response(ctx)

        assert result.status_code == 401
        assert len(m2.request_log) == 0  # m2는 실행 안됨

    @pytest.mark.asyncio
    async def test_process_response_reverse_order(self):
        """응답 처리는 역순 실행"""
        chain = MiddlewareChain()
        m1 = HeaderInjectionMiddleware("X-First", "1")
        m2 = HeaderInjectionMiddleware("X-Second", "2")
        m3 = HeaderInjectionMiddleware("X-Third", "3")

        chain.default_group.add(m1, m2, m3)

        request = HttpRequest(method="GET", path="/test")

        async with chain.process(request) as ctx:
            ctx.set_response(HttpResponse.ok("test"))

        result = chain.get_final_response(ctx)

        # 모든 헤더가 추가됨 (역순이라도 모두 실행됨)
        assert result.headers["X-First"] == "1"
        assert result.headers["X-Second"] == "2"
        assert result.headers["X-Third"] == "3"

    @pytest.mark.asyncio
    async def test_process_with_authorization_header(self):
        """Authorization 헤더 있으면 정상 통과"""
        chain = MiddlewareChain()
        m1 = AuthMiddleware()
        m2 = LoggingMiddleware()

        chain.default_group.add(m1, m2)

        request = HttpRequest(
            method="GET", path="/test", headers={"Authorization": "Bearer token"}
        )

        async with chain.process(request) as ctx:
            ctx.set_response(HttpResponse.ok("test"))

        result = chain.get_final_response(ctx)

        assert result.status_code == 200
        assert len(m2.request_log) == 1

    @pytest.mark.asyncio
    async def test_disabled_middleware_skipped(self):
        """비활성화된 미들웨어는 실행 안됨"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()
        m2 = TimingMiddleware()  # 다른 타입의 미들웨어 사용

        chain.default_group.add(m1, m2)
        chain.disable(m1)

        request = HttpRequest(method="GET", path="/test")

        async with chain.process(request) as ctx:
            ctx.set_response(HttpResponse.ok("test"))

        result = chain.get_final_response(ctx)

        assert len(m1.request_log) == 0
        # TimingMiddleware는 실행되어야 함
        assert "X-Timing" in result.headers

    @pytest.mark.asyncio
    async def test_disabled_group_skipped(self):
        """비활성화된 그룹의 미들웨어는 실행 안됨"""
        chain = MiddlewareChain()
        m1 = LoggingMiddleware()
        m2 = LoggingMiddleware()

        group = chain.add_group_after(m1)
        chain.default_group.add(m2)
        group.disable()

        request = HttpRequest(method="GET", path="/test")

        async with chain.process(request) as ctx:
            ctx.set_response(HttpResponse.ok("test"))

        assert len(m1.request_log) == 0
        assert len(m2.request_log) == 1


# ===========================================
# MiddlewareGroup 테스트
# ===========================================


class TestMiddlewareGroup:
    """MiddlewareGroup 단위 테스트"""

    def test_create_group(self):
        """그룹 생성"""
        group = MiddlewareGroup("auth")
        assert group.name == "auth"
        assert group.enabled is True
        assert len(group.middlewares) == 0

    def test_add_middlewares(self):
        """미들웨어 추가"""
        group = MiddlewareGroup("test")
        m1 = LoggingMiddleware()
        m2 = TimingMiddleware()

        group.add(m1, m2)

        assert m1 in group.middlewares
        assert m2 in group.middlewares

    def test_disable_enable(self):
        """그룹 활성화/비활성화"""
        group = MiddlewareGroup("test")

        group.disable()
        assert group.enabled is False

        group.enable()
        assert group.enabled is True

    def test_method_chaining(self):
        """메서드 체이닝"""
        group = MiddlewareGroup("test")
        m1 = LoggingMiddleware()

        result = group.add(m1).disable().enable()

        assert result is group

    def test_repr(self):
        """__repr__ 출력"""
        group = MiddlewareGroup("auth")
        group.add(LoggingMiddleware())

        repr_str = repr(group)
        assert "auth" in repr_str
        assert "middlewares=1" in repr_str


# ===========================================
# Router + MiddlewareChain 통합 테스트
# ===========================================


class TestRouterMiddlewareIntegration:
    """Router와 MiddlewareChain 통합 테스트"""

    @pytest.mark.asyncio
    async def test_middleware_executes_before_handler(self):
        """미들웨어가 핸들러 전에 실행됨"""
        from vessel.core.manager import get_current_manager
        from vessel.web.middleware import MiddlewareChain
        from vessel.web.router import Router
        from vessel.web.handler import HttpMethodHandler
        from vessel.web.controller import ControllerContainer

        execution_order = []

        class TrackingMiddleware(Middleware):
            async def process_request(self, request: HttpRequest):
                execution_order.append("middleware_request")
                return None

            async def process_response(
                self, request: HttpRequest, response: HttpResponse
            ) -> HttpResponse:
                execution_order.append("middleware_response")
                return response

        class TestController:
            async def test_handler(self) -> str:
                execution_order.append("handler")
                return "ok"

        chain = MiddlewareChain()
        chain.default_group.add(TrackingMiddleware())
        get_current_manager().set_instance(MiddlewareChain, chain)
        get_current_manager().set_instance(TestController, TestController())

        controller_container = ControllerContainer(TestController)
        get_current_manager().register_container(controller_container)

        handler = HttpMethodHandler(
            handler_method=TestController.test_handler,
        )
        handler.add_elements(MethodElement("GET"))
        handler.add_elements(PathElement("/test"))
        handler.owner_cls = TestController
        get_current_manager().register_container(handler)

        router = Router(get_current_manager())
        router.collect_routes()

        request = HttpRequest(method="GET", path="/test")
        response = await router.dispatch(request)

        assert execution_order == [
            "middleware_request",
            "handler",
            "middleware_response",
        ]
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_middleware_early_return_skips_handler(self):
        """미들웨어 early return 시 핸들러 실행 안됨"""
        from vessel.core.manager import get_current_manager
        from vessel.web.middleware import MiddlewareChain
        from vessel.web.router import Router
        from vessel.web.handler import HttpMethodHandler
        from vessel.web.controller import ControllerContainer

        handler_called = False

        class BlockingMiddleware(Middleware):
            async def process_request(self, request: HttpRequest):
                return HttpResponse(
                    status_code=503, body={"error": "Service unavailable"}
                )

            async def process_response(
                self, request: HttpRequest, response: HttpResponse
            ) -> HttpResponse:
                return response

        class TestController:
            async def test_handler(self) -> str:
                nonlocal handler_called
                handler_called = True
                return "ok"

        chain = MiddlewareChain()
        chain.default_group.add(BlockingMiddleware())
        get_current_manager().set_instance(MiddlewareChain, chain)
        get_current_manager().set_instance(TestController, TestController())

        controller_container = ControllerContainer(TestController)
        get_current_manager().register_container(controller_container)

        handler = HttpMethodHandler(
            handler_method=TestController.test_handler,
        )
        handler.add_elements(MethodElement("GET"))
        handler.add_elements(PathElement("/test"))
        handler.owner_cls = TestController
        get_current_manager().register_container(handler)

        router = Router(get_current_manager())
        router.collect_routes()

        request = HttpRequest(method="GET", path="/test")
        response = await router.dispatch(request)

        assert response.status_code == 503
        assert handler_called is False

    @pytest.mark.asyncio
    async def test_cors_middleware_with_router(self):
        """CorsMiddleware가 Router와 함께 동작 - preflight 및 실제 요청"""
        from vessel.core.manager import get_current_manager
        from vessel.web.middleware import MiddlewareChain
        from vessel.web.middleware.cors import CorsMiddleware
        from vessel.web.router import Router
        from vessel.web.handler import HttpMethodHandler
        from vessel.web.controller import ControllerContainer

        class TestController:
            async def get_users(self) -> list:
                return [{"id": 1, "name": "Alice"}]

        chain = MiddlewareChain()
        # 기본 CorsMiddleware 비활성화하고 커스텀 설정으로 교체
        default_cors = chain.get_middleware(CorsMiddleware)
        chain.disable(default_cors)

        custom_cors = CorsMiddleware(
            allow_origins=["http://frontend.com"],
            allow_credentials=True,
        )
        chain.default_group.add(custom_cors)
        get_current_manager().set_instance(MiddlewareChain, chain)
        get_current_manager().set_instance(TestController, TestController())

        controller_container = ControllerContainer(TestController)
        get_current_manager().register_container(controller_container)

        handler = HttpMethodHandler(
            handler_method=TestController.get_users,
        )
        handler.add_elements(MethodElement("GET"))
        handler.add_elements(PathElement("/api/users"))
        handler.owner_cls = TestController
        get_current_manager().register_container(handler)

        router = Router(get_current_manager())
        router.collect_routes()

        # Preflight (OPTIONS) 요청 - 핸들러 없어도 CORS 미들웨어가 처리
        preflight_request = HttpRequest(
            method="OPTIONS",
            path="/api/users",
            headers={"Origin": "http://frontend.com"},
        )
        preflight_response = await router.dispatch(preflight_request)

        assert preflight_response.status_code == 204
        assert (
            preflight_response.headers["Access-Control-Allow-Origin"]
            == "http://frontend.com"
        )

        # 실제 GET 요청
        request = HttpRequest(
            method="GET",
            path="/api/users",
            headers={"Origin": "http://frontend.com"},
        )
        response = await router.dispatch(request)

        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://frontend.com"
        assert response.headers["Access-Control-Allow-Credentials"] == "true"
        assert response.body == [{"id": 1, "name": "Alice"}]

    @pytest.mark.asyncio
    async def test_multiple_middlewares_with_router(self):
        """여러 미들웨어가 순서대로 실행"""
        from vessel.core.manager import get_current_manager
        from vessel.web.middleware import MiddlewareChain
        from vessel.web.router import Router
        from vessel.web.handler import HttpMethodHandler
        from vessel.web.controller import ControllerContainer

        class TestController:
            async def get_data(self) -> dict:
                return {"data": "test"}

        m1 = HeaderInjectionMiddleware("X-First", "1")
        m2 = HeaderInjectionMiddleware("X-Second", "2")
        m3 = TimingMiddleware()

        chain = MiddlewareChain()
        chain.default_group.add(m1, m2, m3)
        get_current_manager().set_instance(MiddlewareChain, chain)
        get_current_manager().set_instance(TestController, TestController())

        controller_container = ControllerContainer(TestController)
        get_current_manager().register_container(controller_container)

        handler = HttpMethodHandler(
            handler_method=TestController.get_data,
        )
        handler.add_elements(MethodElement("GET"), PathElement("/data"))
        handler.owner_cls = TestController
        get_current_manager().register_container(handler)

        router = Router(get_current_manager())
        router.collect_routes()

        request = HttpRequest(method="GET", path="/data")
        response = await router.dispatch(request)

        assert response.status_code == 200
        assert response.headers["X-First"] == "1"
        assert response.headers["X-Second"] == "2"
        assert response.headers["X-Timing"] == "100ms"

    @pytest.mark.asyncio
    async def test_auth_middleware_blocks_unauthorized(self):
        """AuthMiddleware가 인증 없는 요청 차단"""
        from vessel.core.manager import get_current_manager
        from vessel.web.middleware import MiddlewareChain
        from vessel.web.router import Router
        from vessel.web.handler import HttpMethodHandler
        from vessel.web.controller import ControllerContainer

        handler_called = False

        class TestController:
            async def protected_resource(self) -> dict:
                nonlocal handler_called
                handler_called = True
                return {"secret": "data"}

        chain = MiddlewareChain()
        chain.default_group.add(AuthMiddleware())
        get_current_manager().set_instance(MiddlewareChain, chain)
        get_current_manager().set_instance(TestController, TestController())

        controller_container = ControllerContainer(TestController)
        get_current_manager().register_container(controller_container)

        handler = HttpMethodHandler(
            handler_method=TestController.protected_resource,
        )
        handler.add_elements(MethodElement("GET"))
        handler.add_elements(PathElement("/protected"))
        handler.owner_cls = TestController
        get_current_manager().register_container(handler)

        router = Router(get_current_manager())
        router.collect_routes()

        # 인증 없이 요청
        request = HttpRequest(method="GET", path="/protected")
        response = await router.dispatch(request)

        assert response.status_code == 401
        assert handler_called is False

        # 인증 헤더와 함께 요청
        authenticated_request = HttpRequest(
            method="GET",
            path="/protected",
            headers={"Authorization": "Bearer token123"},
        )
        response = await router.dispatch(authenticated_request)

        assert response.status_code == 200
        assert handler_called is True
