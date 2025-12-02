"""라이프사이클 훅 테스트"""

import pytest
from bloom import Application, Component, PostConstruct, PreDestroy


class TestLifecycleHooks:
    """@PostConstruct, @PreDestroy 라이프사이클 훅 테스트"""

    async def test_post_construct_called_on_ready(self, reset_container_manager):
        """@PostConstruct 메서드가 ready() 시 호출됨"""
        call_log = []

        @Component
        class Service:
            @PostConstruct
            def init(self):
                call_log.append("init")

        app = await Application("test").ready_async()

        assert "init" in call_log
        assert len(call_log) == 1

    async def test_pre_destroy_called_on_shutdown(self, reset_container_manager):
        """@PreDestroy 메서드가 shutdown() 시 호출됨"""
        call_log = []

        @Component
        class Service:
            @PreDestroy
            def cleanup(self):
                call_log.append("cleanup")

        app = await Application("test").ready_async()
        assert "cleanup" not in call_log

        await app.shutdown_async()
        assert "cleanup" in call_log

    async def test_multiple_post_construct_methods(self, reset_container_manager):
        """여러 @PostConstruct 메서드가 모두 호출됨"""
        call_log = []

        @Component
        class Service:
            @PostConstruct
            def init1(self):
                call_log.append("init1")

            @PostConstruct
            def init2(self):
                call_log.append("init2")

        app = await Application("test").ready_async()

        assert "init1" in call_log
        assert "init2" in call_log
        assert len(call_log) == 2

    async def test_multiple_pre_destroy_methods(self, reset_container_manager):
        """여러 @PreDestroy 메서드가 모두 호출됨"""
        call_log = []

        @Component
        class Service:
            @PreDestroy
            def cleanup1(self):
                call_log.append("cleanup1")

            @PreDestroy
            def cleanup2(self):
                call_log.append("cleanup2")

        app = await Application("test").ready_async()
        await app.shutdown_async()

        assert "cleanup1" in call_log
        assert "cleanup2" in call_log
        assert len(call_log) == 2

    async def test_post_construct_has_access_to_dependencies(
        self, reset_container_manager
    ):
        """@PostConstruct에서 주입된 의존성에 접근 가능"""
        call_log = []

        @Component
        class Repository:
            def get_data(self):
                return "data"

        @Component
        class Service:
            repository: Repository

            @PostConstruct
            def init(self):
                # 의존성이 이미 주입되어 있어야 함
                call_log.append(self.repository.get_data())

        app = await Application("test").ready_async()

        assert "data" in call_log

    async def test_pre_destroy_called_in_reverse_order(self, reset_container_manager):
        """@PreDestroy가 초기화 역순으로 호출됨"""
        call_log = []

        @Component
        class Repository:
            @PreDestroy
            def cleanup(self):
                call_log.append("repository")

        @Component
        class Service:
            repository: Repository  # Repository에 의존

            @PreDestroy
            def cleanup(self):
                call_log.append("service")

        app = await Application("test").ready_async()
        await app.shutdown_async()

        # Service가 나중에 초기화되므로 먼저 정리됨
        assert call_log.index("service") < call_log.index("repository")

    async def test_post_construct_and_pre_destroy_together(
        self, reset_container_manager
    ):
        """@PostConstruct와 @PreDestroy를 함께 사용"""
        call_log = []

        @Component
        class DatabaseConnection:
            @PostConstruct
            def connect(self):
                call_log.append("connected")

            @PreDestroy
            def disconnect(self):
                call_log.append("disconnected")

        app = await Application("test").ready_async()
        assert call_log == ["connected"]

        await app.shutdown_async()
        assert call_log == ["connected", "disconnected"]

    async def test_shutdown_without_ready_does_nothing(self, reset_container_manager):
        """ready() 없이 shutdown() 호출하면 아무 일도 안 함"""
        call_log = []

        @Component
        class Service:
            @PreDestroy
            def cleanup(self):
                call_log.append("cleanup")

        app = Application("test")
        await app.shutdown_async()  # ready() 호출 안 함

        assert call_log == []

    async def test_lifecycle_with_factory(self, reset_container_manager):
        """Factory로 생성된 컴포넌트의 라이프사이클"""
        call_log = []

        class ExternalClient:
            def connect(self):
                call_log.append("client_connected")

            def disconnect(self):
                call_log.append("client_disconnected")

        from bloom import Factory

        @Component
        class Config:
            @Factory
            def create_client(self) -> ExternalClient:
                client = ExternalClient()
                client.connect()
                return client

            @PostConstruct
            def init(self):
                call_log.append("config_init")

        app = await Application("test").ready_async()

        # Config의 PostConstruct가 호출됨
        assert "config_init" in call_log
        # Factory로 생성된 ExternalClient도 connect 호출됨
        assert "client_connected" in call_log

    async def test_post_construct_container_attribute(self, reset_container_manager):
        """@PostConstruct 메서드에 __container__ 속성이 있음"""

        @Component
        class Service:
            @PostConstruct
            def init(self):
                pass

        # __container__ 속성 확인
        assert hasattr(Service.init, "__container__")
        container = Service.init.__container__
        # LifecycleHandlerContainer인지 확인
        from bloom.core.lifecycle import LifecycleHandlerContainer, LifecycleType

        assert isinstance(container, LifecycleHandlerContainer)
        assert container.lifecycle_type == LifecycleType.POST_CONSTRUCT

    async def test_pre_destroy_container_attribute(self, reset_container_manager):
        """@PreDestroy 메서드에 __container__ 속성이 있음"""

        @Component
        class Service:
            @PreDestroy
            def cleanup(self):
                pass

        # __container__ 속성 확인
        assert hasattr(Service.cleanup, "__container__")
        container = Service.cleanup.__container__
        # LifecycleHandlerContainer인지 확인
        from bloom.core.lifecycle import LifecycleHandlerContainer, LifecycleType

        assert isinstance(container, LifecycleHandlerContainer)
        assert container.lifecycle_type == LifecycleType.PRE_DESTROY


