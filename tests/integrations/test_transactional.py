"""@Transactional 통합 테스트

실제 Repository/Session 패턴과의 통합 테스트.
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
from bloom.core.decorators import register_factories_from_configuration
from bloom.db.decorators import Transactional, Propagation, RequiresNew


# =============================================================================
# Mock Classes
# =============================================================================


@dataclass
class MockTransaction:
    """Mock 트랜잭션/세션"""

    id: int
    operations: list = field(default_factory=list)
    committed: bool = False

    def add(self, op: str):
        self.operations.append(op)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.operations.clear()


# =============================================================================
# Tests: Repository 패턴 통합
# =============================================================================


class TestTransactionalRepositoryIntegration:
    """@Transactional + Repository 패턴 통합 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_multiple_repositories_share_transaction(self):
        """여러 Repository가 같은 트랜잭션 공유"""

        @Configuration
        class TxConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def transaction(self) -> MockTransaction:
                TxConfig._id += 1
                return MockTransaction(id=TxConfig._id)

        @Component
        class UserRepository:
            tx: AsyncProxy[MockTransaction]

            async def create_user(self, name: str) -> int:
                t = await self.tx.resolve()
                t.add(f"INSERT user:{name}")
                return t.id

        @Component
        class OrderRepository:
            tx: AsyncProxy[MockTransaction]

            async def create_order(self, user: str, item: str) -> int:
                t = await self.tx.resolve()
                t.add(f"INSERT order:{user}:{item}")
                return t.id

        @Component
        class AuditRepository:
            tx: AsyncProxy[MockTransaction]

            async def log_action(self, action: str) -> int:
                t = await self.tx.resolve()
                t.add(f"AUDIT:{action}")
                return t.id

        @Component
        class OrderService:
            user_repo: UserRepository
            order_repo: OrderRepository
            audit_repo: AuditRepository
            tx: AsyncProxy[MockTransaction]

            @Transactional
            async def create_order_with_user(
                self, username: str, item: str
            ) -> tuple[list[str], int]:
                user_tx = await self.user_repo.create_user(username)
                order_tx = await self.order_repo.create_order(username, item)
                audit_tx = await self.audit_repo.log_action(
                    f"order_created:{username}:{item}"
                )

                t = await self.tx.resolve()
                await t.commit()

                return t.operations, t.id

        manager = get_container_manager()
        register_factories_from_configuration(TxConfig, manager)
        TxConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(OrderService)

        operations, tx_id = await service.create_order_with_user("alice", "laptop")

        # 모든 작업이 같은 트랜잭션에서 수행됨
        assert tx_id == 1
        assert len(operations) == 3
        assert "INSERT user:alice" in operations
        assert "INSERT order:alice:laptop" in operations
        assert "AUDIT:order_created:alice:laptop" in operations

    @pytest.mark.asyncio
    async def test_nested_transactional_methods(self):
        """중첩된 @Transactional 메서드"""

        @Configuration
        class NestedConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def nested_tx(self) -> MockTransaction:
                NestedConfig._id += 1
                return MockTransaction(id=NestedConfig._id)

        @Component
        class LowLevelService:
            tx: AsyncProxy[MockTransaction]

            @Transactional
            async def low_level_work(self) -> int:
                t = await self.tx.resolve()
                t.add("low_level")
                return t.id

        @Component
        class MidLevelService:
            tx: AsyncProxy[MockTransaction]
            low_level: LowLevelService

            @Transactional
            async def mid_level_work(self) -> tuple[int, int]:
                t = await self.tx.resolve()
                t.add("mid_level")
                low_id = await self.low_level.low_level_work()
                return t.id, low_id

        @Component
        class HighLevelService:
            tx: AsyncProxy[MockTransaction]
            mid_level: MidLevelService

            @Transactional
            async def high_level_work(self) -> tuple[int, int, int]:
                t = await self.tx.resolve()
                t.add("high_level")
                mid_id, low_id = await self.mid_level.mid_level_work()
                return t.id, mid_id, low_id

        manager = get_container_manager()
        register_factories_from_configuration(NestedConfig, manager)
        NestedConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(HighLevelService)

        high_id, mid_id, low_id = await service.high_level_work()

        # 모두 같은 트랜잭션
        assert high_id == mid_id == low_id == 1


# =============================================================================
# Tests: 격리 및 동시성
# =============================================================================


