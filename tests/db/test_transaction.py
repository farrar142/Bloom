"""트랜잭션 시스템 테스트"""

import pytest
from typing import Any

from bloom import Application, Component
from bloom.core.decorators import Factory, Handler
from bloom.core.container import HandlerContainer
from bloom.core.advice import MethodAdvice, MethodAdviceRegistry, InvocationContext
from bloom.core.advice.tracing.context import call_scope, get_call_depth

from bloom.db.transaction import (
    Propagation,
    TransactionError,
    TransactionRequiredError,
    TransactionNotAllowedError,
    TransactionalElement,
    Transactional,
    TransactionContext,
    TransactionAdvice,
    create_transaction_method_advice,
    get_current_transaction,
    has_active_transaction,
    get_transaction_depth,
    push_transaction,
    pop_transaction,
)


# =============================================================================
# Mock Session/SessionFactory
# =============================================================================


class MockSession:
    """테스트용 Mock 세션"""
    
    def __init__(self, session_id: int):
        self.session_id = session_id
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.operations: list[str] = []
    
    def add(self, entity: Any) -> Any:
        self.operations.append(f"add:{entity}")
        return entity
    
    def flush(self) -> None:
        self.operations.append("flush")
    
    def commit(self) -> None:
        self.operations.append("commit")
        self.committed = True
    
    def rollback(self) -> None:
        self.operations.append("rollback")
        self.rolled_back = True
    
    def close(self) -> None:
        self.operations.append("close")
        self.closed = True
    
    # Async 버전
    async def commit_async(self) -> None:
        self.commit()
    
    async def rollback_async(self) -> None:
        self.rollback()
    
    async def close_async(self) -> None:
        self.close()


class MockAsyncSession(MockSession):
    """테스트용 Mock 비동기 세션"""
    
    async def commit(self) -> None:
        self.operations.append("commit")
        self.committed = True
    
    async def rollback(self) -> None:
        self.operations.append("rollback")
        self.rolled_back = True
    
    async def close(self) -> None:
        self.operations.append("close")
        self.closed = True


class MockSessionFactory:
    """테스트용 Mock 세션 팩토리"""
    
    def __init__(self):
        self.session_counter = 0
        self.created_sessions: list[MockSession] = []
    
    def create(self) -> MockSession:
        self.session_counter += 1
        session = MockSession(self.session_counter)
        self.created_sessions.append(session)
        return session
    
    async def create_async(self) -> MockAsyncSession:
        self.session_counter += 1
        session = MockAsyncSession(self.session_counter)
        self.created_sessions.append(session)
        return session


# =============================================================================
# TransactionalElement 테스트
# =============================================================================


class TestTransactionalElement:
    """TransactionalElement 테스트"""
    
    def test_default_propagation(self):
        """기본 전파 옵션은 REQUIRED"""
        element = TransactionalElement()
        assert element.propagation == Propagation.REQUIRED
        assert element.read_only is False
    
    def test_custom_propagation(self):
        """커스텀 전파 옵션"""
        element = TransactionalElement(
            propagation=Propagation.REQUIRES_NEW,
            read_only=True,
        )
        assert element.propagation == Propagation.REQUIRES_NEW
        assert element.read_only is True


class TestTransactionalDecorator:
    """@Transactional 데코레이터 테스트"""
    
    def test_decorator_adds_element(self):
        """데코레이터가 TransactionalElement를 추가"""
        @Transactional()
        def my_method():
            pass
        
        container = HandlerContainer.get_or_create(my_method)
        assert container.has_element(TransactionalElement)
    
    def test_decorator_with_options(self):
        """데코레이터 옵션이 Element에 반영"""
        @Transactional(propagation=Propagation.REQUIRES_NEW, read_only=True)
        def my_method():
            pass
        
        container = HandlerContainer.get_or_create(my_method)
        
        element = None
        for e in container.elements:
            if isinstance(e, TransactionalElement):
                element = e
                break
        
        assert element is not None
        assert element.propagation == Propagation.REQUIRES_NEW
        assert element.read_only is True


# =============================================================================
# TransactionContext 테스트
# =============================================================================