class TestPrototypePostConstruct:
    """PROTOTYPE 스코프에서 PostConstruct 호출 테스트 (Spring과 동일하게 PreDestroy는 미호출)"""

    async def test_prototype_post_construct_on_access(self, reset_container_manager):
        """PROTOTYPE 인스턴스 생성 시 @PostConstruct가 호출됨"""
        from bloom import Scope
        from bloom.core import ScopeEnum

        call_log = []

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeService:
            @PostConstruct
            def init(self):
                call_log.append(f"init:{id(self)}")

            def get_id(self):
                return id(self)

        @Component
        class Consumer:
            service: PrototypeService

        app = await Application("test").ready_async()
        consumer = app.manager.get_instance(Consumer)

        # ready() 시점에는 PROTOTYPE 인스턴스가 생성되지 않음
        assert len(call_log) == 0, "PROTOTYPE should not be initialized on ready()"

        # 첫 번째 접근: 새 인스턴스 생성 + PostConstruct 호출
        service1_id = consumer.service.get_id()
        assert len(call_log) == 1, f"PostConstruct should be called, logs: {call_log}"
        assert f"init:{service1_id}" in call_log

        # 두 번째 접근: 또 다른 새 인스턴스 + PostConstruct 호출
        service2_id = consumer.service.get_id()
        assert (
            len(call_log) == 2
        ), f"PostConstruct should be called again, logs: {call_log}"
        assert f"init:{service2_id}" in call_log
        assert service1_id != service2_id

    async def test_prototype_pre_destroy_not_called(self, reset_container_manager):
        """PROTOTYPE 인스턴스는 PreDestroy가 호출되지 않음 (Spring과 동일)"""
        import gc
        from bloom import Scope
        from bloom.core import ScopeEnum

        call_log = []

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeService:
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
            service: PrototypeService

        app = await Application("test").ready_async()
        consumer = app.manager.get_instance(Consumer)

        # 인스턴스 생성
        service1_id = consumer.service.get_id()
        service2_id = consumer.service.get_id()

        assert (
            service1_id != service2_id
        ), "PROTOTYPE should create new instances each access"

        # PostConstruct가 호출되었는지 확인
        init_count = sum(1 for log in call_log if log.startswith("init:"))
        assert (
            init_count == 2
        ), f"PostConstruct should be called twice, logs: {call_log}"

        # GC 강제 실행
        gc.collect()
        gc.collect()
        gc.collect()

        # PreDestroy는 호출되지 않아야 함 (Spring과 동일하게 컨테이너가 관리하지 않음)
        cleanup_count = sum(1 for log in call_log if log.startswith("cleanup:"))
        assert (
            cleanup_count == 0
        ), f"PreDestroy should NOT be called for PROTOTYPE, logs: {call_log}"

    async def test_prototype_no_memory_leak(self, reset_container_manager):
        """PROTOTYPE 인스턴스가 참조 제거 후 GC됨 (메모리 누수 없음)"""
        import gc
        import weakref
        from bloom import Scope
        from bloom.core import ScopeEnum

        instance_refs = []

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeService:
            def register_self(self):
                # weak reference 등록
                instance_refs.append(weakref.ref(self))
                return self

        @Component
        class Consumer:
            service: PrototypeService

        app = await Application("test").ready_async()
        consumer = app.manager.get_instance(Consumer)

        # 인스턴스 생성 및 weak ref 등록
        consumer.service.register_self()
        consumer.service.register_self()  # 또 다른 인스턴스

        assert len(instance_refs) == 2, f"Should have 2 refs, got {len(instance_refs)}"

        # GC 실행
        gc.collect()
        gc.collect()
        gc.collect()

        # 모든 weak reference가 None이면 객체가 GC됨
        gc_count = sum(1 for ref in instance_refs if ref() is None)
        assert (
            gc_count >= 1
        ), f"At least one PROTOTYPE instance should be garbage collected, refs: {[ref() for ref in instance_refs]}"

    async def test_singleton_not_affected_by_prototype(self, reset_container_manager):
        """SINGLETON은 PROTOTYPE과 독립적으로 동작"""
        from bloom import Scope
        from bloom.core import ScopeEnum

        call_log = []

        @Component
        class SingletonService:
            @PreDestroy
            def cleanup(self):
                call_log.append("singleton_cleanup")

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeService:
            @PreDestroy
            def cleanup(self):
                call_log.append("prototype_cleanup")

        @Component
        class Consumer:
            singleton: SingletonService
            prototype: PrototypeService

        app = await Application("test").ready_async()
        consumer = app.manager.get_instance(Consumer)

        # 두 서비스 접근
        _ = consumer.singleton
        _ = consumer.prototype

        # SINGLETON cleanup은 shutdown 전까지 호출되면 안 됨
        assert (
            "singleton_cleanup" not in call_log
        ), "SINGLETON PreDestroy should not be called until shutdown"

        # shutdown 시에만 SINGLETON cleanup 호출
        await app.shutdown_async()
        assert "singleton_cleanup" in call_log
        # PROTOTYPE cleanup은 호출되지 않음
        assert "prototype_cleanup" not in call_log


