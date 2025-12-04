"""DI 프록시 통합 테스트

LazyProxy와 AsyncProxy의 통합 테스트.
LazyProxy는 manager.initialize() 후에 안전하게 접근 가능.
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
class CallScopedSession:
    """CALL 스코프 세션"""
    id: int


@dataclass
class SharedResource:
    """공유 리소스"""
    id: int


# =============================================================================
# Tests: LazyProxy (Component 간 순환 의존성)
# =============================================================================


class TestLazyProxyIntegration:
    """LazyProxy 통합 테스트 (순환 의존성)"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_lazy_proxy_circular_dependency_resolution(self):
        """LazyProxy 순환 의존성 해결 (Component 간)"""

        @Component
        class CircularA:
            b: "CircularB"  # forward reference, 자동으로 LazyProxy
            name: str = "A"

            def get_b_value(self) -> str:
                return self.b.name

        @Component
        class CircularB:
            a: CircularA  # 직접 참조, 자동으로 LazyProxy
            name: str = "B"

            def get_a_value(self) -> str:
                return self.a.name

        manager = get_container_manager()
        await manager.initialize()  # 모든 SINGLETON 생성

        a = manager.get_instance(CircularA)
        b = manager.get_instance(CircularB)

        # 순환 참조 해결됨
        assert a.get_b_value() == "B"
        assert b.get_a_value() == "A"

    @pytest.mark.asyncio
    async def test_three_way_circular_dependency(self):
        """3자 순환 의존성 해결"""

        @Component
        class ServiceX:
            y: "ServiceY"
            name: str = "X"

        @Component
        class ServiceY:
            z: "ServiceZ"
            name: str = "Y"

        @Component
        class ServiceZ:
            x: ServiceX
            name: str = "Z"

        manager = get_container_manager()
        await manager.initialize()

        x = manager.get_instance(ServiceX)
        y = manager.get_instance(ServiceY)
        z = manager.get_instance(ServiceZ)

        # 3자 순환 참조
        assert x.y.name == "Y"
        assert y.z.name == "Z"
        assert z.x.name == "X"


# =============================================================================
# Tests: AsyncProxy (CALL 스코프)
# =============================================================================


