"""
Scope + Application 통합 테스트

Scope가 적용된 Factory와 Application의 통합을 테스트합니다.

- SINGLETON: 앱 전체에서 하나의 인스턴스
- CALL: @Handler 메서드 호출마다 새로 생성, 호출 끝나면 close
- REQUEST: HTTP 요청 단위로 인스턴스 공유
- @Transactional: 트랜잭션 내 인스턴스 공유
"""

import pytest
from bloom import Application
from bloom.core import get_container_manager, Handler, Service, Component
from bloom.core.decorators import Transactional
from bloom.core.container.scope import (
    Scope,
    call_scope_manager,
    request_scope,
    transactional_scope,
    get_call_scope,
    get_transactional_scope,
)

from tests.conftest import (
    DatabaseConnection,
    DatabaseSession,
    AsyncDatabaseSession,
    RequestContext,
    InfrastructureConfig,
    ScopedFactoryConfig,
)


class TestSingletonScopeIntegration:
    """SINGLETON 스코프 통합 테스트"""

    @pytest.mark.asyncio
    async def test_singleton_factory_returns_same_instance(
        self, application: Application
    ):
        """SINGLETON Factory는 항상 같은 인스턴스 반환"""
        await application.ready()
        manager = application.container_manager

        db1 = await manager.factory(DatabaseConnection)
        db2 = await manager.factory(DatabaseConnection)

        assert db1 is db2
        assert db1.connected is True

    @pytest.mark.asyncio
    async def test_singleton_factory_shared_across_components(
        self, application: Application
    ):
        """SINGLETON Factory는 여러 컴포넌트에서 공유"""
        await application.ready()
        manager = application.container_manager

        # 직접 조회
        db_direct = await manager.factory(DatabaseConnection)

        # MyComponent에 주입된 CacheClient도 같은 인스턴스
        from tests.conftest import MyComponent, CacheClient

        component = manager.instance(type=MyComponent)
        cache_from_component = component.cache_client
        cache_direct = await manager.factory(CacheClient)

        assert cache_from_component is cache_direct


class TestCallScopeIntegration:
    """CALL 스코프 통합 테스트"""

    def setup_method(self):
        DatabaseSession.reset_counters()
        AsyncDatabaseSession.reset_counters()

    @pytest.mark.asyncio
    async def test_call_scope_factory_not_initialized_at_startup(
        self, application: Application
    ):
        """CALL 스코프 Factory는 애플리케이션 시작 시 초기화되지 않음"""
        # 카운터 초기화
        DatabaseSession.reset_counters()
        initial_created = DatabaseSession._instance_count

        # 애플리케이션 시작
        await application.ready()

        # CALL 스코프 Factory는 시작 시점에 생성되지 않아야 함
        assert DatabaseSession._instance_count == initial_created, (
            f"CALL 스코프 Factory가 시작 시 생성됨: "
            f"created={DatabaseSession._instance_count - initial_created}"
        )

    @pytest.mark.asyncio
    async def test_call_scope_creates_new_instance_per_handler(
        self, application: Application
    ):
        """CALL 스코프 Factory는 핸들러마다 새 인스턴스 생성"""
        await application.ready()

        sessions = []

        @Service
        class TestService:
            @Handler
            async def handler1(self):
                ctx = get_call_scope()
                if ctx:
                    # 실제로는 ScopedProxy를 통해 접근하지만,
                    # 여기서는 직접 ScopeContext 테스트
                    session = DatabaseSession(DatabaseConnection("localhost", 5432))
                    session.__enter__()
                    ctx.register_closeable(session)
                    ctx.set("session", session)
                    sessions.append(session)
                return "handler1"

            @Handler
            async def handler2(self):
                ctx = get_call_scope()
                if ctx:
                    session = DatabaseSession(DatabaseConnection("localhost", 5432))
                    session.__enter__()
                    ctx.register_closeable(session)
                    ctx.set("session", session)
                    sessions.append(session)
                return "handler2"

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=TestService)

        # 핸들러 호출
        await service.handler1()
        await service.handler2()

        # 각각 다른 세션
        assert len(sessions) == 2
        assert sessions[0] is not sessions[1]

        # 둘 다 close됨
        assert not sessions[0].is_active
        assert not sessions[1].is_active

    @pytest.mark.asyncio
    async def test_call_scope_auto_closes_on_handler_exit(
        self, application: Application
    ):
        """CALL 스코프는 핸들러 종료 시 AutoCloseable 자동 close"""
        await application.ready()

        session_ref = []

        @Service
        class AutoCloseTestService:
            @Handler
            async def create_session(self):
                ctx = get_call_scope()
                session = DatabaseSession(DatabaseConnection("localhost", 5432))
                session.__enter__()
                ctx.register_closeable(session)
                session_ref.append(session)
                assert session.is_active
                return "created"

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=AutoCloseTestService)
        await service.create_session()

        # 핸들러 종료 후 자동 close
        assert len(session_ref) == 1
        assert not session_ref[0].is_active


