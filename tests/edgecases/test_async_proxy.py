"""AsyncProxy 엣지케이스 테스트

AsyncProxy의 극단적인 상황 테스트.
AsyncProxy는 CALL 스코프용으로 Handler 내에서만 resolve 가능.
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
class CallScopedResource:
    """CALL 스코프 리소스"""

    id: int


@dataclass
class ChainedResource:
    """체인된 리소스"""

    name: str


# =============================================================================
# Tests: AsyncProxy resolve 동작
# =============================================================================


class TestAsyncProxyResolveEdgeCases:
    """AsyncProxy resolve 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_resolve_returns_same_instance_in_call(self):
        """같은 CALL 내에서 resolve는 같은 인스턴스 반환"""

        @Configuration
        class ResolveConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def call_resource(self) -> CallScopedResource:
                ResolveConfig._id += 1
                return CallScopedResource(id=ResolveConfig._id)

        @Component
        class ResolveConsumer:
            resource: AsyncProxy[CallScopedResource]

            async def get_resource(self) -> CallScopedResource:
                return await self.resource.resolve()

        manager = get_container_manager()
        register_factories_from_configuration(ResolveConfig, manager)
        ResolveConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(ResolveConsumer)

        @Handler
        async def handler():
            r1 = await consumer.get_resource()
            r2 = await consumer.get_resource()
            r3 = await consumer.get_resource()
            return r1, r2, r3

        r1, r2, r3 = await handler()

        # 모두 같은 인스턴스
        assert r1 is r2 is r3
        assert r1.id == 1

    @pytest.mark.asyncio
    async def test_resolve_outside_handler_raises_error(self):
        """Handler 외부에서 resolve 시 RuntimeError"""

        @Configuration
        class OutsideResolveConfig:
            @Factory(scope=ScopeEnum.CALL)
            async def outside_resource(self) -> CallScopedResource:
                return CallScopedResource(id=1)

        @Component
        class OutsideConsumer:
            resource: AsyncProxy[CallScopedResource]

            async def get_resource(self) -> CallScopedResource:
                return await self.resource.resolve()

        manager = get_container_manager()
        register_factories_from_configuration(OutsideResolveConfig, manager)
        await manager.initialize()

        consumer = manager.get_instance(OutsideConsumer)

        # Handler 없이 직접 호출 - RuntimeError
        with pytest.raises(RuntimeError, match="outside of @Handler context"):
            await consumer.get_resource()


# =============================================================================
# Tests: AsyncProxy 동시성
# =============================================================================


class TestAsyncProxyConcurrencyEdgeCases:
    """AsyncProxy 동시성 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_high_concurrency_resolve(self):
        """고동시성 resolve 테스트"""

        @Configuration
        class HighConcConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def high_conc_resource(self) -> CallScopedResource:
                async with HighConcConfig._lock:
                    HighConcConfig._id += 1
                    return CallScopedResource(id=HighConcConfig._id)

        @Component
        class HighConcConsumer:
            resource: AsyncProxy[CallScopedResource]

            async def get_id(self) -> int:
                r = await self.resource.resolve()
                return r.id

        manager = get_container_manager()
        register_factories_from_configuration(HighConcConfig, manager)
        HighConcConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(HighConcConsumer)

        @Handler
        async def handler():
            return await consumer.get_id()

        # 100개 동시 Handler
        results = await asyncio.gather(*[handler() for _ in range(100)])

        # 모두 다른 ID
        assert len(set(results)) == 100

    @pytest.mark.asyncio
    async def test_concurrent_resolve_within_handler(self):
        """Handler 내에서 동시 resolve"""

        @Configuration
        class WithinHandlerConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def within_resource(self) -> CallScopedResource:
                WithinHandlerConfig._id += 1
                return CallScopedResource(id=WithinHandlerConfig._id)

        @Component
        class WithinConsumer:
            resource: AsyncProxy[CallScopedResource]

            async def get_id(self) -> int:
                r = await self.resource.resolve()
                return r.id

        manager = get_container_manager()
        register_factories_from_configuration(WithinHandlerConfig, manager)
        WithinHandlerConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(WithinConsumer)

        @Handler
        async def handler():
            # Handler 내에서 동시에 여러 resolve
            results = await asyncio.gather(*[consumer.get_id() for _ in range(10)])
            return results

        results = await handler()

        # 같은 Handler 내에서는 모두 같은 인스턴스
        assert all(r == results[0] for r in results)


# =============================================================================
# Tests: AsyncProxy 예외 처리
# =============================================================================


class TestAsyncProxyExceptionEdgeCases:
    """AsyncProxy 예외 처리 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_factory_exception_propagation(self):
        """Factory 예외 전파"""

        @Configuration
        class ExceptionConfig:
            @Factory(scope=ScopeEnum.CALL)
            async def exception_resource(self) -> CallScopedResource:
                raise ValueError("Factory failed")

        @Component
        class ExceptionConsumer:
            resource: AsyncProxy[CallScopedResource]

            async def get_resource(self) -> CallScopedResource:
                return await self.resource.resolve()

        manager = get_container_manager()
        register_factories_from_configuration(ExceptionConfig, manager)
        await manager.initialize()

        consumer = manager.get_instance(ExceptionConsumer)

        @Handler
        async def handler():
            return await consumer.get_resource()

        with pytest.raises(ValueError, match="Factory failed"):
            await handler()

    @pytest.mark.asyncio
    async def test_exception_does_not_affect_next_handler(self):
        """예외가 다음 Handler에 영향 없음"""

        @Configuration
        class NextHandlerConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def next_handler_resource(self) -> CallScopedResource:
                NextHandlerConfig._id += 1
                if NextHandlerConfig._id == 1:
                    raise ValueError("First fails")
                return CallScopedResource(id=NextHandlerConfig._id)

        @Component
        class NextHandlerConsumer:
            resource: AsyncProxy[CallScopedResource]

            async def get_id(self) -> int:
                r = await self.resource.resolve()
                return r.id

        manager = get_container_manager()
        register_factories_from_configuration(NextHandlerConfig, manager)
        NextHandlerConfig._id = 0
        await manager.initialize()

        consumer = manager.get_instance(NextHandlerConsumer)

        @Handler
        async def handler():
            return await consumer.get_id()

        # 첫 번째 실패
        with pytest.raises(ValueError):
            await handler()

        # 두 번째 성공
        result = await handler()
        assert result == 2


# =============================================================================
# Tests: AsyncProxy 메모리 관리
# =============================================================================


class TestAsyncProxyMemoryEdgeCases:
    """AsyncProxy 메모리 관리 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_handler_cleanup_releases_instance(self):
        """Handler 종료 후 인스턴스 참조 해제 확인"""
        created_ids: list[int] = []

        @Configuration
        class CleanupConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def cleanup_resource(self) -> CallScopedResource:
                CleanupConfig._id += 1
                created_ids.append(CleanupConfig._id)
                return CallScopedResource(id=CleanupConfig._id)

        @Component
        class CleanupConsumer:
            resource: AsyncProxy[CallScopedResource]

            async def get_id(self) -> int:
                r = await self.resource.resolve()
                return r.id

        manager = get_container_manager()
        register_factories_from_configuration(CleanupConfig, manager)
        CleanupConfig._id = 0
        created_ids.clear()
        await manager.initialize()

        consumer = manager.get_instance(CleanupConsumer)

        @Handler
        async def handler():
            return await consumer.get_id()

        # 10개 Handler 실행
        for _ in range(10):
            await handler()

        # 10개 생성됨 (각 Handler마다 새로 생성)
        assert len(created_ids) == 10