class TestTransactionContext:
    """TransactionContext 테스트"""
    
    def setup_method(self):
        """각 테스트 전 컨텍스트 초기화"""
        # 스택 비우기
        while pop_transaction():
            pass
    
    def test_no_active_transaction_initially(self):
        """초기에는 활성 트랜잭션 없음"""
        assert get_current_transaction() is None
        assert has_active_transaction() is False
        assert get_transaction_depth() == 0
    
    def test_push_pop_transaction(self):
        """트랜잭션 스택 push/pop"""
        session = MockSession(1)
        ctx = TransactionContext(session=session, depth=1)
        
        push_transaction(ctx)
        
        assert get_current_transaction() is ctx
        assert has_active_transaction() is True
        assert get_transaction_depth() == 1
        
        popped = pop_transaction()
        
        assert popped is ctx
        assert get_current_transaction() is None
        assert has_active_transaction() is False
    
    def test_nested_transactions(self):
        """중첩 트랜잭션 스택"""
        session1 = MockSession(1)
        session2 = MockSession(2)
        
        ctx1 = TransactionContext(session=session1, depth=1)
        ctx2 = TransactionContext(session=session2, depth=2)
        
        push_transaction(ctx1)
        push_transaction(ctx2)
        
        assert get_transaction_depth() == 2
        assert get_current_transaction() is ctx2
        
        pop_transaction()
        assert get_current_transaction() is ctx1
        
        pop_transaction()
        assert get_current_transaction() is None
    
    def test_committed_transaction_not_active(self):
        """커밋된 트랜잭션은 활성 상태가 아님"""
        session = MockSession(1)
        ctx = TransactionContext(session=session, depth=1)
        ctx.committed = True
        
        push_transaction(ctx)
        
        assert get_current_transaction() is ctx
        assert has_active_transaction() is False  # committed이므로


# =============================================================================
# TransactionAdvice 테스트 (동기)
# =============================================================================


