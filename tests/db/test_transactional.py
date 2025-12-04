"""@Transactional 데코레이터 단위 테스트"""

import pytest
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
from bloom.core.decorators import register_factories_from_configuration
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
    rolled_back: bool = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    def add_operation(self, op: str):
        self.operations.append(op)


# =============================================================================
# Tests: 기본 @Transactional 동작
# =============================================================================


class TestTransactionalBasic:
    """@Transactional 기본 동작 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_transactional_creates_scope(self):
        """@Transactional이 CALL 스코프를 생성"""

        @Configuration
        class TxConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def session(self) -> MockSession:
                TxConfig._id += 1
                return MockSession(id=TxConfig._id)

        @Component
        class Service:
            session: AsyncProxy[MockSession]

            @Transactional
            async def do_work(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(TxConfig, manager)
        TxConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(Service)

        # 각 호출마다 새 스코프
        id1 = await service.do_work()
        id2 = await service.do_work()

        assert id1 == 1
        assert id2 == 2

    @pytest.mark.asyncio
    async def test_transactional_default_propagation_required(self):
        """@Transactional 기본값은 REQUIRED (부모 스코프 재사용)"""

        @Configuration
        class PropConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def prop_session(self) -> MockSession:
                PropConfig._id += 1
                return MockSession(id=PropConfig._id)

        @Component
        class InnerService:
            session: AsyncProxy[MockSession]

            @Transactional  # 기본값 REQUIRED
            async def inner_work(self) -> int:
                s = await self.session.resolve()
                return s.id

        @Component
        class OuterService:
            session: AsyncProxy[MockSession]
            inner: InnerService

            @Transactional
            async def outer_work(self) -> tuple[int, int]:
                s = await self.session.resolve()
                outer_id = s.id
                inner_id = await self.inner.inner_work()
                return outer_id, inner_id

        manager = get_container_manager()
        register_factories_from_configuration(PropConfig, manager)
        PropConfig._id = 0
        await manager.initialize()

        outer = manager.get_instance(OuterService)

        outer_id, inner_id = await outer.outer_work()

        # REQUIRED: 같은 트랜잭션 (같은 세션)
        assert outer_id == inner_id == 1

    @pytest.mark.asyncio
    async def test_transactional_with_explicit_required(self):
        """@Transactional(propagation=REQUIRED) 명시적 지정"""

        @Configuration
        class ExplicitConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def explicit_session(self) -> MockSession:
                ExplicitConfig._id += 1
                return MockSession(id=ExplicitConfig._id)

        @Component
        class ExplicitService:
            session: AsyncProxy[MockSession]

            @Transactional(propagation=Propagation.REQUIRED)
            async def work(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(ExplicitConfig, manager)
        ExplicitConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(ExplicitService)

        id1 = await service.work()
        id2 = await service.work()

        assert id1 == 1
        assert id2 == 2


# =============================================================================
# Tests: REQUIRES_NEW 전파
# =============================================================================


class TestTransactionalRequiresNew:
    """REQUIRES_NEW 전파 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_requires_new_creates_new_scope(self):
        """REQUIRES_NEW는 항상 새 스코프 생성"""

        @Configuration
        class NewConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def new_session(self) -> MockSession:
                NewConfig._id += 1
                return MockSession(id=NewConfig._id)

        @Component
        class NewInner:
            session: AsyncProxy[MockSession]

            @Transactional(propagation=Propagation.REQUIRES_NEW)
            async def new_work(self) -> int:
                s = await self.session.resolve()
                return s.id

        @Component
        class NewOuter:
            session: AsyncProxy[MockSession]
            inner: NewInner

            @Transactional
            async def outer_work(self) -> tuple[int, int]:
                s = await self.session.resolve()
                outer_id = s.id
                inner_id = await self.inner.new_work()
                return outer_id, inner_id

        manager = get_container_manager()
        register_factories_from_configuration(NewConfig, manager)
        NewConfig._id = 0
        await manager.initialize()

        outer = manager.get_instance(NewOuter)

        outer_id, inner_id = await outer.outer_work()

        # REQUIRES_NEW: 항상 다른 트랜잭션
        assert outer_id == 1
        assert inner_id == 2

    @pytest.mark.asyncio
    async def test_requires_new_alias_decorator(self):
        """@RequiresNew 별칭 데코레이터"""

        @Configuration
        class AliasConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def alias_session(self) -> MockSession:
                AliasConfig._id += 1
                return MockSession(id=AliasConfig._id)

        @Component
        class AliasInner:
            session: AsyncProxy[MockSession]

            @RequiresNew
            async def new_work(self) -> int:
                s = await self.session.resolve()
                return s.id

        @Component
        class AliasOuter:
            session: AsyncProxy[MockSession]
            inner: AliasInner

            @Transactional
            async def outer_work(self) -> tuple[int, int]:
                s = await self.session.resolve()
                outer_id = s.id
                inner_id = await self.inner.new_work()
                return outer_id, inner_id

        manager = get_container_manager()
        register_factories_from_configuration(AliasConfig, manager)
        AliasConfig._id = 0
        await manager.initialize()

        outer = manager.get_instance(AliasOuter)

        outer_id, inner_id = await outer.outer_work()

        assert outer_id == 1
        assert inner_id == 2


