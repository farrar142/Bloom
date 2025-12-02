"""ContainerOrchestrator 테스트"""

import asyncio
import pytest
from bloom import Application
from bloom.core import (
    ContainerManager,
    ContainerOrchestrator,
    Component,
    Factory,
    PostConstruct,
    PreDestroy,
    ScopeEnum,
    Scope,
    CircularDependencyError,
    Lazy,
)


class TestOrchestratorBasics:
    """Orchestrator 기본 기능 테스트"""

    async def test_creation(self):
        """Orchestrator 생성"""
        manager = ContainerManager("test")
        orchestrator = ContainerOrchestrator(manager)
        assert orchestrator.manager is manager
        assert orchestrator.initialized_containers == []

    async def test_initialize_empty(self):
        """빈 상태에서 초기화"""
        manager = ContainerManager("test")
        orchestrator = ContainerOrchestrator(manager)

        containers = await orchestrator.initialize_async()
        assert containers == []

    async def test_initialize_single_component(self):
        """단일 컴포넌트 초기화"""

        @Component
        class Service:
            pass

        manager = ContainerManager("test")
        manager.scan(Service)
        orchestrator = ContainerOrchestrator(manager)

        containers = await orchestrator.initialize_async()
        assert len(containers) == 1

        instance = manager.get_instance(Service)
        assert instance is not None


class TestInitializationOrder:
    """초기화 순서 테스트"""

    async def test_dependency_order(self):
        """의존성 순서대로 초기화"""
        init_order = []

        @Component
        class Database:
            @PostConstruct
            def init(self):
                init_order.append("Database")

        @Component
        class Repository:
            db: Database

            @PostConstruct
            def init(self):
                init_order.append("Repository")

        @Component
        class Service:
            repo: Repository

            @PostConstruct
            def init(self):
                init_order.append("Service")

        app = (
            await Application("test").scan(Database, Repository, Service).ready_async()
        )

        # 의존성 순서: Database -> Repository -> Service
        assert init_order == ["Database", "Repository", "Service"]

    async def test_parallel_initialization(self):
        """병렬 초기화 - 같은 레벨은 동시 실행"""

        @Component
        class IndependentA:
            pass

        @Component
        class IndependentB:
            pass

        @Component
        class DependsOnBoth:
            a: IndependentA
            b: IndependentB

        app = await (
            Application("test")
            .scan(IndependentA, IndependentB, DependsOnBoth)
            .ready_async(parallel=True)
        )

        # 모든 인스턴스가 생성됨
        assert app.manager.get_instance(IndependentA) is not None
        assert app.manager.get_instance(IndependentB) is not None
        assert app.manager.get_instance(DependsOnBoth) is not None


class TestPostConstruct:
    """@PostConstruct 테스트"""

    async def test_sync_post_construct(self):
        """동기 @PostConstruct 호출"""

        @Component
        class Service:
            initialized = False

            @PostConstruct
            def init(self):
                self.initialized = True

        manager = ContainerManager("test")
        manager.scan(Service)
        orchestrator = ContainerOrchestrator(manager)

        await orchestrator.initialize_async()

        instance = manager.get_instance(Service)
        assert instance.initialized is True

    async def test_async_post_construct(self):
        """비동기 @PostConstruct 호출"""

        @Component
        class AsyncService:
            data = ""

            @PostConstruct
            async def init(self):
                await asyncio.sleep(0.01)
                self.data = "loaded"

        manager = ContainerManager("test")
        manager.scan(AsyncService)
        orchestrator = ContainerOrchestrator(manager)

        await orchestrator.initialize_async()

        instance = manager.get_instance(AsyncService)
        assert instance.data == "loaded"

    async def test_multiple_post_construct(self):
        """여러 @PostConstruct 메서드"""

        @Component
        class MultiInit:
            steps = []

            @PostConstruct
            def init_first(self):
                self.steps.append("first")

            @PostConstruct
            def init_second(self):
                self.steps.append("second")

        manager = ContainerManager("test")
        manager.scan(MultiInit)
        orchestrator = ContainerOrchestrator(manager)

        await orchestrator.initialize_async()

        instance = manager.get_instance(MultiInit)
        assert len(instance.steps) == 2
        assert "first" in instance.steps
        assert "second" in instance.steps