class TestTransactionAdviceSync:
    """TransactionAdvice 동기 테스트"""
    
    def setup_method(self):
        """각 테스트 전 컨텍스트 초기화"""
        while pop_transaction():
            pass
        self.factory = MockSessionFactory()
        self.advice = TransactionAdvice(self.factory)
    
    def _make_container(
        self,
        propagation: Propagation = Propagation.REQUIRED,
        read_only: bool = False,
    ) -> HandlerContainer:
        """테스트용 컨테이너 생성"""
        def dummy():
            pass
        
        container = HandlerContainer.get_or_create(dummy)
        container.add_elements(TransactionalElement(
            propagation=propagation,
            read_only=read_only,
        ))
        return container
    
    def test_required_starts_new_transaction(self):
        """REQUIRED: 트랜잭션 없으면 새로 시작"""
        container = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            tx_ctx, is_new = self.advice.begin_transaction_sync(container, 1)
            
            assert tx_ctx is not None
            assert is_new is True
            assert has_active_transaction() is True
            
            self.advice.commit_transaction_sync(tx_ctx)
        
        assert len(self.factory.created_sessions) == 1
        session = self.factory.created_sessions[0]
        assert session.committed is True
        assert session.closed is True
    
    def test_required_joins_existing_transaction(self):
        """REQUIRED: 기존 트랜잭션 있으면 합류"""
        container = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            # 첫 번째 트랜잭션 시작
            tx_ctx1, is_new1 = self.advice.begin_transaction_sync(container, 1)
            assert is_new1 is True
            
            # 두 번째는 합류
            tx_ctx2, is_new2 = self.advice.begin_transaction_sync(container, 2)
            assert is_new2 is False
            assert tx_ctx2 is tx_ctx1  # 같은 트랜잭션
            
            self.advice.commit_transaction_sync(tx_ctx1)
        
        # 세션은 1개만 생성
        assert len(self.factory.created_sessions) == 1
    
    def test_requires_new_always_starts_new(self):
        """REQUIRES_NEW: 항상 새 트랜잭션 시작"""
        container_required = self._make_container(Propagation.REQUIRED)
        container_requires_new = self._make_container(Propagation.REQUIRES_NEW)
        
        with call_scope():
            # 첫 번째 트랜잭션
            tx_ctx1, _ = self.advice.begin_transaction_sync(container_required, 1)
            
            # REQUIRES_NEW는 새 트랜잭션
            tx_ctx2, is_new = self.advice.begin_transaction_sync(
                container_requires_new, 2
            )
            assert is_new is True
            assert tx_ctx2 is not tx_ctx1
            assert get_transaction_depth() == 2
            
            self.advice.commit_transaction_sync(tx_ctx2)
            self.advice.commit_transaction_sync(tx_ctx1)
        
        # 세션 2개 생성
        assert len(self.factory.created_sessions) == 2
    
    def test_supports_without_existing(self):
        """SUPPORTS: 트랜잭션 없으면 없이 실행"""
        container = self._make_container(Propagation.SUPPORTS)
        
        with call_scope():
            tx_ctx, is_new = self.advice.begin_transaction_sync(container, 1)
            
            assert tx_ctx is None
            assert is_new is False
        
        assert len(self.factory.created_sessions) == 0
    
    def test_supports_with_existing(self):
        """SUPPORTS: 기존 트랜잭션 있으면 합류"""
        container_required = self._make_container(Propagation.REQUIRED)
        container_supports = self._make_container(Propagation.SUPPORTS)
        
        with call_scope():
            tx_ctx1, _ = self.advice.begin_transaction_sync(container_required, 1)
            tx_ctx2, is_new = self.advice.begin_transaction_sync(container_supports, 2)
            
            assert tx_ctx2 is tx_ctx1
            assert is_new is False
            
            self.advice.commit_transaction_sync(tx_ctx1)
    
    def test_mandatory_without_existing_raises(self):
        """MANDATORY: 트랜잭션 없으면 예외"""
        container = self._make_container(Propagation.MANDATORY)
        
        with call_scope():
            with pytest.raises(TransactionRequiredError):
                self.advice.begin_transaction_sync(container, 1)
    
    def test_mandatory_with_existing(self):
        """MANDATORY: 기존 트랜잭션 있으면 합류"""
        container_required = self._make_container(Propagation.REQUIRED)
        container_mandatory = self._make_container(Propagation.MANDATORY)
        
        with call_scope():
            tx_ctx1, _ = self.advice.begin_transaction_sync(container_required, 1)
            tx_ctx2, is_new = self.advice.begin_transaction_sync(container_mandatory, 2)
            
            assert tx_ctx2 is tx_ctx1
            assert is_new is False
            
            self.advice.commit_transaction_sync(tx_ctx1)
    
    def test_never_with_existing_raises(self):
        """NEVER: 트랜잭션 있으면 예외"""
        container_required = self._make_container(Propagation.REQUIRED)
        container_never = self._make_container(Propagation.NEVER)
        
        with call_scope():
            tx_ctx1, _ = self.advice.begin_transaction_sync(container_required, 1)
            
            with pytest.raises(TransactionNotAllowedError):
                self.advice.begin_transaction_sync(container_never, 2)
            
            self.advice.commit_transaction_sync(tx_ctx1)
    
    def test_never_without_existing(self):
        """NEVER: 트랜잭션 없으면 정상 실행"""
        container = self._make_container(Propagation.NEVER)
        
        with call_scope():
            tx_ctx, is_new = self.advice.begin_transaction_sync(container, 1)
            
            assert tx_ctx is None
            assert is_new is False
    
    def test_rollback_on_error(self):
        """에러 발생 시 롤백"""
        container = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            tx_ctx, _ = self.advice.begin_transaction_sync(container, 1)
            
            # 에러 발생 시뮬레이션
            self.advice.rollback_transaction_sync(tx_ctx)
        
        session = self.factory.created_sessions[0]
        assert session.rolled_back is True
        assert session.committed is False
        assert session.closed is True


# =============================================================================
# TransactionAdvice 테스트 (비동기)
# =============================================================================