# =============================================================================
# Tests: MANDATORY 전파
# =============================================================================


class TestTransactionalMandatory:
    """MANDATORY 전파 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_mandatory_requires_existing_transaction(self):
        """MANDATORY는 기존 트랜잭션 필수"""

        @Configuration
        class MandConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def mand_session(self) -> MockSession:
                MandConfig._id += 1
                return MockSession(id=MandConfig._id)

        @Component
        class MandService:
            session: AsyncProxy[MockSession]

            @Transactional(propagation=Propagation.MANDATORY)
            async def mandatory_work(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(MandConfig, manager)
        MandConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(MandService)

        # 트랜잭션 없이 호출하면 예외
        with pytest.raises(NoActiveTransactionError):
            await service.mandatory_work()

    @pytest.mark.asyncio
    async def test_mandatory_works_within_transaction(self):
        """MANDATORY는 기존 트랜잭션 내에서 정상 동작"""

        @Configuration
        class MandOkConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def mandok_session(self) -> MockSession:
                MandOkConfig._id += 1
                return MockSession(id=MandOkConfig._id)

        @Component
        class MandOkInner:
            session: AsyncProxy[MockSession]

            @Transactional(propagation=Propagation.MANDATORY)
            async def inner_work(self) -> int:
                s = await self.session.resolve()
                return s.id

        @Component
        class MandOkOuter:
            session: AsyncProxy[MockSession]
            inner: MandOkInner

            @Transactional
            async def outer_work(self) -> tuple[int, int]:
                s = await self.session.resolve()
                outer_id = s.id
                inner_id = await self.inner.inner_work()
                return outer_id, inner_id

        manager = get_container_manager()
        register_factories_from_configuration(MandOkConfig, manager)
        MandOkConfig._id = 0
        await manager.initialize()

        outer = manager.get_instance(MandOkOuter)

        outer_id, inner_id = await outer.outer_work()

        # MANDATORY도 부모 트랜잭션 재사용
        assert outer_id == inner_id == 1

    @pytest.mark.asyncio
    async def test_mandatory_alias_decorator(self):
        """@Mandatory 별칭 데코레이터"""

        @Configuration
        class MandAliasConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def mandalias_session(self) -> MockSession:
                MandAliasConfig._id += 1
                return MockSession(id=MandAliasConfig._id)

        @Component
        class MandAliasService:
            session: AsyncProxy[MockSession]

            @Mandatory
            async def work(self) -> int:
                s = await self.session.resolve()
                return s.id

        manager = get_container_manager()
        register_factories_from_configuration(MandAliasConfig, manager)
        MandAliasConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(MandAliasService)

        with pytest.raises(NoActiveTransactionError):
            await service.work()


# =============================================================================
# Tests: 메타데이터 보존
# =============================================================================


class TestTransactionalMetadata:
    """@Transactional 메타데이터 테스트"""

    def test_transactional_preserves_function_name(self):
        """함수 이름 보존"""

        @Transactional
        async def my_function():
            pass

        assert my_function.__name__ == "my_function"

    def test_transactional_sets_metadata(self):
        """메타데이터 설정 확인"""

        @Transactional
        async def default_func():
            pass

        @Transactional(propagation=Propagation.REQUIRES_NEW)
        async def new_func():
            pass

        @Transactional(propagation=Propagation.MANDATORY, read_only=True)
        async def mandatory_func():
            pass

        assert getattr(default_func, "__bloom_transactional__", False)
        assert (
            getattr(default_func, "__bloom_transactional_propagation__")
            == Propagation.REQUIRED
        )

        assert (
            getattr(new_func, "__bloom_transactional_propagation__")
            == Propagation.REQUIRES_NEW
        )

        assert (
            getattr(mandatory_func, "__bloom_transactional_propagation__")
            == Propagation.MANDATORY
        )
        assert getattr(mandatory_func, "__bloom_transactional_read_only__")