class TestTransactionalIsolation:
    """트랜잭션 격리 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_separate_calls_have_separate_transactions(self):
        """별도 호출은 별도 트랜잭션"""

        @Configuration
        class SepConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def sep_tx(self) -> MockTransaction:
                SepConfig._id += 1
                return MockTransaction(id=SepConfig._id)

        @Component
        class SepService:
            tx: AsyncProxy[MockTransaction]

            @Transactional
            async def work(self, data: str) -> tuple[int, list[str]]:
                t = await self.tx.resolve()
                t.add(data)
                return t.id, t.operations.copy()

        manager = get_container_manager()
        register_factories_from_configuration(SepConfig, manager)
        SepConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(SepService)

        id1, ops1 = await service.work("first")
        id2, ops2 = await service.work("second")

        # 다른 트랜잭션
        assert id1 == 1
        assert id2 == 2
        assert ops1 == ["first"]
        assert ops2 == ["second"]

    @pytest.mark.asyncio
    async def test_concurrent_transactions(self):
        """동시 트랜잭션 격리"""

        @Configuration
        class ConcConfig:
            _id: ClassVar[int] = 0
            _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

            @Factory(scope=ScopeEnum.CALL)
            async def conc_tx(self) -> MockTransaction:
                async with ConcConfig._lock:
                    ConcConfig._id += 1
                    return MockTransaction(id=ConcConfig._id)

        @Component
        class ConcService:
            tx: AsyncProxy[MockTransaction]

            @Transactional
            async def work(self, delay: float) -> int:
                t = await self.tx.resolve()
                await asyncio.sleep(delay)
                return t.id

        manager = get_container_manager()
        register_factories_from_configuration(ConcConfig, manager)
        ConcConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(ConcService)

        # 동시에 50개 트랜잭션
        results = await asyncio.gather(*[service.work(0.001) for _ in range(50)])

        # 모두 다른 트랜잭션
        assert len(set(results)) == 50


# =============================================================================
# Tests: 혼합 전파
# =============================================================================


class TestMixedPropagation:
    """혼합 전파 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_requires_new_in_required_chain(self):
        """REQUIRED 체인 중간에 REQUIRES_NEW"""

        @Configuration
        class MixConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def mix_tx(self) -> MockTransaction:
                MixConfig._id += 1
                return MockTransaction(id=MixConfig._id)

        @Component
        class AuditService:
            tx: AsyncProxy[MockTransaction]

            @RequiresNew  # 항상 새 트랜잭션
            async def audit(self, action: str) -> int:
                t = await self.tx.resolve()
                t.add(f"AUDIT:{action}")
                await t.commit()  # 별도 커밋
                return t.id

        @Component
        class BusinessService:
            tx: AsyncProxy[MockTransaction]
            audit: AuditService

            @Transactional  # REQUIRED
            async def do_business(self) -> tuple[int, int]:
                t = await self.tx.resolve()
                t.add("BUSINESS")
                audit_tx = await self.audit.audit("business_done")
                return t.id, audit_tx

        manager = get_container_manager()
        register_factories_from_configuration(MixConfig, manager)
        MixConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(BusinessService)

        business_tx, audit_tx = await service.do_business()

        # 다른 트랜잭션
        assert business_tx == 1
        assert audit_tx == 2

    @pytest.mark.asyncio
    async def test_complex_propagation_chain(self):
        """복잡한 전파 체인"""

        @Configuration
        class ComplexConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def complex_tx(self) -> MockTransaction:
                ComplexConfig._id += 1
                return MockTransaction(id=ComplexConfig._id)

        @Component
        class Level3Service:
            tx: AsyncProxy[MockTransaction]

            @Transactional  # REQUIRED - L2와 공유
            async def level3_work(self) -> int:
                t = await self.tx.resolve()
                t.add("L3")
                return t.id

        @Component
        class Level2Service:
            tx: AsyncProxy[MockTransaction]
            level3: Level3Service

            @RequiresNew  # 새 트랜잭션
            async def level2_work(self) -> tuple[int, int]:
                t = await self.tx.resolve()
                t.add("L2")
                l3_id = await self.level3.level3_work()
                return t.id, l3_id

        @Component
        class Level1Service:
            tx: AsyncProxy[MockTransaction]
            level2: Level2Service

            @Transactional  # REQUIRED
            async def level1_work(self) -> tuple[int, int, int]:
                t = await self.tx.resolve()
                t.add("L1")
                l2_id, l3_id = await self.level2.level2_work()
                return t.id, l2_id, l3_id

        manager = get_container_manager()
        register_factories_from_configuration(ComplexConfig, manager)
        ComplexConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(Level1Service)

        l1_id, l2_id, l3_id = await service.level1_work()

        # L1: 1, L2: 새 트랜잭션 2, L3: L2와 공유 2
        assert l1_id == 1
        assert l2_id == 2
        assert l3_id == 2