class TestTransactionAdviceAsync:
    """TransactionAdvice 비동기 테스트"""
    
    def setup_method(self):
        while pop_transaction():
            pass
        self.factory = MockSessionFactory()
        self.advice = TransactionAdvice(self.factory)
    
    def _make_container(
        self,
        propagation: Propagation = Propagation.REQUIRED,
    ) -> HandlerContainer:
        def dummy():
            pass
        
        container = HandlerContainer.get_or_create(dummy)
        container.add_elements(TransactionalElement(propagation=propagation))
        return container
    
    @pytest.mark.asyncio
    async def test_required_starts_new_transaction_async(self):
        """REQUIRED: 비동기 트랜잭션 시작"""
        container = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            tx_ctx, is_new = await self.advice.begin_transaction_async(container, 1)
            
            assert tx_ctx is not None
            assert is_new is True
            
            await self.advice.commit_transaction_async(tx_ctx)
        
        assert len(self.factory.created_sessions) == 1
    
    @pytest.mark.asyncio
    async def test_requires_new_async(self):
        """REQUIRES_NEW: 비동기에서 항상 새 트랜잭션"""
        container_required = self._make_container(Propagation.REQUIRED)
        container_requires_new = self._make_container(Propagation.REQUIRES_NEW)
        
        with call_scope():
            tx_ctx1, _ = await self.advice.begin_transaction_async(container_required, 1)
            tx_ctx2, is_new = await self.advice.begin_transaction_async(
                container_requires_new, 2
            )
            
            assert is_new is True
            assert tx_ctx2 is not tx_ctx1
            
            await self.advice.commit_transaction_async(tx_ctx2)
            await self.advice.commit_transaction_async(tx_ctx1)
        
        assert len(self.factory.created_sessions) == 2


# =============================================================================
# MethodAdvice 통합 테스트
# =============================================================================


class TestTransactionMethodAdvice:
    """TransactionMethodAdvice 통합 테스트"""
    
    def setup_method(self):
        while pop_transaction():
            pass
    
    def test_create_method_advice(self):
        """MethodAdvice 생성"""
        factory = MockSessionFactory()
        advice = create_transaction_method_advice(factory)
        
        # supports 테스트
        @Transactional()
        def transactional_method():
            pass
        
        def normal_method():
            pass
        
        tx_container = HandlerContainer.get_or_create(transactional_method)
        normal_container = HandlerContainer.get_or_create(normal_method)
        
        assert advice.supports(tx_container) is True
        assert advice.supports(normal_container) is False
    
    def test_sync_before_after(self):
        """동기 before/after 호출"""
        factory = MockSessionFactory()
        advice = create_transaction_method_advice(factory)
        
        @Transactional()
        def my_method():
            pass
        
        container = HandlerContainer.get_or_create(my_method)
        context = InvocationContext(
            container=container,
            instance=None,
            args=(),
            kwargs={},
        )
        
        with call_scope():
            advice.before_sync(context)
            
            assert has_active_transaction() is True
            tx_ctx = context.get_attribute("__tx_ctx__")
            assert tx_ctx is not None
            
            result = advice.after_sync(context, "result")
            
            assert result == "result"
        
        session = factory.created_sessions[0]
        assert session.committed is True
    
    def test_sync_on_error(self):
        """동기 에러 시 롤백"""
        factory = MockSessionFactory()
        advice = create_transaction_method_advice(factory)
        
        @Transactional()
        def my_method():
            pass
        
        container = HandlerContainer.get_or_create(my_method)
        context = InvocationContext(
            container=container,
            instance=None,
            args=(),
            kwargs={},
        )
        
        with call_scope():
            advice.before_sync(context)
            
            with pytest.raises(ValueError):
                advice.on_error_sync(context, ValueError("test error"))
        
        session = factory.created_sessions[0]
        assert session.rolled_back is True
        assert session.committed is False
    
    @pytest.mark.asyncio
    async def test_async_before_after(self):
        """비동기 before/after 호출"""
        factory = MockSessionFactory()
        advice = create_transaction_method_advice(factory)
        
        @Transactional()
        async def my_method():
            pass
        
        container = HandlerContainer.get_or_create(my_method)
        context = InvocationContext(
            container=container,
            instance=None,
            args=(),
            kwargs={},
        )
        
        with call_scope():
            await advice.before(context)
            
            assert has_active_transaction() is True
            
            result = await advice.after(context, "async_result")
            
            assert result == "async_result"
        
        session = factory.created_sessions[0]
        assert session.committed is True


