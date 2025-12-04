"""@Transactional 엣지케이스 테스트

극단적인 상황과 예외 처리 테스트.
"""

import pytest
import asyncio
from typing import ClassVar
from dataclasses import dataclass, field

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
from bloom.db.decorators import (
    Transactional,
    Propagation,
    NoActiveTransactionError,
    RequiresNew,
    Mandatory,
)


# =============================================================================
# Mock Classes
# =============================================================================


@dataclass
class MockSession:
    """Mock 세션"""

    id: int
    operations: list = field(default_factory=list)
    committed: bool = False
    closed: bool = False

    def add(self, op: str):
        self.operations.append(op)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.operations.clear()

    async def close(self):
        self.closed = True


# =============================================================================
# Tests: 예외 처리
# =============================================================================


class TestTransactionalExceptionHandling:
    """예외 처리 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_exception_propagates_correctly(self):
        """예외가 올바르게 전파됨"""

        @Configuration
        class ExcConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def exc_session(self) -> MockSession:
                ExcConfig._id += 1
                return MockSession(id=ExcConfig._id)

        @Component
        class ExcService:
            session: AsyncProxy[MockSession]

            @Transactional
            async def failing_work(self):
                s = await self.session.resolve()
                s.add("before_error")
                raise ValueError("Intentional error")

        manager = get_container_manager()
        register_factories_from_configuration(ExcConfig, manager)
        ExcConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(ExcService)

        with pytest.raises(ValueError, match="Intentional error"):
            await service.failing_work()

    @pytest.mark.asyncio
    async def test_scope_cleanup_after_exception(self):
        """예외 후 스코프 정리"""

        @Configuration
        class CleanupConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def cleanup_session(self) -> MockSession:
                CleanupConfig._id += 1
                return MockSession(id=CleanupConfig._id)

        @Component
        class CleanupService:
            session: AsyncProxy[MockSession]

            @Transactional
            async def work_that_fails(self):
                await self.session.resolve()
                raise RuntimeError("Failed")

            @Transactional
            async def work_after_failure(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(CleanupConfig, manager)
        CleanupConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(CleanupService)

        # 첫 번째 호출 실패
        with pytest.raises(RuntimeError):
            await service.work_that_fails()

        # 두 번째 호출은 새 스코프에서 정상 동작
        id2 = await service.work_after_failure()
        assert id2 == 2  # 새 세션

    @pytest.mark.asyncio
    async def test_mandatory_error_message_contains_method_name(self):
        """MANDATORY 예외 메시지에 메서드 이름 포함"""

        @Configuration
        class MsgConfig:
            @Factory(scope=ScopeEnum.CALL)
            async def msg_session(self) -> MockSession:
                return MockSession(id=1)

        @Component
        class MsgService:
            session: AsyncProxy[MockSession]

            @Mandatory
            async def my_important_method(self):
                pass

        manager = get_container_manager()
        register_factories_from_configuration(MsgConfig, manager)
        await manager.initialize()

        service = manager.get_instance(MsgService)

        with pytest.raises(NoActiveTransactionError) as exc_info:
            await service.my_important_method()

        assert "my_important_method" in str(exc_info.value)


# =============================================================================
# Tests: 깊은 중첩
# =============================================================================


class TestDeepNesting:
    """깊은 중첩 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_very_deep_transactional_chain(self):
        """매우 깊은 @Transactional 체인"""

        @Configuration
        class DeepConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def deep_session(self) -> MockSession:
                DeepConfig._id += 1
                return MockSession(id=DeepConfig._id)

        @Component
        class DeepService:
            session: AsyncProxy[MockSession]

            @Transactional
            async def level(self, depth: int, results: list) -> int:
                s = await self.session.resolve()
                results.append(s.id)
                if depth > 0:
                    await self.level(depth - 1, results)
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(DeepConfig, manager)
        DeepConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(DeepService)
        results: list = []

        await service.level(10, results)

        # 모든 레벨에서 같은 세션 (REQUIRED 전파)
        assert all(id == 1 for id in results)
        assert len(results) == 11

    @pytest.mark.asyncio
    async def test_alternating_propagation_deep_chain(self):
        """교차하는 전파 방식의 깊은 체인"""

        @Configuration
        class AltConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def alt_session(self) -> MockSession:
                AltConfig._id += 1
                return MockSession(id=AltConfig._id)

        @Component
        class AltService:
            session: AsyncProxy[MockSession]

            @Transactional
            async def required_level(self, depth: int, results: list):
                s = await self.session.resolve()
                results.append(("REQ", s.id))
                if depth > 0:
                    await self.new_level(depth - 1, results)

            @RequiresNew
            async def new_level(self, depth: int, results: list):
                s = await self.session.resolve()
                results.append(("NEW", s.id))
                if depth > 0:
                    await self.required_level(depth - 1, results)

        manager = get_container_manager()
        register_factories_from_configuration(AltConfig, manager)
        AltConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(AltService)
        results: list = []

        await service.required_level(5, results)

        # REQ는 NEW와 같은 세션, 새 NEW마다 새 세션
        # REQ(1) -> NEW(2) -> REQ(2) -> NEW(3) -> REQ(3) -> NEW(4)
        assert results[0] == ("REQ", 1)
        assert results[1] == ("NEW", 2)
        assert results[2] == ("REQ", 2)  # NEW(2)와 공유
        assert results[3] == ("NEW", 3)
        assert results[4] == ("REQ", 3)  # NEW(3)와 공유