# =============================================================================
# Tests: 실제 사용 패턴
# =============================================================================


class TestRealWorldPatterns:
    """실제 사용 패턴 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_unit_of_work_pattern(self):
        """Unit of Work 패턴"""

        @Configuration
        class UowConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def uow_session(self) -> MockTransaction:
                UowConfig._id += 1
                return MockTransaction(id=UowConfig._id)

        @Component
        class ProductRepository:
            session: AsyncProxy[MockTransaction]

            async def save(self, product: str):
                s = await self.session.resolve()
                s.add(f"SAVE product:{product}")

        @Component
        class InventoryRepository:
            session: AsyncProxy[MockTransaction]

            async def update_stock(self, product: str, qty: int):
                s = await self.session.resolve()
                s.add(f"UPDATE inventory:{product}:{qty}")

        @Component
        class OrderFulfillmentService:
            product_repo: ProductRepository
            inventory_repo: InventoryRepository
            session: AsyncProxy[MockTransaction]

            @Transactional
            async def fulfill_order(
                self, product: str, qty: int
            ) -> tuple[list[str], bool]:
                await self.product_repo.save(product)
                await self.inventory_repo.update_stock(product, -qty)

                s = await self.session.resolve()
                s.add("COMMIT order")
                await s.commit()

                return s.operations, s.committed

        manager = get_container_manager()
        register_factories_from_configuration(UowConfig, manager)
        UowConfig._id = 0
        await manager.initialize()

        service = manager.get_instance(OrderFulfillmentService)

        operations, committed = await service.fulfill_order("laptop", 5)

        assert committed
        assert "SAVE product:laptop" in operations
        assert "UPDATE inventory:laptop:-5" in operations
        assert "COMMIT order" in operations

    @pytest.mark.asyncio
    async def test_saga_pattern_with_compensation(self):
        """Saga 패턴 (보상 트랜잭션)"""

        @Configuration
        class SagaConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.CALL)
            async def saga_tx(self) -> MockTransaction:
                SagaConfig._id += 1
                return MockTransaction(id=SagaConfig._id)

        compensations: list[str] = []

        @Component
        class PaymentService:
            tx: AsyncProxy[MockTransaction]

            @RequiresNew  # 별도 트랜잭션
            async def process_payment(self, amount: int) -> int:
                t = await self.tx.resolve()
                t.add(f"PAYMENT:{amount}")
                await t.commit()
                return t.id

            @RequiresNew
            async def refund_payment(self, amount: int) -> int:
                t = await self.tx.resolve()
                t.add(f"REFUND:{amount}")
                await t.commit()
                compensations.append(f"refund:{amount}")
                return t.id

        @Component
        class ShippingService:
            tx: AsyncProxy[MockTransaction]

            @RequiresNew
            async def create_shipment(self, order_id: str) -> int:
                t = await self.tx.resolve()
                t.add(f"SHIP:{order_id}")
                # 실패 시뮬레이션
                raise RuntimeError("Shipping failed")

        @Component
        class SagaOrchestrator:
            payment: PaymentService
            shipping: ShippingService

            @Transactional
            async def execute_order_saga(self, order_id: str, amount: int) -> str:
                # Step 1: Payment
                await self.payment.process_payment(amount)

                try:
                    # Step 2: Shipping
                    await self.shipping.create_shipment(order_id)
                except RuntimeError:
                    # Compensation: Refund
                    await self.payment.refund_payment(amount)
                    return "COMPENSATED"

                return "SUCCESS"

        manager = get_container_manager()
        register_factories_from_configuration(SagaConfig, manager)
        SagaConfig._id = 0
        compensations.clear()
        await manager.initialize()

        orchestrator = manager.get_instance(SagaOrchestrator)

        result = await orchestrator.execute_order_saga("order-123", 100)

        assert result == "COMPENSATED"
        assert "refund:100" in compensations
