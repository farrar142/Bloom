"""Repository-Session 통합 테스트

Repository 패턴과 Session의 CALL 스코프 통합 테스트.
"""

import pytest
import asyncio
from dataclasses import dataclass, field
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
class MockSession:
    """Mock 데이터베이스 세션"""
    id: int
    data: dict = field(default_factory=dict)
    committed: bool = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.data.clear()

    def add(self, key: str, value: str):
        self.data[key] = value


# =============================================================================
# Tests
# =============================================================================


class TestRepositorySessionIntegration:
    """Repository-Session 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_repository_with_session_proxy(self):
        """Repository가 AsyncProxy[Session] 사용"""

        @Configuration
        class RepoConfig:
            _session_id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def mock_session(self) -> MockSession:
                RepoConfig._session_id += 1
                return MockSession(id=RepoConfig._session_id)

        @Component
        class UserRepository:
            session: AsyncProxy[MockSession]

            async def create_user(self, name: str) -> int:
                s = await self.session.resolve()
                s.add("user", name)
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(RepoConfig, manager)
        RepoConfig._session_id = 0
        await manager.initialize()

        repo = manager.get_instance(UserRepository)

        @Handler
        async def create_user_handler(name: str):
            return await repo.create_user(name)

        # 각 Handler는 새 세션
        id1 = await create_user_handler("Alice")
        id2 = await create_user_handler("Bob")

        assert id1 == 1
        assert id2 == 2

    @pytest.mark.asyncio
    async def test_same_session_within_handler(self):
        """같은 Handler 내에서 세션 공유"""

        @Configuration
        class SessionShareConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def shared_session(self) -> MockSession:
                SessionShareConfig._id += 1
                return MockSession(id=SessionShareConfig._id)

        @Component
        class RepoA:
            session: AsyncProxy[MockSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        @Component
        class RepoB:
            session: AsyncProxy[MockSession]

            async def get_session_id(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(SessionShareConfig, manager)
        SessionShareConfig._id = 0
        await manager.initialize()

        repo_a = manager.get_instance(RepoA)
        repo_b = manager.get_instance(RepoB)

        @Handler
        async def handler():
            id_a = await repo_a.get_session_id()
            id_b = await repo_b.get_session_id()
            return id_a, id_b

        id_a, id_b = await handler()

        # 같은 Handler 내에서는 같은 세션
        assert id_a == id_b == 1


class TestTransactionIntegration:
    """트랜잭션 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_transaction_isolation_between_handlers(self):
        """Handler 간 트랜잭션 격리"""

        @Configuration
        class TxConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def tx_session(self) -> MockSession:
                TxConfig._id += 1
                return MockSession(id=TxConfig._id)

        @Component
        class TxRepository:
            session: AsyncProxy[MockSession]

            async def add_item(self, key: str, value: str):
                s = await self.session.resolve()
                s.add(key, value)

            async def commit(self):
                s = await self.session.resolve()
                await s.commit()

            async def get_data(self) -> dict:
                s = await self.session.resolve()
                return s.data.copy()

        manager = get_container_manager()
        register_factories_from_configuration(TxConfig, manager)
        TxConfig._id = 0
        await manager.initialize()

        repo = manager.get_instance(TxRepository)

        @Handler
        async def handler1():
            await repo.add_item("h1_key", "h1_value")
            await repo.commit()
            return await repo.get_data()

        @Handler
        async def handler2():
            await repo.add_item("h2_key", "h2_value")
            return await repo.get_data()

        data1 = await handler1()
        data2 = await handler2()

        # 각 Handler는 독립적인 트랜잭션
        assert data1 == {"h1_key": "h1_value"}
        assert data2 == {"h2_key": "h2_value"}


class TestSessionLifecycleIntegration:
    """세션 라이프사이클 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_session_created_per_handler(self):
        """Handler마다 새 세션 생성"""
        created_sessions: list[int] = []

        @Configuration
        class LifecycleConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def lifecycle_session(self) -> MockSession:
                LifecycleConfig._id += 1
                created_sessions.append(LifecycleConfig._id)
                return MockSession(id=LifecycleConfig._id)

        @Component
        class LifecycleRepo:
            session: AsyncProxy[MockSession]

            async def touch(self):
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(LifecycleConfig, manager)
        LifecycleConfig._id = 0
        created_sessions.clear()
        await manager.initialize()

        repo = manager.get_instance(LifecycleRepo)

        @Handler
        async def handler():
            return await repo.touch()

        # 5번 Handler 호출
        for _ in range(5):
            await handler()

        # 5개 세션 생성됨
        assert len(created_sessions) == 5
        assert created_sessions == [1, 2, 3, 4, 5]

    @pytest.mark.asyncio
    async def test_session_reused_within_handler(self):
        """Handler 내에서 세션 재사용"""
        resolve_count = {"count": 0}

        @Configuration
        class ReuseConfig:
            @Factory(scope=ScopeEnum.CALL)
            async def reuse_session(self) -> MockSession:
                resolve_count["count"] += 1
                return MockSession(id=resolve_count["count"])

        @Component
        class ReuseRepo:
            session: AsyncProxy[MockSession]

            async def get_session(self) -> MockSession:
                return await self.session.resolve()

        manager = get_container_manager()
        register_factories_from_configuration(ReuseConfig, manager)
        resolve_count["count"] = 0
        await manager.initialize()

        repo = manager.get_instance(ReuseRepo)

        @Handler
        async def handler():
            s1 = await repo.get_session()
            s2 = await repo.get_session()
            s3 = await repo.get_session()
            return s1, s2, s3

        s1, s2, s3 = await handler()

        # 같은 세션 (Factory는 한 번만 호출)
        assert s1 is s2 is s3
        assert resolve_count["count"] == 1


class TestConcurrentSessions:
    """동시 세션 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_concurrent_handlers_with_sessions(self):
        """동시 Handler에서 세션 격리"""

        @Configuration
        class ConcSessionConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def conc_session(self) -> MockSession:
                async with ConcSessionConfig._lock:
                    ConcSessionConfig._id += 1
                    return MockSession(id=ConcSessionConfig._id)

        @Component
        class ConcRepo:
            session: AsyncProxy[MockSession]

            async def work(self):
                s = await self.session.resolve()
                await asyncio.sleep(0.01)  # 지연
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(ConcSessionConfig, manager)
        ConcSessionConfig._id = 0
        await manager.initialize()

        repo = manager.get_instance(ConcRepo)

        @Handler
        async def handler():
            return await repo.work()

        # 동시에 20개 Handler 실행
        results = await asyncio.gather(*[handler() for _ in range(20)])

        # 모두 다른 세션 ID
        assert len(set(results)) == 20