# =============================================================================
# Tests: @Handler와의 상호작용
# =============================================================================


class TestTransactionalWithHandler:
    """@Transactional과 @Handler 상호작용"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_transactional_inside_handler(self):
        """@Handler 내부에서 @Transactional 호출"""

        @Configuration
        class HtConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def ht_session(self) -> MockSession:
                HtConfig._id += 1
                return MockSession(id=HtConfig._id)

        @Component
        class HtService:
            session: AsyncProxy[MockSession]

            @Transactional
            async def transactional_work(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(HtConfig, manager)
        HtConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(HtService)

        @Handler
        async def api_handler():
            return await service.transactional_work()

        result = await api_handler()

        # @Handler가 먼저 스코프를 만들고, @Transactional(REQUIRED)은 재사용
        assert result == 1

    @pytest.mark.asyncio
    async def test_handler_with_propagate_false_and_transactional(self):
        """@Handler(propagate=False)와 @Transactional"""

        @Configuration
        class HpConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def hp_session(self) -> MockSession:
                HpConfig._id += 1
                return MockSession(id=HpConfig._id)

        @Component
        class HpService:
            session: AsyncProxy[MockSession]

            @Transactional  # REQUIRED
            async def tx_work(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(HpConfig, manager)
        HpConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(HpService)

        @Handler
        async def outer_handler():
            @Handler  # propagate=False (기본)
            async def inner_handler():
                return await service.tx_work()

            outer_id = (await service.session.resolve()).id
            inner_id = await inner_handler()
            return outer_id, inner_id

        outer_id, inner_id = await outer_handler()

        # outer와 inner는 다른 스코프
        assert outer_id == 1
        assert inner_id == 2


# =============================================================================
# Tests: 동시성 엣지케이스
# =============================================================================


class TestConcurrencyEdgeCases:
    """동시성 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_many_concurrent_required_transactions(self):
        """대량 동시 REQUIRED 트랜잭션"""

        @Configuration
        class ManyConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def many_session(self) -> MockSession:
                async with ManyConfig._lock:
                    ManyConfig._id += 1
                    return MockSession(id=ManyConfig._id)

        @Component
        class ManyService:
            session: AsyncProxy[MockSession]

            @Transactional
            async def work(self) -> int:
                s = await self.session.resolve()
                await asyncio.sleep(0.001)
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(ManyConfig, manager)
        ManyConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(ManyService)

        # 100개 동시 트랜잭션
        results = await asyncio.gather(*[service.work() for _ in range(100)])

        assert len(set(results)) == 100

    @pytest.mark.asyncio
    async def test_requires_new_under_concurrent_load(self):
        """동시 부하에서 REQUIRES_NEW"""

        @Configuration
        class NewLoadConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def newload_session(self) -> MockSession:
                async with NewLoadConfig._lock:
                    NewLoadConfig._id += 1
                    return MockSession(id=NewLoadConfig._id)

        @Component
        class NewLoadService:
            session: AsyncProxy[MockSession]

            @RequiresNew
            async def new_tx_work(self) -> int:
                s = await self.session.resolve()
                await asyncio.sleep(0.001)
                return s.id

            @Transactional
            async def parent_work(self) -> tuple[int, int]:
                s = await self.session.resolve()
                parent_id = s.id
                child_id = await self.new_tx_work()
                return parent_id, child_id

        manager = get_container_manager()
        register_factories_from_configuration(NewLoadConfig, manager)
        NewLoadConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(NewLoadService)

        # 50개 동시 실행
        results = await asyncio.gather(*[service.parent_work() for _ in range(50)])

        # 각 parent와 child는 다른 ID
        for parent_id, child_id in results:
            assert parent_id != child_id


# =============================================================================
# Tests: 특수 케이스
# =============================================================================