class TestTransactionalIntegration:
    """@Transactional 통합 테스트"""

    def setup_method(self):
        DatabaseSession.reset_counters()
        AsyncDatabaseSession.reset_counters()

    @pytest.mark.asyncio
    async def test_transactional_shares_scope_context(self, application: Application):
        """@Transactional 내에서 같은 ScopeContext 공유"""
        await application.ready()

        context_ids = []

        @Service
        class TransactionalService:
            @Transactional
            async def outer_method(self):
                ctx = get_transactional_scope()
                context_ids.append(ctx.context_id)
                await self.inner_method()
                return "outer"

            @Transactional
            async def inner_method(self):
                ctx = get_transactional_scope()
                context_ids.append(ctx.context_id)
                return "inner"

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=TransactionalService)
        await service.outer_method()

        # 같은 context_id (중첩 transactional은 같은 context 공유)
        assert len(context_ids) == 2
        assert context_ids[0] == context_ids[1]

    @pytest.mark.asyncio
    async def test_transactional_auto_closes_on_exit(self, application: Application):
        """@Transactional 종료 시 AutoCloseable 자동 close"""
        await application.ready()

        session_ref = []

        @Service
        class TransactionalCloseService:
            @Transactional
            async def do_work(self):
                ctx = get_transactional_scope()
                session = DatabaseSession(DatabaseConnection("localhost", 5432))
                session.__enter__()
                ctx.register_closeable(session)
                session_ref.append(session)

                # 작업 수행
                session.execute("SELECT 1")
                assert session.is_active
                return "done"

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=TransactionalCloseService)
        result = await service.do_work()

        assert result == "done"
        assert len(session_ref) == 1
        assert not session_ref[0].is_active  # 자동 close됨

    @pytest.mark.asyncio
    async def test_transactional_with_handler(self, application: Application):
        """@Transactional + @Handler 조합 테스트"""
        await application.ready()

        call_order = []

        @Service
        class CombinedService:
            @Handler
            @Transactional
            async def handler_with_transaction(self):
                call_ctx = get_call_scope()
                trans_ctx = get_transactional_scope()

                call_order.append("call_scope" if call_ctx else "no_call")
                call_order.append("trans_scope" if trans_ctx else "no_trans")

                return "combined"

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=CombinedService)
        result = await service.handler_with_transaction()

        assert result == "combined"
        # 둘 다 있어야 함
        assert "call_scope" in call_order
        assert "trans_scope" in call_order

    @pytest.mark.asyncio
    async def test_transactional_exception_still_closes(self, application: Application):
        """@Transactional 예외 발생 시에도 close 실행"""
        await application.ready()

        session_ref = []

        @Service
        class ExceptionService:
            @Transactional
            async def failing_method(self):
                ctx = get_transactional_scope()
                session = DatabaseSession(DatabaseConnection("localhost", 5432))
                session.__enter__()
                ctx.register_closeable(session)
                session_ref.append(session)

                raise ValueError("Intentional error")

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=ExceptionService)

        with pytest.raises(ValueError, match="Intentional error"):
            await service.failing_method()

        # 예외에도 불구하고 close됨
        assert len(session_ref) == 1
        assert not session_ref[0].is_active


