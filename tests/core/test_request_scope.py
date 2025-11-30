"""REQUEST 스코프 테스트"""

import pytest
from bloom import Application, Component, Scope, PostConstruct, PreDestroy
from bloom.core import ScopeEnum, RequestContext, request_scope


class TestRequestScope:
    """REQUEST 스코프 기본 동작 테스트"""

    def test_request_scope_instance_per_context(self, reset_container_manager):
        """REQUEST 스코프는 요청 컨텍스트마다 새 인스턴스 생성"""
        instance_ids = []

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestService:
            def get_id(self):
                return id(self)

        @Component
        class Consumer:
            service: RequestService

        app = Application("test").ready()
        consumer = app.manager.get_instance(Consumer)

        # 첫 번째 요청 컨텍스트
        with request_scope():
            id1 = consumer.service.get_id()
            id1_again = consumer.service.get_id()
            instance_ids.append(id1)
            # 같은 요청 내에서는 동일 인스턴스
            assert id1 == id1_again

        # 두 번째 요청 컨텍스트
        with request_scope():
            id2 = consumer.service.get_id()
            instance_ids.append(id2)

        # 다른 요청은 다른 인스턴스
        assert instance_ids[0] != instance_ids[1]

    def test_request_scope_without_context_raises_error(self, reset_container_manager):
        """컨텍스트 없이 REQUEST 스코프 접근 시 에러"""

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestService:
            def do_something(self):
                pass

        @Component
        class Consumer:
            service: RequestService

        app = Application("test").ready()
        consumer = app.manager.get_instance(Consumer)

        # 컨텍스트 없이 메서드 호출하면 에러
        with pytest.raises(RuntimeError, match="REQUEST scope requires active request context"):
            consumer.service.do_something()

    def test_request_context_is_active(self, reset_container_manager):
        """RequestContext.is_active() 동작 확인"""
        assert not RequestContext.is_active()

        with request_scope():
            assert RequestContext.is_active()

        assert not RequestContext.is_active()


class TestRequestScopeLifecycle:
    """REQUEST 스코프 라이프사이클 테스트"""

    def test_post_construct_on_first_access(self, reset_container_manager):
        """REQUEST 인스턴스 첫 접근 시 @PostConstruct 호출"""
        call_log = []

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestService:
            @PostConstruct
            def init(self):
                call_log.append(f"init:{id(self)}")

            def get_id(self):
                return id(self)

        @Component
        class Consumer:
            service: RequestService

        app = Application("test").ready()
        consumer = app.manager.get_instance(Consumer)

        # 아직 호출 안됨
        assert len(call_log) == 0

        with request_scope():
            service_id = consumer.service.get_id()
            # 첫 접근 시 호출됨
            assert len(call_log) == 1
            assert f"init:{service_id}" in call_log

            # 같은 요청 내 재접근 시 다시 호출 안됨
            _ = consumer.service.get_id()
            assert len(call_log) == 1

    def test_pre_destroy_on_context_end(self, reset_container_manager):
        """요청 컨텍스트 종료 시 @PreDestroy 호출"""
        call_log = []

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestService:
            @PostConstruct
            def init(self):
                call_log.append(f"init:{id(self)}")

            @PreDestroy
            def cleanup(self):
                call_log.append(f"cleanup:{id(self)}")

            def get_id(self):
                return id(self)

        @Component
        class Consumer:
            service: RequestService

        app = Application("test").ready()
        consumer = app.manager.get_instance(Consumer)

        with request_scope():
            service_id = consumer.service.get_id()
            assert f"init:{service_id}" in call_log
            # 컨텍스트 내에서는 cleanup 아직 안됨
            assert f"cleanup:{service_id}" not in call_log

        # 컨텍스트 종료 후 cleanup 호출됨
        assert f"cleanup:{service_id}" in call_log

    def test_multiple_request_instances_cleanup(self, reset_container_manager):
        """여러 REQUEST 인스턴스가 역순으로 정리됨"""
        call_log = []

        @Component
        @Scope(ScopeEnum.REQUEST)
        class ServiceA:
            @PreDestroy
            def cleanup(self):
                call_log.append("cleanup:A")

            def touch(self):
                pass

        @Component
        @Scope(ScopeEnum.REQUEST)
        class ServiceB:
            @PreDestroy
            def cleanup(self):
                call_log.append("cleanup:B")

            def touch(self):
                pass

        @Component
        class Consumer:
            a: ServiceA
            b: ServiceB

        app = Application("test").ready()
        consumer = app.manager.get_instance(Consumer)

        with request_scope():
            consumer.a.touch()  # A 먼저 생성
            consumer.b.touch()  # B 나중 생성

        # 역순으로 정리 (B → A)
        assert call_log == ["cleanup:B", "cleanup:A"]