class TestSpecialCases:
    """특수 케이스 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_transactional_with_no_session_usage(self):
        """세션을 사용하지 않는 @Transactional"""

        @Configuration
        class NoUseConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def nouse_session(self) -> MockSession:
                NoUseConfig._id += 1
                return MockSession(id=NoUseConfig._id)

        @Component
        class NoUseService:
            session: AsyncProxy[MockSession]

            @Transactional
            async def no_session_work(self) -> str:
                # 세션 사용 안 함
                return "done"

        manager = get_container_manager()
        register_factories_from_configuration(NoUseConfig, manager)
        NoUseConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(NoUseService)

        result = await service.no_session_work()

        assert result == "done"
        # 세션이 생성되지 않음
        assert NoUseConfig._id == 0

    @pytest.mark.asyncio
    async def test_transactional_returns_various_types(self):
        """다양한 반환 타입"""

        @Configuration
        class RetConfig:
            @Factory(scope=ScopeEnum.CALL)
            async def ret_session(self) -> MockSession:
                return MockSession(id=1)

        @Component
        class RetService:
            session: AsyncProxy[MockSession]

            @Transactional
            async def return_none(self):
                pass

            @Transactional
            async def return_int(self) -> int:
                return 42

            @Transactional
            async def return_list(self) -> list:
                return [1, 2, 3]

            @Transactional
            async def return_dict(self) -> dict:
                return {"key": "value"}

        manager = get_container_manager()
        register_factories_from_configuration(RetConfig, manager)
        await manager.initialize()

        service = manager.get_instance(RetService)

        assert await service.return_none() is None
        assert await service.return_int() == 42
        assert await service.return_list() == [1, 2, 3]
        assert await service.return_dict() == {"key": "value"}

    @pytest.mark.asyncio
    async def test_transactional_with_self_reference(self):
        """자기 참조 호출"""

        @Configuration
        class SelfRefConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def selfref_session(self) -> MockSession:
                SelfRefConfig._id += 1
                return MockSession(id=SelfRefConfig._id)

        @Component
        class SelfRefService:
            session: AsyncProxy[MockSession]

            @Transactional
            async def outer_method(self) -> tuple[int, int]:
                s = await self.session.resolve()
                outer_id = s.id
                inner_id = await self.inner_method()
                return outer_id, inner_id

            @Transactional
            async def inner_method(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(SelfRefConfig, manager)
        SelfRefConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(SelfRefService)

        outer_id, inner_id = await service.outer_method()

        # 같은 트랜잭션
        assert outer_id == inner_id == 1


# =============================================================================
# Tests: read_only 힌트
# =============================================================================


class TestReadOnlyHint:
    """read_only 힌트 테스트"""

    def test_read_only_metadata_is_set(self):
        """read_only 메타데이터 설정 확인"""

        @Transactional(read_only=True)
        async def read_only_method():
            pass

        @Transactional(read_only=False)
        async def write_method():
            pass

        @Transactional
        async def default_method():
            pass

        assert getattr(read_only_method, "__bloom_transactional_read_only__")
        assert not getattr(write_method, "__bloom_transactional_read_only__")
        assert not getattr(default_method, "__bloom_transactional_read_only__")


# =============================================================================
# Tests: MANDATORY 전파 엣지케이스
# =============================================================================


class TestMandatoryEdgeCases:
    """MANDATORY 전파 엣지케이스"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_mandatory_after_requires_new(self):
        """REQUIRES_NEW 후 MANDATORY"""

        @Configuration
        class MandNewConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def mandnew_session(self) -> MockSession:
                MandNewConfig._id += 1
                return MockSession(id=MandNewConfig._id)

        @Component
        class MandNewService:
            session: AsyncProxy[MockSession]

            @Mandatory
            async def mandatory_work(self) -> int:
                s = await self.session.resolve()
                return s.id

            @RequiresNew
            async def new_then_mandatory(self) -> tuple[int, int]:
                s = await self.session.resolve()
                new_id = s.id
                mand_id = await self.mandatory_work()
                return new_id, mand_id

            @Transactional
            async def start(self) -> tuple[int, int, int]:
                s = await self.session.resolve()
                start_id = s.id
                new_id, mand_id = await self.new_then_mandatory()
                return start_id, new_id, mand_id

        manager = get_container_manager()
        register_factories_from_configuration(MandNewConfig, manager)
        MandNewConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(MandNewService)

        start_id, new_id, mand_id = await service.start()

        # start: 1, new: 2, mandatory: 2 (new와 공유)
        assert start_id == 1
        assert new_id == 2
        assert mand_id == 2

    @pytest.mark.asyncio
    async def test_mandatory_fails_after_scope_ends(self):
        """스코프 종료 후 MANDATORY 호출 실패"""

        @Configuration
        class MandFailConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def mandfail_session(self) -> MockSession:
                MandFailConfig._id += 1
                return MockSession(id=MandFailConfig._id)

        mandatory_service_ref = []

        @Component
        class MandFailService:
            session: AsyncProxy[MockSession]

            @Mandatory
            async def mandatory_method(self) -> int:
                s = await self.session.resolve()
                return s.id

            @Transactional
            async def store_and_return(self) -> int:
                mandatory_service_ref.append(self)
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(MandFailConfig, manager)
        MandFailConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(MandFailService)

        # 트랜잭션 내에서 호출
        await service.store_and_return()

        # 트랜잭션 끝난 후 mandatory 호출
        with pytest.raises(NoActiveTransactionError):
            await mandatory_service_ref[0].mandatory_method()
