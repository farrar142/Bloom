"""CALL 스코프 통합 테스트

Handler 데코레이터를 사용한 CALL 스코프 통합 테스트.
"""

import pytest
import asyncio
from dataclasses import dataclass
from typing import ClassVar, Any

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
class CallSession:
    """CALL 스코프 세션"""

    id: int
    data: dict[str, Any] = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


# =============================================================================
# Tests
# =============================================================================


class TestCallScopeLifecycle:
    """CALL 스코프 라이프사이클 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_call_scope_create_per_handler(self):
        """Handler마다 새 CALL 스코프 인스턴스 생성"""
        session_ids: list[int] = []

        @Configuration
        class SessionConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def call_session(self) -> CallSession:
                SessionConfig._id += 1
                session_ids.append(SessionConfig._id)
                return CallSession(id=SessionConfig._id)

        @Component
        class Consumer:
            session: AsyncProxy[CallSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(SessionConfig, manager)
        SessionConfig._id = 0
        session_ids.clear()

        consumer = await manager.get_instance_async(Consumer)

        @Handler
        async def handler():
            return await consumer.get_session_id()

        # 3번 Handler 호출 = 3개 세션
        await handler()
        await handler()
        await handler()

        assert session_ids == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_multiple_call_scoped_share_context(self):
        """같은 Handler 내에서 여러 CALL 스코프 리소스 공유"""

        @Configuration
        class SharedConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def shared_session(self) -> CallSession:
                SharedConfig._id += 1
                return CallSession(id=SharedConfig._id)

        @Component
        class ConsumerA:
            session: AsyncProxy[CallSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        @Component
        class ConsumerB:
            session: AsyncProxy[CallSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(SharedConfig, manager)
        SharedConfig._id = 0

        consumer_a = await manager.get_instance_async(ConsumerA)
        consumer_b = await manager.get_instance_async(ConsumerB)

        @Handler
        async def handler():
            id_a = await consumer_a.get_session_id()
            id_b = await consumer_b.get_session_id()
            return id_a, id_b

        id_a, id_b = await handler()

        # 같은 Handler = 같은 세션
        assert id_a == id_b == 1


class TestNestedHandlers:
    """중첩 Handler 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_nested_handler_separate_contexts(self):
        """중첩 Handler는 별도 컨텍스트"""

        @Configuration
        class NestedConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def nested_session(self) -> CallSession:
                NestedConfig._id += 1
                return CallSession(id=NestedConfig._id)

        @Component
        class NestedConsumer:
            session: AsyncProxy[CallSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(NestedConfig, manager)
        NestedConfig._id = 0

        consumer = await manager.get_instance_async(NestedConsumer)

        @Handler
        async def inner():
            return await consumer.get_session_id()

        @Handler
        async def outer():
            outer_id = await consumer.get_session_id()
            inner_id = await inner()
            return outer_id, inner_id

        outer_id, inner_id = await outer()

        assert outer_id == 1
        assert inner_id == 2

    @pytest.mark.asyncio
    async def test_deeply_nested_handlers(self):
        """깊은 중첩 Handler"""

        @Configuration
        class DeepConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def deep_session(self) -> CallSession:
                DeepConfig._id += 1
                return CallSession(id=DeepConfig._id)

        @Component
        class DeepConsumer:
            session: AsyncProxy[CallSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(DeepConfig, manager)
        DeepConfig._id = 0

        consumer = await manager.get_instance_async(DeepConsumer)

        @Handler
        async def level3():
            return await consumer.get_session_id()

        @Handler
        async def level2():
            id2 = await consumer.get_session_id()
            id3 = await level3()
            return id2, id3

        @Handler
        async def level1():
            id1 = await consumer.get_session_id()
            id2, id3 = await level2()
            return id1, id2, id3

        ids = await level1()

        assert ids == (1, 2, 3)


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
        """동시 Handler 간 격리"""

        @Configuration
        class ConcConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def conc_session(self) -> CallSession:
                async with ConcConfig._lock:
                    ConcConfig._id += 1
                    return CallSession(id=ConcConfig._id)

        @Component
        class ConcConsumer:
            session: AsyncProxy[CallSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(ConcConfig, manager)
        ConcConfig._id = 0

        consumer = await manager.get_instance_async(ConcConsumer)

        @Handler
        async def handler(delay: float):
            await asyncio.sleep(delay)
            return await consumer.get_session_id()

        # 동시에 여러 Handler
        results = await asyncio.gather(
            handler(0.02),
            handler(0.01),
            handler(0.03),
        )

        # 모두 다른 세션
        assert len(set(results)) == 3

    @pytest.mark.asyncio
    async def test_concurrent_handlers_no_data_leak(self):
        """동시 Handler 간 데이터 누수 없음"""

        @Configuration
        class LeakConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def leak_session(self) -> CallSession:
                async with LeakConfig._lock:
                    LeakConfig._id += 1
                    return CallSession(id=LeakConfig._id)

        @Component
        class LeakConsumer:
            session: AsyncProxy[CallSession]

            async def store_and_retrieve(
                self, key: str, value: str, delay: float
            ) -> tuple:
                s = await self.session.resolve()
                s.data[key] = value
                await asyncio.sleep(delay)
                return s.id, s.data.get(key)

        manager = get_container_manager()
        register_factories_from_configuration(LeakConfig, manager)
        LeakConfig._id = 0

        consumer = await manager.get_instance_async(LeakConsumer)

        @Handler
        async def handler(key: str, value: str, delay: float):
            return await consumer.store_and_retrieve(key, value, delay)

        # 동시에 같은 키에 다른 값
        results = await asyncio.gather(
            handler("key", "A", 0.02),
            handler("key", "B", 0.01),
        )

        # 각자 자신의 값만 봄
        for session_id, retrieved in results:
            assert retrieved in ["A", "B"]


class TestCallScopeExceptions:
    """CALL 스코프 예외 처리 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_exception_does_not_affect_next_handler(self):
        """예외가 다음 Handler에 영향 없음"""

        @Configuration
        class ExcConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def exc_session(self) -> CallSession:
                ExcConfig._id += 1
                return CallSession(id=ExcConfig._id)

        @Component
        class ExcConsumer:
            session: AsyncProxy[CallSession]

            async def may_fail(self, should_fail: bool) -> int:
                s = await self.session.resolve()
                if should_fail:
                    raise ValueError(f"Intentional failure with session {s.id}")
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(ExcConfig, manager)
        ExcConfig._id = 0

        consumer = await manager.get_instance_async(ExcConsumer)

        @Handler
        async def handler(fail: bool):
            return await consumer.may_fail(fail)

        # 첫 번째 성공
        r1 = await handler(False)
        assert r1 == 1

        # 두 번째 실패
        with pytest.raises(ValueError):
            await handler(True)

        # 세 번째 성공 - 영향 없음
        r3 = await handler(False)
        assert r3 == 3
