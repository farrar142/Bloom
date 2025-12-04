"""CALL 스코프 엣지케이스 테스트

Handler와 CALL 스코프의 극단적인 상황 테스트.
"""

import pytest
import asyncio
from dataclasses import dataclass
from typing import ClassVar

from bloom.core import (
    Component,
    Configuration,
    Factory,
    get_container_manager,
    reset_container_manager,
)
from bloom.core.scope import ScopeEnum
from bloom.core.proxy import AsyncProxy
from bloom.core.decorators import register_factories_from_configuration, Handler


# =============================================================================
# Mock Classes
# =============================================================================


@dataclass
class CallScopedInstance:
    """CALL 스코프 인스턴스"""
    id: int


@dataclass
class StatefulInstance:
    """상태가 있는 인스턴스"""
    id: int
    state: str = ""


# =============================================================================
# Tests: CALL 스코프 중첩
# =============================================================================


class TestCallScopeNestingEdgeCases:
    """CALL 스코프 중첩 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_nested_handlers_separate_scopes(self):
        """중첩 Handler는 각자 스코프"""

        @Configuration
        class NestedConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def nested_instance(self) -> CallScopedInstance:
                NestedConfig._id += 1
                return CallScopedInstance(id=NestedConfig._id)

        @Component
        class NestedConsumer:
            instance: AsyncProxy[CallScopedInstance]

            async def get_id(self) -> int:
                i = await self.instance.resolve()
                return i.id

        manager = get_container_manager()
        register_factories_from_configuration(NestedConfig, manager)
        NestedConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(NestedConsumer)

        @Handler
        async def inner_handler():
            return await consumer.get_id()

        @Handler
        async def outer_handler():
            outer_id = await consumer.get_id()
            inner_id = await inner_handler()
            outer_id_again = await consumer.get_id()
            return outer_id, inner_id, outer_id_again

        outer_id, inner_id, outer_id_again = await outer_handler()

        # outer는 같은 인스턴스, inner는 다른 인스턴스
        assert outer_id == 1
        assert inner_id == 2
        assert outer_id_again == 1

    @pytest.mark.asyncio
    async def test_deeply_nested_handlers(self):
        """깊게 중첩된 Handler"""

        @Configuration
        class DeepConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def deep_instance(self) -> CallScopedInstance:
                DeepConfig._id += 1
                return CallScopedInstance(id=DeepConfig._id)

        @Component
        class DeepConsumer:
            instance: AsyncProxy[CallScopedInstance]

            async def get_id(self) -> int:
                i = await self.instance.resolve()
                return i.id

        manager = get_container_manager()
        register_factories_from_configuration(DeepConfig, manager)
        DeepConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(DeepConsumer)

        @Handler
        async def level3():
            return await consumer.get_id()

        @Handler
        async def level2():
            return await consumer.get_id(), await level3()

        @Handler
        async def level1():
            return await consumer.get_id(), await level2()

        l1_id, (l2_id, l3_id) = await level1()

        # 각 레벨 다른 ID
        assert l1_id == 1
        assert l2_id == 2
        assert l3_id == 3


# =============================================================================
# Tests: CALL 스코프 동시성
# =============================================================================


class TestCallScopeConcurrencyEdgeCases:
    """CALL 스코프 동시성 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_massive_concurrent_handlers(self):
        """대량 동시 Handler"""

        @Configuration
        class MassiveConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def massive_instance(self) -> CallScopedInstance:
                async with MassiveConfig._lock:
                    MassiveConfig._id += 1
                    return CallScopedInstance(id=MassiveConfig._id)

        @Component
        class MassiveConsumer:
            instance: AsyncProxy[CallScopedInstance]

            async def get_id(self) -> int:
                i = await self.instance.resolve()
                return i.id

        manager = get_container_manager()
        register_factories_from_configuration(MassiveConfig, manager)
        MassiveConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(MassiveConsumer)

        @Handler
        async def handler():
            return await consumer.get_id()

        # 200개 동시 Handler
        results = await asyncio.gather(*[handler() for _ in range(200)])

        # 모두 다른 ID
        assert len(set(results)) == 200


# =============================================================================
# Tests: CALL 스코프 예외 처리
# =============================================================================