class TestAsyncLifecycleInSyncContext:
    """동기 컨텍스트에서 비동기 라이프사이클 테스트"""

    async def test_async_post_construct_with_run_async_init(
        self, reset_container_manager
    ):
        """run_async_init=True 시 비동기 @PostConstruct가 실행됨"""
        call_log = []

        @Component
        class AsyncService:
            @PostConstruct
            async def init(self):
                call_log.append("async_init")

        @Component
        class SyncService:
            @PostConstruct
            def init(self):
                call_log.append("sync_init")

        app = Application("test")
        app.scan(AsyncService, SyncService)
        await app.ready_async()

        assert "sync_init" in call_log
        assert "async_init" in call_log
        assert len(call_log) == 2

    @pytest.mark.skip(
        reason="run_async_init 파라미터 제거됨 - ready()는 항상 비동기 초기화 수행"
    )
    async def test_async_post_construct_without_run_async_init(
        self, reset_container_manager
    ):
        """run_async_init=False 시 비동기 @PostConstruct는 지연됨"""
        call_log = []

        @Component
        class AsyncService:
            @PostConstruct
            async def init(self):
                call_log.append("async_init")

        @Component
        class SyncService:
            @PostConstruct
            def init(self):
                call_log.append("sync_init")

        app = Application("test")
        app.scan(AsyncService, SyncService)
        await app.ready_async()  # 명시적으로 False

        # 동기만 실행됨
        assert "sync_init" in call_log
        assert "async_init" not in call_log
        assert len(call_log) == 1

    async def test_async_post_construct_order_preserved(self, reset_container_manager):
        """비동기 @PostConstruct 실행 순서가 보존됨"""
        call_log = []

        @Component
        class First:
            @PostConstruct
            async def init(self):
                call_log.append("first")

        @Component
        class Second:
            first: First

            @PostConstruct
            async def init(self):
                call_log.append("second")

        @Component
        class Third:
            second: Second

            @PostConstruct
            async def init(self):
                call_log.append("third")

        app = Application("test")
        app.scan(First, Second, Third)
        await app.ready_async()

        # 의존성 순서대로 실행
        assert call_log == ["first", "second", "third"]

    async def test_mixed_sync_async_post_construct_order(self, reset_container_manager):
        """동기/비동기 @PostConstruct 혼합 시 올바른 순서로 실행"""
        call_log = []

        @Component
        class SyncFirst:
            @PostConstruct
            def init(self):
                call_log.append("sync_first")

        @Component
        class AsyncSecond:
            first: SyncFirst

            @PostConstruct
            async def init(self):
                call_log.append("async_second")

        @Component
        class SyncThird:
            second: AsyncSecond

            @PostConstruct
            def init(self):
                call_log.append("sync_third")

        app = Application("test")
        app.scan(SyncFirst, AsyncSecond, SyncThird)
        await app.ready_async()

        # 동기가 먼저 실행되고, 비동기가 나중에 실행됨
        # (동기: ready() 시점, 비동기: start_async() 시점)
        assert "sync_first" in call_log
        assert "sync_third" in call_log
        assert "async_second" in call_log

    async def test_async_post_construct_actually_awaits(self, reset_container_manager):
        """비동기 @PostConstruct가 실제로 await됨 (asyncio.sleep 포함)"""
        import asyncio

        result = {"value": None, "counter": 0}

        @Component
        class AsyncService:
            @PostConstruct
            async def init(self):
                # 실제 비동기 작업 시뮬레이션
                await asyncio.sleep(0.01)
                result["counter"] += 1
                result["value"] = "completed"

        app = Application("test")
        app.scan(AsyncService)
        await app.ready_async()

        # await가 완료되어야 값이 설정됨
        assert result["value"] == "completed"
        assert result["counter"] == 1

    async def test_multiple_async_post_construct_all_await(
        self, reset_container_manager
    ):
        """여러 비동기 @PostConstruct가 모두 await됨"""
        import asyncio

        results = []

        @Component
        class ServiceA:
            @PostConstruct
            async def init(self):
                await asyncio.sleep(0.01)
                results.append("A")

        @Component
        class ServiceB:
            a: ServiceA

            @PostConstruct
            async def init(self):
                await asyncio.sleep(0.01)
                results.append("B")

        @Component
        class ServiceC:
            b: ServiceB

            @PostConstruct
            async def init(self):
                await asyncio.sleep(0.01)
                results.append("C")

        app = Application("test")
        app.scan(ServiceA, ServiceB, ServiceC)
        await app.ready_async()

        # 모든 비동기 초기화가 완료됨
        assert results == ["A", "B", "C"]

    async def test_async_post_construct_with_async_dependency_setup(
        self, reset_container_manager
    ):
        """비동기 @PostConstruct에서 설정한 값을 다른 컴포넌트가 사용"""
        import asyncio

        @Component
        class DatabasePool:
            connection_string: str | None = None

            @PostConstruct
            async def connect(self):
                # 비동기 연결 시뮬레이션
                await asyncio.sleep(0.01)
                self.connection_string = "postgresql://localhost/test"

        @Component
        class Repository:
            pool: DatabasePool

            def get_connection_info(self) -> str | None:
                return self.pool.connection_string

        app = Application("test")
        app.scan(DatabasePool, Repository)
        await app.ready_async()

        repo = app.manager.get_instance(Repository)
        # 비동기 초기화가 완료되어야 connection_string이 설정됨
        assert repo.get_connection_info() == "postgresql://localhost/test"