# =============================================================================
# 전파 시나리오 테스트
# =============================================================================


class TestPropagationScenarios:
    """실제 사용 시나리오 테스트"""
    
    def setup_method(self):
        while pop_transaction():
            pass
        self.factory = MockSessionFactory()
        self.advice = TransactionAdvice(self.factory)
    
    def _make_container(self, propagation: Propagation) -> HandlerContainer:
        def dummy():
            pass
        container = HandlerContainer.get_or_create(dummy)
        container.add_elements(TransactionalElement(propagation=propagation))
        return container
    
    def test_nested_service_calls(self):
        """중첩 서비스 호출 시나리오
        
        UserService.createUser() -> ProfileService.createProfile()
        둘 다 REQUIRED이면 같은 트랜잭션 공유
        """
        container1 = self._make_container(Propagation.REQUIRED)
        container2 = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            # UserService.createUser() 시작
            tx1, is_new1 = self.advice.begin_transaction_sync(container1, 1)
            assert is_new1 is True
            session1 = tx1.session
            
            # ProfileService.createProfile() - 합류
            tx2, is_new2 = self.advice.begin_transaction_sync(container2, 2)
            assert is_new2 is False
            assert tx2 is tx1  # 같은 트랜잭션
            
            # ProfileService 종료 (커밋하지 않음 - 합류했으므로)
            # UserService 종료
            self.advice.commit_transaction_sync(tx1)
        
        # 세션 1개만 생성, 커밋 1번
        assert len(self.factory.created_sessions) == 1
        assert session1.committed is True
    
    def test_audit_log_with_requires_new(self):
        """감사 로그는 별도 트랜잭션
        
        OrderService.createOrder() -> AuditService.log()
        AuditService는 REQUIRES_NEW로 별도 커밋
        """
        container_order = self._make_container(Propagation.REQUIRED)
        container_audit = self._make_container(Propagation.REQUIRES_NEW)
        
        with call_scope():
            # OrderService.createOrder() 시작
            tx_order, _ = self.advice.begin_transaction_sync(container_order, 1)
            session_order = tx_order.session
            
            # AuditService.log() - 별도 트랜잭션
            tx_audit, is_new = self.advice.begin_transaction_sync(container_audit, 2)
            assert is_new is True
            assert tx_audit is not tx_order
            session_audit = tx_audit.session
            
            # Audit 먼저 커밋
            self.advice.commit_transaction_sync(tx_audit)
            assert session_audit.committed is True
            
            # Order 트랜잭션 롤백 시뮬레이션
            self.advice.rollback_transaction_sync(tx_order)
            assert session_order.rolled_back is True
        
        # 세션 2개, Audit은 커밋됨 (Order 롤백과 무관)
        assert len(self.factory.created_sessions) == 2
        assert session_audit.committed is True
        assert session_order.rolled_back is True


# =============================================================================
# 엣지케이스 테스트
# =============================================================================