class TestCallScopeExceptionEdgeCases:
    """CALL 스코프 예외 처리 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_exception_in_factory_first_resolve(self):
        """Factory에서 예외 - 첫 resolve"""

        @Configuration
        class ExcFactoryConfig:
            @Factory(scope=ScopeEnum.CALL)
            async def exc_factory_instance(self) -> CallScopedInstance:
                raise ValueError("Factory error")

        @Component
        class ExcFactoryConsumer:
            instance: AsyncProxy[CallScopedInstance]

            async def get_id(self) -> int:
                i = await self.instance.resolve()
                return i.id

        manager = get_container_manager()
        register_factories_from_configuration(ExcFactoryConfig, manager)
        await manager.initialize()

        consumer = manager.get_instance(ExcFactoryConsumer)

        @Handler
        async def handler():
            return await consumer.get_id()

        with pytest.raises(ValueError, match="Factory error"):
            await handler()

    @pytest.mark.asyncio
    async def test_exception_after_resolve(self):
        """resolve 후 예외"""

        @Configuration
        class AfterResolveConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def after_resolve_instance(self) -> CallScopedInstance:
                AfterResolveConfig._id += 1
                return CallScopedInstance(id=AfterResolveConfig._id)

        @Component
        class AfterResolveConsumer:
            instance: AsyncProxy[CallScopedInstance]

            async def get_id_and_fail(self) -> int:
                i = await self.instance.resolve()
                raise RuntimeError(f"Error after resolve: {i.id}")

        manager = get_container_manager()
        register_factories_from_configuration(AfterResolveConfig, manager)
        AfterResolveConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(AfterResolveConsumer)

        @Handler
        async def handler():
            return await consumer.get_id_and_fail()

        with pytest.raises(RuntimeError, match="Error after resolve: 1"):
            await handler()


# =============================================================================
# Tests: CALL 스코프 상태 격리
# =============================================================================


class TestCallScopeStateIsolation:
    """CALL 스코프 상태 격리 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_state_not_shared_between_handlers(self):
        """Handler 간 상태 공유 없음"""

        @Configuration
        class StateConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def state_instance(self) -> StatefulInstance:
                StateConfig._id += 1
                return StatefulInstance(id=StateConfig._id)

        @Component
        class StateConsumer:
            instance: AsyncProxy[StatefulInstance]

            async def set_state(self, state: str):
                i = await self.instance.resolve()
                i.state = state

            async def get_state(self) -> str:
                i = await self.instance.resolve()
                return i.state

        manager = get_container_manager()
        register_factories_from_configuration(StateConfig, manager)
        StateConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(StateConsumer)

        @Handler
        async def handler1():
            await consumer.set_state("handler1_state")
            return await consumer.get_state()

        @Handler
        async def handler2():
            return await consumer.get_state()

        state1 = await handler1()
        state2 = await handler2()

        # handler1의 상태가 handler2에 영향 없음
        assert state1 == "handler1_state"
        assert state2 == ""  # 새 인스턴스이므로 빈 상태


# =============================================================================
# Tests: CALL 스코프 타이밍
# =============================================================================


class TestCallScopeTimingEdgeCases:
    """CALL 스코프 타이밍 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_slow_factory_does_not_block_other_handlers(self):
        """느린 Factory가 다른 Handler 차단 안 함"""

        @Configuration
        class SlowConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def slow_instance(self) -> CallScopedInstance:
                async with SlowConfig._lock:
                    SlowConfig._id += 1
                    id = SlowConfig._id
                await asyncio.sleep(0.01)  # 느린 생성
                return CallScopedInstance(id=id)

        @Component
        class SlowConsumer:
            instance: AsyncProxy[CallScopedInstance]

            async def get_id(self) -> int:
                i = await self.instance.resolve()
                return i.id

        manager = get_container_manager()
        register_factories_from_configuration(SlowConfig, manager)
        SlowConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(SlowConsumer)

        @Handler
        async def handler():
            return await consumer.get_id()

        import time
        start = time.time()

        # 10개 동시 실행
        results = await asyncio.gather(*[handler() for _ in range(10)])

        elapsed = time.time() - start

        # 순차 실행이면 0.1초 이상, 병렬이면 훨씬 짧음
        assert elapsed < 0.05  # 병렬 실행 확인
        assert len(set(results)) == 10


# =============================================================================
# Tests: CALL 스코프 리소스 관리
# =============================================================================


class TestCallScopeResourceManagement:
    """CALL 스코프 리소스 관리 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_multiple_resources_in_single_handler(self):
        """단일 Handler에서 여러 리소스"""

        @dataclass
        class ResourceA:
            id: int

        @dataclass
        class ResourceB:
            id: int

        @Configuration
        class MultiResourceConfig:
            _a_id: ClassVar[int] = 0
            _b_id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def resource_a(self) -> ResourceA:
                MultiResourceConfig._a_id += 1
                return ResourceA(id=MultiResourceConfig._a_id)

            @Factory(scope=ScopeEnum.CALL)
            async def resource_b(self) -> ResourceB:
                MultiResourceConfig._b_id += 1
                return ResourceB(id=MultiResourceConfig._b_id)

        @Component
        class MultiConsumer:
            a: AsyncProxy[ResourceA]
            b: AsyncProxy[ResourceB]

            async def get_ids(self) -> tuple[int, int]:
                a = await self.a.resolve()
                b = await self.b.resolve()
                return a.id, b.id

        manager = get_container_manager()
        register_factories_from_configuration(MultiResourceConfig, manager)
        MultiResourceConfig._a_id = 0
        MultiResourceConfig._b_id = 0
        await manager.initialize()

        consumer = manager.get_instance(MultiConsumer)

        @Handler
        async def handler():
            return await consumer.get_ids()

        id_a1, id_b1 = await handler()
        id_a2, id_b2 = await handler()

        # 각 Handler에서 각 리소스 새로 생성
        assert id_a1 == 1 and id_b1 == 1
        assert id_a2 == 2 and id_b2 == 2