class TestPreDestroy:
    """@PreDestroy 테스트"""

    async def test_finalize_calls_pre_destroy(self):
        """finalize_async가 @PreDestroy 호출"""
        destroyed = []

        @Component
        class Service:
            @PreDestroy
            def cleanup(self):
                destroyed.append("cleaned")

        manager = ContainerManager("test")
        manager.scan(Service)
        orchestrator = ContainerOrchestrator(manager)

        containers = await orchestrator.initialize_async()
        await orchestrator.finalize_async(containers)

        assert "cleaned" in destroyed

    async def test_finalize_reverse_order(self):
        """@PreDestroy는 초기화 역순으로 호출"""
        destroy_order = []

        @Component
        class First:
            @PreDestroy
            def cleanup(self):
                destroy_order.append("First")

        @Component
        class Second:
            first: First

            @PreDestroy
            def cleanup(self):
                destroy_order.append("Second")

        @Component
        class Third:
            second: Second

            @PreDestroy
            def cleanup(self):
                destroy_order.append("Third")

        app = await Application("test").scan(First, Second, Third).ready_async()
        await app.shutdown_async()

        # 초기화 순서: First -> Second -> Third
        # 소멸 순서: Third -> Second -> First
        assert destroy_order == ["Third", "Second", "First"]


class TestLazyScope:
    """Lazy 스코프 테스트 (CALL/REQUEST는 즉시 초기화 안 함)"""

    async def test_call_scope_not_initialized_immediately(self):
        """CALL 스코프는 즉시 초기화되지 않음"""
        init_count = 0

        @Component
        @Scope(ScopeEnum.CALL)
        class CallService:
            def __init__(self):
                nonlocal init_count
                init_count += 1

        manager = ContainerManager("test")
        manager.scan(CallService)
        orchestrator = ContainerOrchestrator(manager)

        await orchestrator.initialize_async()

        # CALL 스코프는 즉시 초기화되지 않음
        assert init_count == 0

    async def test_singleton_initialized_immediately(self):
        """SINGLETON 스코프는 즉시 초기화"""
        init_count = 0

        @Component
        class SingletonService:
            def __init__(self):
                nonlocal init_count
                init_count += 1

        manager = ContainerManager("test")
        manager.scan(SingletonService)
        orchestrator = ContainerOrchestrator(manager)

        await orchestrator.initialize_async()

        assert init_count == 1


class TestFactoryChain:
    """Factory Chain 테스트"""

    async def test_factory_creates_instance(self):
        """Factory가 인스턴스 생성"""

        class Config:
            def __init__(self, value: str):
                self.value = value

        @Component
        class ConfigFactory:
            @Factory
            def create(self) -> Config:
                return Config("created_by_factory")

        app = await Application("test").scan(ConfigFactory).ready_async()

        config = app.manager.get_instance(Config)
        assert config.value == "created_by_factory"

    async def test_factory_with_dependency(self):
        """Factory가 의존성 주입받아서 생성"""

        class Database:
            def __init__(self, url: str):
                self.url = url

        @Component
        class DbUrl:
            url: str = "postgres://localhost"

        @Component
        class DbFactory:
            db_url: DbUrl

            @Factory
            def create(self) -> Database:
                return Database(self.db_url.url)

        app = await Application("test").scan(DbUrl, DbFactory).ready_async()

        db = app.manager.get_instance(Database)
        assert db.url == "postgres://localhost"


class TestCircularDependency:
    """순환 의존성 테스트"""

    async def test_circular_dependency_with_lazy(self):
        """Lazy로 순환 의존성 해결"""

        @Component
        class ServiceA:
            b: Lazy["ServiceB"]

        @Component
        class ServiceB:
            a: ServiceA

        # Lazy로 순환 참조 해결
        app = await Application("test").scan(ServiceA, ServiceB).ready_async()

        a = app.manager.get_instance(ServiceA)
        b = app.manager.get_instance(ServiceB)

        assert a is not None
        assert b is not None
        assert b.a is a


class TestParallelVsSequential:
    """병렬 vs 순차 초기화 비교"""

    async def test_both_produce_same_result(self):
        """병렬/순차 초기화 모두 같은 결과"""

        @Component
        class A:
            pass

        @Component
        class B:
            a: A

        @Component
        class C:
            b: B

        # 순차 초기화
        app1 = await Application("test1").scan(A, B, C).ready_async(parallel=False)

        # 병렬 초기화
        app2 = await Application("test2").scan(A, B, C).ready_async(parallel=True)

        # 둘 다 모든 인스턴스 생성됨
        assert app1.manager.get_instance(C) is not None
        assert app2.manager.get_instance(C) is not None
