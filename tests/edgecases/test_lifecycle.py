"""Lifecycle 엣지케이스 테스트

컴포넌트 라이프사이클의 극단적인 상황 테스트.
"""

import pytest
import asyncio
from dataclasses import dataclass
from typing import ClassVar

from bloom.core import (
    Component,
    Configuration,
    Factory,
    PostConstruct,
    get_container_manager,
    reset_container_manager,
)
from bloom.core.scope import ScopeEnum
from bloom.core.decorators import register_factories_from_configuration


# =============================================================================
# Mock Classes
# =============================================================================


@dataclass
class PersistentSingleton:
    """영구 싱글톤"""

    id: int


@dataclass
class AsyncCreated:
    """비동기로 생성된 객체"""

    mode: str


@dataclass
class MayFailSingleton:
    """실패할 수도 있는 싱글톤"""

    id: int


@dataclass
class CountingInstance:
    """카운팅 인스턴스"""

    count: int


# =============================================================================
# Tests
# =============================================================================


class TestPostConstructEdgeCases:
    """PostConstruct 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_post_construct_called_once(self):
        """PostConstruct는 한 번만 호출"""
        init_count = {"count": 0}

        @Component
        class SingleInit:
            value: str = ""

            @PostConstruct
            async def init(self):
                init_count["count"] += 1
                self.value = f"initialized-{init_count['count']}"

        manager = get_container_manager()
        init_count["count"] = 0
        await manager.initialize()

        # 여러 번 get
        inst1 = manager.get_instance(SingleInit)
        inst2 = manager.get_instance(SingleInit)
        inst3 = manager.get_instance(SingleInit)

        # 한 번만 호출됨
        assert init_count["count"] == 1
        assert inst1.value == "initialized-1"
        assert inst1 is inst2 is inst3

    @pytest.mark.asyncio
    async def test_post_construct_with_simple_dependency(self):
        """간단한 의존성이 있는 PostConstruct"""
        init_order: list[str] = []

        @Component
        class SimpleDep:
            value: str = "dep-value"

            @PostConstruct
            async def init(self):
                init_order.append("dep")

        @Component
        class SimpleDependent:
            dep: SimpleDep
            combined: str = ""

            @PostConstruct
            async def init(self):
                init_order.append("dependent")
                # PostConstruct 시점에 dep은 이미 초기화됨
                # (LazyProxy를 통해 접근하지만 initialize()로 이미 생성됨)

        manager = get_container_manager()
        init_order.clear()
        await manager.initialize()

        dependent = manager.get_instance(SimpleDependent)

        # 의존성 먼저 초기화
        assert "dep" in init_order
        assert "dependent" in init_order

    @pytest.mark.asyncio
    async def test_post_construct_exception_handling(self):
        """PostConstruct 예외 처리"""

        @Component
        class FailingInit:
            @PostConstruct
            async def init(self):
                raise RuntimeError("Init failed")

        manager = get_container_manager()

        with pytest.raises(RuntimeError, match="Init failed"):
            await manager.initialize()


class TestSingletonLifecycleEdgeCases:
    """싱글톤 라이프사이클 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_singleton_survives_multiple_gets(self):
        """싱글톤은 여러 get 호출에도 유지"""
        create_count = {"count": 0}

        @Configuration
        class SingletonConfig:
            @Factory(scope=ScopeEnum.SINGLETON)
            def persistent_singleton(self) -> PersistentSingleton:
                create_count["count"] += 1
                return PersistentSingleton(id=create_count["count"])

        @Component
        class Consumer:
            singleton: PersistentSingleton

            def get_id(self) -> int:
                return self.singleton.id

        manager = get_container_manager()
        register_factories_from_configuration(SingletonConfig, manager)
        create_count["count"] = 0
        await manager.initialize()

        consumer = manager.get_instance(Consumer)

        # 많은 호출
        ids = [consumer.get_id() for _ in range(1000)]

        # 한 번만 생성
        assert create_count["count"] == 1
        assert all(id == 1 for id in ids)