class TestTransactionEdgeCases:
    """트랜잭션 엣지케이스 테스트"""
    
    def setup_method(self):
        while pop_transaction():
            pass
        self.factory = MockSessionFactory()
        self.advice = TransactionAdvice(self.factory)
    
    def _make_container(self, propagation: Propagation) -> HandlerContainer:
        def dummy():
            pass
        container = HandlerContainer.get_or_create(dummy)
        container.add_elements(TransactionalElement(propagation=propagation))
        return container
    
    def test_double_commit_ignored(self):
        """이미 커밋된 트랜잭션에 다시 커밋 시도 - 무시됨"""
        container = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            tx_ctx, _ = self.advice.begin_transaction_sync(container, 1)
            
            # 첫 번째 커밋
            self.advice.commit_transaction_sync(tx_ctx)
            assert tx_ctx.committed is True
            
            # 두 번째 커밋 시도 - 무시됨 (예외 없음)
            self.advice.commit_transaction_sync(tx_ctx)
        
        session = self.factory.created_sessions[0]
        # commit은 1번만 호출됨
        assert session.operations.count("commit") == 1
    
    def test_double_rollback_ignored(self):
        """이미 롤백된 트랜잭션에 다시 롤백 시도 - 무시됨"""
        container = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            tx_ctx, _ = self.advice.begin_transaction_sync(container, 1)
            
            # 첫 번째 롤백
            self.advice.rollback_transaction_sync(tx_ctx)
            assert tx_ctx.rolled_back is True
            
            # 두 번째 롤백 시도 - 무시됨
            self.advice.rollback_transaction_sync(tx_ctx)
        
        session = self.factory.created_sessions[0]
        assert session.operations.count("rollback") == 1
    
    def test_commit_after_rollback_ignored(self):
        """롤백 후 커밋 시도 - 무시됨"""
        container = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            tx_ctx, _ = self.advice.begin_transaction_sync(container, 1)
            
            self.advice.rollback_transaction_sync(tx_ctx)
            self.advice.commit_transaction_sync(tx_ctx)
        
        session = self.factory.created_sessions[0]
        assert session.rolled_back is True
        assert session.committed is False
    
    def test_rollback_after_commit_ignored(self):
        """커밋 후 롤백 시도 - 무시됨"""
        container = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            tx_ctx, _ = self.advice.begin_transaction_sync(container, 1)
            
            self.advice.commit_transaction_sync(tx_ctx)
            self.advice.rollback_transaction_sync(tx_ctx)
        
        session = self.factory.created_sessions[0]
        assert session.committed is True
        assert session.rolled_back is False
    
    def test_empty_transaction_stack_pop(self):
        """빈 스택에서 pop - None 반환"""
        result = pop_transaction()
        assert result is None
    
    def test_deeply_nested_transactions(self):
        """깊이 중첩된 트랜잭션 (5레벨)"""
        containers = [self._make_container(Propagation.REQUIRED) for _ in range(5)]
        
        with call_scope():
            txs = []
            # 5개의 REQUIRED 트랜잭션 시작 - 모두 첫 번째에 합류
            for i, container in enumerate(containers):
                tx, is_new = self.advice.begin_transaction_sync(container, i + 1)
                txs.append((tx, is_new))
            
            # 첫 번째만 새로 시작, 나머지는 합류
            assert txs[0][1] is True  # is_new
            for i in range(1, 5):
                assert txs[i][1] is False
                assert txs[i][0] is txs[0][0]  # 같은 트랜잭션
            
            # 커밋
            self.advice.commit_transaction_sync(txs[0][0])
        
        assert len(self.factory.created_sessions) == 1
    
    def test_deeply_nested_requires_new(self):
        """깊이 중첩된 REQUIRES_NEW (각각 별도 트랜잭션)"""
        containers = [self._make_container(Propagation.REQUIRES_NEW) for _ in range(3)]
        
        with call_scope():
            txs = []
            for i, container in enumerate(containers):
                tx, is_new = self.advice.begin_transaction_sync(container, i + 1)
                txs.append(tx)
                assert is_new is True
            
            assert get_transaction_depth() == 3
            
            # 역순으로 커밋 (내부 → 외부)
            for tx in reversed(txs):
                self.advice.commit_transaction_sync(tx)
        
        assert len(self.factory.created_sessions) == 3
        for session in self.factory.created_sessions:
            assert session.committed is True
    
    def test_mixed_propagation_chain(self):
        """혼합 전파 체인: REQUIRED -> REQUIRES_NEW -> REQUIRED"""
        container_required1 = self._make_container(Propagation.REQUIRED)
        container_requires_new = self._make_container(Propagation.REQUIRES_NEW)
        container_required2 = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            # 1. REQUIRED - 새 트랜잭션
            tx1, is_new1 = self.advice.begin_transaction_sync(container_required1, 1)
            assert is_new1 is True
            
            # 2. REQUIRES_NEW - 새 트랜잭션
            tx2, is_new2 = self.advice.begin_transaction_sync(container_requires_new, 2)
            assert is_new2 is True
            assert tx2 is not tx1
            
            # 3. REQUIRED - tx2에 합류 (현재 활성 트랜잭션)
            tx3, is_new3 = self.advice.begin_transaction_sync(container_required2, 3)
            assert is_new3 is False
            assert tx3 is tx2  # REQUIRES_NEW 트랜잭션에 합류
            
            # 역순으로 정리
            self.advice.commit_transaction_sync(tx2)
            self.advice.commit_transaction_sync(tx1)
        
        assert len(self.factory.created_sessions) == 2
    
    def test_not_supported_suspends_transaction(self):
        """NOT_SUPPORTED: 기존 트랜잭션 일시 중단"""
        container_required = self._make_container(Propagation.REQUIRED)
        container_not_supported = self._make_container(Propagation.NOT_SUPPORTED)
        
        with call_scope():
            tx1, _ = self.advice.begin_transaction_sync(container_required, 1)
            assert has_active_transaction() is True
            
            # NOT_SUPPORTED - 트랜잭션 없이 실행
            tx2, is_new = self.advice.begin_transaction_sync(container_not_supported, 2)
            assert tx2 is None
            assert is_new is False
            # 기존 트랜잭션은 여전히 스택에 있음
            assert has_active_transaction() is True
            
            self.advice.commit_transaction_sync(tx1)
    
    def test_supports_propagation_scenarios(self):
        """SUPPORTS 다양한 시나리오"""
        container_supports = self._make_container(Propagation.SUPPORTS)
        container_required = self._make_container(Propagation.REQUIRED)
        
        # 시나리오 1: 트랜잭션 없이 시작
        with call_scope():
            tx, is_new = self.advice.begin_transaction_sync(container_supports, 1)
            assert tx is None
            assert is_new is False
        
        # 시나리오 2: 기존 트랜잭션에 합류
        with call_scope():
            tx1, _ = self.advice.begin_transaction_sync(container_required, 1)
            tx2, is_new = self.advice.begin_transaction_sync(container_supports, 2)
            
            assert tx2 is tx1
            assert is_new is False
            
            self.advice.commit_transaction_sync(tx1)
    
    def test_transaction_context_isolation(self):
        """ContextVar 격리 - 각 call_scope는 독립적"""
        container = self._make_container(Propagation.REQUIRED)
        
        # 첫 번째 call_scope
        with call_scope():
            tx1, _ = self.advice.begin_transaction_sync(container, 1)
            assert has_active_transaction() is True
            self.advice.commit_transaction_sync(tx1)
        
        # call_scope 종료 후
        assert has_active_transaction() is False
        
        # 두 번째 call_scope - 새로운 트랜잭션
        with call_scope():
            tx2, is_new = self.advice.begin_transaction_sync(container, 1)
            assert is_new is True  # 새 트랜잭션
            assert tx2 is not tx1
            self.advice.commit_transaction_sync(tx2)
        
        assert len(self.factory.created_sessions) == 2