class TestRequestScopeWithSingleton:
    """REQUEST 스코프와 SINGLETON 혼합 테스트"""

    def test_request_scope_with_singleton_dependency(self, reset_container_manager):
        """REQUEST 컴포넌트가 SINGLETON 의존성을 가질 수 있음"""

        @Component
        class SingletonService:
            def get_id(self):
                return id(self)

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestService:
            singleton: SingletonService

            def get_singleton_id(self):
                return self.singleton.get_id()

        @Component
        class Consumer:
            request_svc: RequestService

        app = Application("test").ready()
        consumer = app.manager.get_instance(Consumer)

        singleton_ids = []

        with request_scope():
            singleton_ids.append(consumer.request_svc.get_singleton_id())

        with request_scope():
            singleton_ids.append(consumer.request_svc.get_singleton_id())

        # SINGLETON은 동일 인스턴스
        assert singleton_ids[0] == singleton_ids[1]

    def test_singleton_with_request_dependency_fails_outside_context(
        self, reset_container_manager
    ):
        """SINGLETON이 REQUEST 의존성에 접근하면 컨텍스트 필요"""

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestService:
            def do_something(self):
                pass

        @Component
        class SingletonService:
            request: RequestService

            def use_request(self):
                self.request.do_something()

        app = Application("test").ready()
        singleton = app.manager.get_instance(SingletonService)

        # 컨텍스트 없이 접근하면 에러
        with pytest.raises(RuntimeError):
            singleton.use_request()

        # 컨텍스트 내에서는 정상
        with request_scope():
            singleton.use_request()


@pytest.mark.asyncio
class TestRequestScopeAsync:
    """REQUEST 스코프 비동기 테스트"""

    async def test_async_request_scope(self, reset_container_manager):
        """async with request_scope() 동작 확인"""
        call_log = []

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestService:
            @PostConstruct
            def init(self):
                call_log.append("init")

            @PreDestroy
            def cleanup(self):
                call_log.append("cleanup")

            def touch(self):
                pass

        @Component
        class Consumer:
            service: RequestService

        app = Application("test").ready()
        consumer = app.manager.get_instance(Consumer)

        async with request_scope():
            consumer.service.touch()
            assert "init" in call_log
            assert "cleanup" not in call_log

        assert "cleanup" in call_log


@pytest.mark.asyncio
class TestRequestScopeASGI:
    """ASGI 레벨 REQUEST 스코프 테스트"""

    async def test_asgi_request_scope_lifecycle(self, reset_container_manager):
        """ASGI에서 REQUEST 스코프 라이프사이클 자동 관리"""
        call_log = []

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestSession:
            @PostConstruct
            def init(self):
                call_log.append("init")

            @PreDestroy
            def cleanup(self):
                call_log.append("cleanup")

            def get_user(self):
                return "test_user"

        from bloom.web import Controller, Get

        @Controller
        class TestController:
            session: RequestSession

            @Get("/test")
            def test_endpoint(self) -> dict:
                return {"user": self.session.get_user()}

        app = Application("test").ready()

        # ASGI 앱 생성
        asgi = app.asgi

        # 테스트용 ASGI 스코프
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
        }

        received_body = []
        sent_messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent_messages.append(message)

        # ASGI 호출
        await asgi(scope, receive, send)

        # 라이프사이클 확인
        assert "init" in call_log
        assert "cleanup" in call_log

        # init이 cleanup보다 먼저 호출됨
        assert call_log.index("init") < call_log.index("cleanup")

    async def test_asgi_request_scope_in_middleware(self, reset_container_manager):
        """미들웨어에서도 REQUEST 스코프 사용 가능"""
        middleware_access_log = []

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestSession:
            request_id: str = ""

            def set_id(self, rid: str):
                self.request_id = rid

            def get_id(self):
                return self.request_id

        from bloom.web import Controller, Get
        from bloom.web.middleware import Middleware, MiddlewareChain
        from bloom.core.decorators import Factory

        @Component
        class RequestIdMiddleware(Middleware):
            session: RequestSession

            async def process_request(self, request):
                # 미들웨어에서 REQUEST 스코프 접근
                self.session.set_id("req-123")
                middleware_access_log.append(f"set:{self.session.get_id()}")
                return None

        @Component
        class MiddlewareConfig:
            @Factory
            def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.add_group_after(*middlewares)
                return chain

        @Controller
        class TestController:
            session: RequestSession

            @Get("/test")
            def test_endpoint(self) -> dict:
                # 핸들러에서도 같은 인스턴스 접근
                return {"request_id": self.session.get_id()}

        app = Application("test").ready()
        asgi = app.asgi

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
        }

        sent_messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent_messages.append(message)

        await asgi(scope, receive, send)

        # 미들웨어에서 REQUEST 스코프 접근 성공
        assert middleware_access_log == ["set:req-123"]

        # 응답 확인
        body_message = sent_messages[-1]
        import json

        body = json.loads(body_message["body"])
        assert body["request_id"] == "req-123"