class TestScopeIsolation:
    """스코프 격리 테스트"""

    def setup_method(self):
        DatabaseSession.reset_counters()

    @pytest.mark.asyncio
    async def test_call_scope_isolated_between_handlers(self, application: Application):
        """핸들러 간 CALL 스코프 격리"""
        await application.ready()

        sessions = []

        @Service
        class IsolationService:
            @Handler
            async def handler_a(self):
                ctx = get_call_scope()
                session = DatabaseSession(DatabaseConnection("localhost", 5432))
                session.__enter__()
                ctx.set("session", session)
                ctx.register_closeable(session)
                sessions.append(("a", session, ctx.context_id))
                return "a"

            @Handler
            async def handler_b(self):
                ctx = get_call_scope()
                session = DatabaseSession(DatabaseConnection("localhost", 5432))
                session.__enter__()
                ctx.set("session", session)
                ctx.register_closeable(session)
                sessions.append(("b", session, ctx.context_id))
                return "b"

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=IsolationService)

        await service.handler_a()
        await service.handler_b()

        # 다른 세션, 다른 context_id
        assert sessions[0][1] is not sessions[1][1]
        assert sessions[0][2] != sessions[1][2]

    @pytest.mark.asyncio
    async def test_transactional_scope_isolated_between_calls(
        self, application: Application
    ):
        """별도 @Transactional 호출 간 격리"""
        await application.ready()

        context_ids = []

        @Service
        class IsolatedTransactionalService:
            @Transactional
            async def method_a(self):
                ctx = get_transactional_scope()
                context_ids.append(("a", ctx.context_id))
                return "a"

            @Transactional
            async def method_b(self):
                ctx = get_transactional_scope()
                context_ids.append(("b", ctx.context_id))
                return "b"

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=IsolatedTransactionalService)

        await service.method_a()
        await service.method_b()

        # 별도 호출은 다른 context
        assert context_ids[0][1] != context_ids[1][1]


class TestAsyncAutoCloseableIntegration:
    """AsyncAutoCloseable 통합 테스트"""

    def setup_method(self):
        AsyncDatabaseSession.reset_counters()

    @pytest.mark.asyncio
    async def test_async_closeable_auto_closes(self, application: Application):
        """AsyncAutoCloseable 자동 close 테스트"""
        await application.ready()

        session_ref = []

        @Service
        class AsyncSessionService:
            @Transactional
            async def use_async_session(self):
                ctx = get_transactional_scope()
                session = AsyncDatabaseSession(DatabaseConnection("localhost", 5432))
                await session.__aenter__()
                ctx.register_closeable(session)
                session_ref.append(session)

                result = await session.execute("SELECT 1")
                assert session.is_active
                return result

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=AsyncSessionService)
        result = await service.use_async_session()

        assert "SELECT 1" in result
        assert len(session_ref) == 1
        assert not session_ref[0].is_active  # 자동 aclose

    @pytest.mark.asyncio
    async def test_multiple_async_closeables_close_in_reverse_order(
        self, application: Application
    ):
        """여러 AsyncAutoCloseable이 역순으로 close"""
        await application.ready()

        close_order = []

        class TrackedSession(AsyncDatabaseSession):
            def __init__(self, id: int, connection):
                super().__init__(connection)
                self.tracked_id = id

            async def __aexit__(self, exc_type, exc_value, traceback):
                await super().__aexit__(exc_type, exc_value, traceback)
                close_order.append(self.tracked_id)

        @Service
        class MultiSessionService:
            @Transactional
            async def use_multiple_sessions(self):
                ctx = get_transactional_scope()
                conn = DatabaseConnection("localhost", 5432)

                for i in range(3):
                    session = TrackedSession(i, conn)
                    await session.__aenter__()
                    ctx.register_closeable(session)

                return "done"

        manager = application.container_manager
        await manager.initialize()

        service = manager.instance(type=MultiSessionService)
        await service.use_multiple_sessions()

        # 역순으로 close: 2, 1, 0
        assert close_order == [2, 1, 0]


class TestScopeWithFactoryContainer:
    """FactoryContainer와 Scope 통합 테스트"""

    @pytest.mark.asyncio
    async def test_factory_container_has_scope(self, application: Application):
        """FactoryContainer에 scope가 설정되어 있는지 확인"""
        await application.ready()
        manager = application.container_manager

        # ScopedFactoryConfig에서 Factory 정의 확인
        config = manager.configuration_for(DatabaseSession)

        if config:
            factory_def = config.get_factory_definition(DatabaseSession)
            assert factory_def is not None
            assert factory_def.scope == Scope.CALL

    @pytest.mark.asyncio
    async def test_singleton_factory_caches_correctly(self, application: Application):
        """SINGLETON Factory가 올바르게 캐시되는지 확인"""
        await application.ready()
        manager = application.container_manager

        # DatabaseConnection은 SINGLETON
        db1 = await manager.factory(DatabaseConnection)
        db2 = await manager.factory(DatabaseConnection)

        assert db1 is db2

        # 캐시 확인
        config = manager.configuration_for(DatabaseConnection)
        if config:
            factory_def = config.get_factory_definition(DatabaseConnection)
            cached = factory_def.get_cached_instance()
            assert cached is db1