class TestTransactionMethodAdviceEdgeCases:
    """TransactionMethodAdvice 엣지케이스"""
    
    def setup_method(self):
        while pop_transaction():
            pass
    
    def test_joined_transaction_not_committed_twice(self):
        """합류한 트랜잭션은 커밋하지 않음"""
        factory = MockSessionFactory()
        advice = create_transaction_method_advice(factory)
        
        @Transactional()
        def outer_method():
            pass
        
        @Transactional()
        def inner_method():
            pass
        
        outer_container = HandlerContainer.get_or_create(outer_method)
        inner_container = HandlerContainer.get_or_create(inner_method)
        
        outer_context = InvocationContext(
            container=outer_container,
            instance=None,
            args=(),
            kwargs={},
        )
        inner_context = InvocationContext(
            container=inner_container,
            instance=None,
            args=(),
            kwargs={},
        )
        
        with call_scope():
            # outer 시작
            advice.before_sync(outer_context)
            assert outer_context.get_attribute("__tx_is_new__") is True
            
            # inner 시작 (합류)
            advice.before_sync(inner_context)
            assert inner_context.get_attribute("__tx_is_new__") is False
            
            # inner 종료 - 커밋하지 않음
            advice.after_sync(inner_context, None)
            
            # outer 종료 - 커밋
            advice.after_sync(outer_context, None)
        
        session = factory.created_sessions[0]
        # commit은 1번만
        assert session.operations.count("commit") == 1
    
    def test_inner_error_does_not_rollback_if_joined(self):
        """합류한 트랜잭션에서 에러 - 롤백하지 않음 (외부에서 처리)"""
        factory = MockSessionFactory()
        advice = create_transaction_method_advice(factory)
        
        @Transactional()
        def outer_method():
            pass
        
        @Transactional()
        def inner_method():
            pass
        
        outer_container = HandlerContainer.get_or_create(outer_method)
        inner_container = HandlerContainer.get_or_create(inner_method)
        
        outer_context = InvocationContext(
            container=outer_container,
            instance=None,
            args=(),
            kwargs={},
        )
        inner_context = InvocationContext(
            container=inner_container,
            instance=None,
            args=(),
            kwargs={},
        )
        
        with call_scope():
            # outer 시작
            advice.before_sync(outer_context)
            
            # inner 시작 (합류)
            advice.before_sync(inner_context)
            
            # inner에서 에러 발생 - 합류했으므로 롤백 안 함
            with pytest.raises(ValueError):
                advice.on_error_sync(inner_context, ValueError("inner error"))
            
            # outer에서 에러 처리 - 롤백
            with pytest.raises(ValueError):
                advice.on_error_sync(outer_context, ValueError("propagated"))
        
        session = factory.created_sessions[0]
        assert session.rolled_back is True
        assert session.operations.count("rollback") == 1