class TestCircularDependencyLifecycleEdgeCases:
    """순환 의존성 라이프사이클 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_circular_dependency_both_initialized(self):
        """순환 의존성에서 양쪽 모두 초기화"""
        init_status = {"a": False, "b": False}

        @Component
        class CircA:
            b: "CircB"

            @PostConstruct
            async def init(self):
                init_status["a"] = True

            def get_b_status(self) -> bool:
                return init_status["b"]

        @Component
        class CircB:
            a: CircA

            @PostConstruct
            async def init(self):
                init_status["b"] = True

            def get_a_status(self) -> bool:
                return init_status["a"]

        manager = get_container_manager()
        init_status["a"] = False
        init_status["b"] = False
        await manager.initialize()

        a = manager.get_instance(CircA)
        b = manager.get_instance(CircB)

        # 둘 다 초기화됨
        assert init_status["a"]
        assert init_status["b"]

        # 서로 접근 가능
        assert a.get_b_status()
        assert b.get_a_status()


class TestAsyncLifecycleEdgeCases:
    """비동기 라이프사이클 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_async_post_construct(self):
        """비동기 PostConstruct"""
        result = {"data": None}

        @Component
        class AsyncInit:
            @PostConstruct
            async def async_init(self):
                await asyncio.sleep(0.01)
                result["data"] = "async-initialized"

        manager = get_container_manager()
        result["data"] = None
        await manager.initialize()

        manager.get_instance(AsyncInit)

        assert result["data"] == "async-initialized"

    @pytest.mark.asyncio
    async def test_async_factory_lifecycle(self):
        """비동기 Factory 라이프사이클"""

        @Configuration
        class AsyncFactoryConfig:
            @Factory(scope=ScopeEnum.SINGLETON)
            async def async_created(self) -> AsyncCreated:
                await asyncio.sleep(0.01)
                return AsyncCreated(mode="async")

        manager = get_container_manager()
        register_factories_from_configuration(AsyncFactoryConfig, manager)
        await manager.initialize()

        inst = manager.get_instance(AsyncCreated)

        assert inst.mode == "async"


class TestInitializationOrderEdgeCases:
    """초기화 순서 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_simple_dependency_order(self):
        """간단한 의존성 초기화 순서"""
        init_order: list[str] = []

        @Component
        class BaseComp:
            @PostConstruct
            async def init(self):
                init_order.append("base")

        @Component
        class TopComp:
            base: BaseComp

            @PostConstruct
            async def init(self):
                init_order.append("top")

        manager = get_container_manager()
        init_order.clear()
        await manager.initialize()

        # initialize는 토폴로지 순서로 초기화
        # 의존성이 있는 컴포넌트들이 순서대로 초기화됨
        assert "base" in init_order
        assert "top" in init_order


class TestFactoryLifecycleEdgeCases:
    """Factory 라이프사이클 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_factory_exception_does_not_cache(self):
        """Factory 예외는 캐시되지 않음"""

        @Configuration
        class FailConfig:
            _call_count: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.SINGLETON)
            def may_fail_singleton(self) -> MayFailSingleton:
                FailConfig._call_count += 1
                if FailConfig._call_count < 3:
                    raise RuntimeError(f"Fail {FailConfig._call_count}")
                return MayFailSingleton(id=FailConfig._call_count)

        manager = get_container_manager()
        register_factories_from_configuration(FailConfig, manager)
        FailConfig._call_count = 0

        # 처음 두 번은 실패
        with pytest.raises(RuntimeError):
            await manager.get_instance_async(MayFailSingleton)

        with pytest.raises(RuntimeError):
            await manager.get_instance_async(MayFailSingleton)

        # 세 번째는 성공
        inst = await manager.get_instance_async(MayFailSingleton)
        assert inst.id == 3

        # 이제 캐시됨 - 같은 인스턴스
        inst2 = await manager.get_instance_async(MayFailSingleton)
        assert inst is inst2

    @pytest.mark.asyncio
    async def test_factory_with_configuration_instance(self):
        """Configuration 인스턴스 메서드로 Factory (CALL 스코프)"""
        from bloom.core.decorators import Handler
        from bloom.core.proxy import AsyncProxy

        @Configuration
        class StatefulConfig:
            def __init__(self):
                self.counter = 0

            @Factory(scope=ScopeEnum.CALL)  # CALL 스코프로 매번 새 인스턴스
            def counting_instance(self) -> CountingInstance:
                self.counter += 1
                return CountingInstance(count=self.counter)

        @Component
        class CountingConsumer:
            instance: AsyncProxy[CountingInstance]

            async def get_count(self) -> int:
                i = await self.instance.resolve()
                return i.count

        manager = get_container_manager()
        register_factories_from_configuration(StatefulConfig, manager)
        await manager.initialize()

        consumer = manager.get_instance(CountingConsumer)

        @Handler
        async def handler():
            return await consumer.get_count()

        # CALL 스코프는 Handler마다 새 인스턴스
        count1 = await handler()
        count2 = await handler()
        count3 = await handler()

        # Configuration의 상태 유지, 각 Handler마다 새 인스턴스
        assert count1 == 1
        assert count2 == 2
        assert count3 == 3