class TestAsyncProxyIntegration:
    """AsyncProxy 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_async_proxy_call_scope(self):
        """AsyncProxy CALL 스코프 - Handler마다 새 인스턴스"""

        @Configuration
        class SessionConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def call_session(self) -> CallScopedSession:
                SessionConfig._id += 1
                return CallScopedSession(id=SessionConfig._id)

        @Component
        class Repository:
            session: AsyncProxy[CallScopedSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(SessionConfig, manager)
        SessionConfig._id = 0
        await manager.initialize()

        repo = manager.get_instance(Repository)

        @Handler
        async def handler1():
            return await repo.get_session_id()

        @Handler
        async def handler2():
            return await repo.get_session_id()

        id1 = await handler1()
        id2 = await handler2()

        # 각 Handler는 독립적인 세션
        assert id1 == 1
        assert id2 == 2

    @pytest.mark.asyncio
    async def test_async_proxy_multiple_resolves_same_call(self):
        """같은 CALL에서 여러 번 resolve - 같은 인스턴스"""

        @Configuration
        class ResourceConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def call_resource(self) -> SharedResource:
                ResourceConfig._id += 1
                return SharedResource(id=ResourceConfig._id)

        @Component
        class ConsumerA:
            resource: AsyncProxy[SharedResource]

            async def get_id(self) -> int:
                r = await self.resource.resolve()
                return r.id

        @Component
        class ConsumerB:
            resource: AsyncProxy[SharedResource]

            async def get_id(self) -> int:
                r = await self.resource.resolve()
                return r.id

        manager = get_container_manager()
        register_factories_from_configuration(ResourceConfig, manager)
        ResourceConfig._id = 0
        await manager.initialize()

        consumer_a = manager.get_instance(ConsumerA)
        consumer_b = manager.get_instance(ConsumerB)

        @Handler
        async def handler():
            id_a = await consumer_a.get_id()
            id_b = await consumer_b.get_id()
            return id_a, id_b

        id_a, id_b = await handler()

        # 같은 Handler에서는 같은 인스턴스
        assert id_a == id_b == 1


# =============================================================================
# Tests: 스코프 전환
# =============================================================================


class TestScopeTransitionIntegration:
    """스코프 전환 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_singleton_to_call_scope_transition(self):
        """싱글톤에서 CALL 스코프로 전환"""

        @Configuration
        class TransitionConfig:
            _session_id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def call_session(self) -> CallScopedSession:
                TransitionConfig._session_id += 1
                return CallScopedSession(id=TransitionConfig._session_id)

        @Component
        class SingletonService:
            """싱글톤 서비스가 CALL 스코프 세션 사용"""
            session: AsyncProxy[CallScopedSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(TransitionConfig, manager)
        TransitionConfig._session_id = 0
        await manager.initialize()

        svc = manager.get_instance(SingletonService)

        @Handler
        async def handler():
            return await svc.get_session_id()

        # 같은 싱글톤 서비스지만 Handler마다 다른 세션
        assert await handler() == 1
        assert await handler() == 2
        assert await handler() == 3

    @pytest.mark.asyncio
    async def test_nested_handlers(self):
        """중첩 Handler"""

        @Configuration
        class NestedConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def nested_session(self) -> CallScopedSession:
                NestedConfig._id += 1
                return CallScopedSession(id=NestedConfig._id)

        @Component
        class NestedService:
            session: AsyncProxy[CallScopedSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(NestedConfig, manager)
        NestedConfig._id = 0
        await manager.initialize()

        svc = manager.get_instance(NestedService)

        @Handler
        async def inner_handler():
            return await svc.get_session_id()

        @Handler
        async def outer_handler():
            outer_id = await svc.get_session_id()
            inner_id = await inner_handler()
            return outer_id, inner_id

        outer_id, inner_id = await outer_handler()

        # 중첩 Handler는 각자 스코프
        assert outer_id == 1
        assert inner_id == 2


# =============================================================================
# Tests: 에러 처리
# =============================================================================


class TestProxyErrorHandling:
    """프록시 에러 처리 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_async_proxy_outside_handler_raises_error(self):
        """Handler 없이 AsyncProxy resolve - RuntimeError 발생"""

        @Configuration
        class OutsideConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def outside_session(self) -> CallScopedSession:
                OutsideConfig._id += 1
                return CallScopedSession(id=OutsideConfig._id)

        @Component
        class OutsideService:
            session: AsyncProxy[CallScopedSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(OutsideConfig, manager)
        OutsideConfig._id = 0
        await manager.initialize()

        svc = manager.get_instance(OutsideService)

        # Handler 없이 직접 호출 - RuntimeError 발생
        with pytest.raises(RuntimeError, match="outside of @Handler context"):
            await svc.get_session_id()


# =============================================================================
# Tests: 동시성
# =============================================================================


class TestConcurrentHandlers:
    """동시 Handler 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_concurrent_handlers_isolation(self):
        """동시 Handler 격리"""

        @Configuration
        class ConcConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def conc_session(self) -> CallScopedSession:
                async with ConcConfig._lock:
                    ConcConfig._id += 1
                    return CallScopedSession(id=ConcConfig._id)

        @Component
        class ConcService:
            session: AsyncProxy[CallScopedSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(ConcConfig, manager)
        ConcConfig._id = 0
        await manager.initialize()

        svc = manager.get_instance(ConcService)

        @Handler
        async def handler():
            return await svc.get_session_id()

        # 동시에 10개 Handler 실행
        results = await asyncio.gather(*[handler() for _ in range(10)])

        # 모두 다른 세션 ID
        assert len(set(results)) == 10