class TestAsyncTransactionEdgeCases:
    """비동기 트랜잭션 엣지케이스"""
    
    def setup_method(self):
        while pop_transaction():
            pass
        self.factory = MockSessionFactory()
        self.advice = TransactionAdvice(self.factory)
    
    def _make_container(self, propagation: Propagation) -> HandlerContainer:
        def dummy():
            pass
        container = HandlerContainer.get_or_create(dummy)
        container.add_elements(TransactionalElement(propagation=propagation))
        return container
    
    @pytest.mark.asyncio
    async def test_async_mandatory_without_existing_raises(self):
        """비동기 MANDATORY: 트랜잭션 없으면 예외"""
        container = self._make_container(Propagation.MANDATORY)
        
        with call_scope():
            with pytest.raises(TransactionRequiredError):
                await self.advice.begin_transaction_async(container, 1)
    
    @pytest.mark.asyncio
    async def test_async_never_with_existing_raises(self):
        """비동기 NEVER: 트랜잭션 있으면 예외"""
        container_required = self._make_container(Propagation.REQUIRED)
        container_never = self._make_container(Propagation.NEVER)
        
        with call_scope():
            tx, _ = await self.advice.begin_transaction_async(container_required, 1)
            
            with pytest.raises(TransactionNotAllowedError):
                await self.advice.begin_transaction_async(container_never, 2)
            
            await self.advice.commit_transaction_async(tx)
    
    @pytest.mark.asyncio
    async def test_async_double_commit_ignored(self):
        """비동기 이중 커밋 - 무시됨"""
        container = self._make_container(Propagation.REQUIRED)
        
        with call_scope():
            tx, _ = await self.advice.begin_transaction_async(container, 1)
            
            await self.advice.commit_transaction_async(tx)
            await self.advice.commit_transaction_async(tx)
        
        session = self.factory.created_sessions[0]
        assert session.operations.count("commit") == 1
    
    @pytest.mark.asyncio
    async def test_async_mixed_propagation(self):
        """비동기 혼합 전파"""
        container_required = self._make_container(Propagation.REQUIRED)
        container_requires_new = self._make_container(Propagation.REQUIRES_NEW)
        container_supports = self._make_container(Propagation.SUPPORTS)
        
        with call_scope():
            tx1, _ = await self.advice.begin_transaction_async(container_required, 1)
            tx2, is_new2 = await self.advice.begin_transaction_async(container_requires_new, 2)
            tx3, is_new3 = await self.advice.begin_transaction_async(container_supports, 3)
            
            assert is_new2 is True
            assert tx2 is not tx1
            assert is_new3 is False
            assert tx3 is tx2  # REQUIRES_NEW에 합류
            
            await self.advice.commit_transaction_async(tx2)
            await self.advice.commit_transaction_async(tx1)
        
        assert len(self.factory.created_sessions) == 2
