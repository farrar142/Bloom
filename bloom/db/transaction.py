"""트랜잭션 관리 시스템

콜스택 기반 트랜잭션 전파를 지원합니다.
ContextVar를 사용하여 스레드/코루틴 안전합니다.

사용법:
    @Component
    class UserService:
        repository: UserRepository

        @Transactional
        def create_user(self, name: str) -> User:
            # 트랜잭션 내에서 실행
            user = self.repository.save(User(name=name))
            return user

        @Transactional
        def create_user_with_profile(self, name: str) -> User:
            user = self.create_user(name)  # 기존 트랜잭션에 합류
            self.profile_repo.save(Profile(user_id=user.id))
            return user

        @Transactional(propagation=Propagation.REQUIRES_NEW)
        def audit_log(self, message: str) -> None:
            # 항상 새 트랜잭션 시작
            self.audit_repo.save(AuditLog(message=message))
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TYPE_CHECKING

from bloom.core.container import HandlerContainer
from bloom.core.container.element import Element

if TYPE_CHECKING:
    from .session import Session, AsyncSession


class Propagation(Enum):
    """트랜잭션 전파 옵션

    - REQUIRED: 기존 트랜잭션 있으면 합류, 없으면 새로 시작 (기본값)
    - REQUIRES_NEW: 항상 새 트랜잭션 시작 (기존 트랜잭션 일시 중단)
    - SUPPORTS: 기존 트랜잭션 있으면 합류, 없으면 트랜잭션 없이 실행
    - NOT_SUPPORTED: 트랜잭션 없이 실행 (기존 트랜잭션 일시 중단)
    - MANDATORY: 기존 트랜잭션 필수 (없으면 예외)
    - NEVER: 트랜잭션 없어야 함 (있으면 예외)
    """

    REQUIRED = "required"
    REQUIRES_NEW = "requires_new"
    SUPPORTS = "supports"
    NOT_SUPPORTED = "not_supported"
    MANDATORY = "mandatory"
    NEVER = "never"


class TransactionError(Exception):
    """트랜잭션 관련 예외"""

    pass


class TransactionRequiredError(TransactionError):
    """트랜잭션이 필요한데 없을 때"""

    pass


class TransactionNotAllowedError(TransactionError):
    """트랜잭션이 있으면 안 되는데 있을 때"""

    pass


# =============================================================================
# Element & Decorator
# =============================================================================


class TransactionalElement(Element):
    """트랜잭션 적용 마커 Element"""

    def __init__(
        self,
        propagation: Propagation = Propagation.REQUIRED,
        read_only: bool = False,
    ):
        super().__init__()
        self.metadata["propagation"] = propagation
        self.metadata["read_only"] = read_only

    @property
    def propagation(self) -> Propagation:
        return self.metadata.get("propagation", Propagation.REQUIRED)

    @property
    def read_only(self) -> bool:
        return self.metadata.get("read_only", False)


def Transactional(
    propagation: Propagation = Propagation.REQUIRED,
    read_only: bool = False,
) -> Callable[[Callable], Callable]:
    """트랜잭션 데코레이터

    메서드에 적용하면 TransactionalElement가 추가되어
    TransactionAdvice가 트랜잭션을 관리합니다.

    Args:
        propagation: 트랜잭션 전파 옵션
        read_only: 읽기 전용 여부 (최적화 힌트)

    Example:
        @Component
        class UserService:
            @Transactional
            def create_user(self, name: str) -> User:
                return self.repository.save(User(name=name))

            @Transactional(propagation=Propagation.REQUIRES_NEW)
            def audit_log(self, message: str) -> None:
                self.audit_repo.save(AuditLog(message=message))
    """

    def decorator(method: Callable) -> Callable:
        container = HandlerContainer.get_or_create(method)
        container.add_elements(
            TransactionalElement(
                propagation=propagation,
                read_only=read_only,
            )
        )
        return method

    return decorator


# =============================================================================
# Transaction Context (ContextVar 기반)
# =============================================================================


@dataclass
class TransactionContext:
    """현재 트랜잭션 컨텍스트

    콜스택 깊이별로 트랜잭션 상태를 추적합니다.
    """

    session: "Session | AsyncSession"
    """현재 세션"""

    depth: int
    """트랜잭션이 시작된 콜스택 깊이"""

    read_only: bool = False
    """읽기 전용 여부"""

    committed: bool = False
    """커밋 완료 여부"""

    rolled_back: bool = False
    """롤백 완료 여부"""

    savepoint: str | None = None
    """REQUIRES_NEW에서 사용하는 savepoint 이름"""


# 현재 트랜잭션 스택 (중첩 트랜잭션 지원)
_transaction_stack: ContextVar[list[TransactionContext]] = ContextVar(
    "bloom_transaction_stack", default=[]
)


def get_current_transaction() -> TransactionContext | None:
    """현재 활성 트랜잭션 반환"""
    stack = _transaction_stack.get()
    return stack[-1] if stack else None


def has_active_transaction() -> bool:
    """활성 트랜잭션 존재 여부"""
    tx = get_current_transaction()
    return tx is not None and not tx.committed and not tx.rolled_back


def push_transaction(ctx: TransactionContext) -> None:
    """트랜잭션 스택에 추가"""
    stack = _transaction_stack.get()
    new_stack = stack.copy()
    new_stack.append(ctx)
    _transaction_stack.set(new_stack)


def pop_transaction() -> TransactionContext | None:
    """트랜잭션 스택에서 제거"""
    stack = _transaction_stack.get()
    if not stack:
        return None

    new_stack = stack.copy()
    ctx = new_stack.pop()
    _transaction_stack.set(new_stack)
    return ctx


def get_transaction_depth() -> int:
    """현재 트랜잭션 스택 깊이"""
    return len(_transaction_stack.get())


# =============================================================================
# Transaction Advice
# =============================================================================


class TransactionAdvice:
    """트랜잭션 어드바이스

    @Transactional 데코레이터가 적용된 메서드에 트랜잭션을 관리합니다.
    콜스택 기반으로 트랜잭션 전파를 지원합니다.

    사용법:
        @Component
        class TransactionAdvice(MethodAdvice):
            session_factory: SessionFactory

            def supports(self, container: HandlerContainer) -> bool:
                return container.has_element(TransactionalElement)
    """

    def __init__(self, session_factory: Any):
        """
        Args:
            session_factory: SessionFactory 인스턴스
        """
        from .session import SessionFactory

        self._session_factory: SessionFactory = session_factory

    def supports(self, container: HandlerContainer) -> bool:
        """TransactionalElement가 있는 메서드에만 적용"""
        return container.has_element(TransactionalElement)

    def _get_element(self, container: HandlerContainer) -> TransactionalElement:
        """TransactionalElement 조회"""
        for element in container.elements:
            if isinstance(element, TransactionalElement):
                return element
        return TransactionalElement()  # 기본값

    # =========================================================================
    # 동기 버전
    # =========================================================================

    def begin_transaction_sync(
        self,
        container: HandlerContainer,
        call_depth: int,
    ) -> tuple[TransactionContext | None, bool]:
        """트랜잭션 시작 (동기)

        Args:
            container: 핸들러 컨테이너
            call_depth: 현재 콜스택 깊이

        Returns:
            (트랜잭션 컨텍스트, 새로 시작했는지 여부)
        """
        element = self._get_element(container)
        propagation = element.propagation
        read_only = element.read_only

        current_tx = get_current_transaction()

        # 전파 옵션에 따른 처리
        if propagation == Propagation.REQUIRED:
            if has_active_transaction():
                # 기존 트랜잭션에 합류
                return current_tx, False
            else:
                # 새 트랜잭션 시작
                return self._start_new_transaction_sync(call_depth, read_only), True

        elif propagation == Propagation.REQUIRES_NEW:
            # 항상 새 트랜잭션 (기존 것은 스택에 유지)
            return self._start_new_transaction_sync(call_depth, read_only), True

        elif propagation == Propagation.SUPPORTS:
            if has_active_transaction():
                return current_tx, False
            else:
                # 트랜잭션 없이 실행
                return None, False

        elif propagation == Propagation.NOT_SUPPORTED:
            # 트랜잭션 없이 실행 (기존 것은 일시 중단)
            return None, False

        elif propagation == Propagation.MANDATORY:
            if not has_active_transaction():
                raise TransactionRequiredError(
                    f"Propagation.MANDATORY requires an existing transaction"
                )
            return current_tx, False

        elif propagation == Propagation.NEVER:
            if has_active_transaction():
                raise TransactionNotAllowedError(
                    f"Propagation.NEVER does not allow existing transaction"
                )
            return None, False

        return None, False

    def _start_new_transaction_sync(
        self,
        call_depth: int,
        read_only: bool,
    ) -> TransactionContext:
        """새 트랜잭션 시작 (동기)"""
        session = self._session_factory.create()
        ctx = TransactionContext(
            session=session,
            depth=call_depth,
            read_only=read_only,
        )
        push_transaction(ctx)
        return ctx

    def commit_transaction_sync(self, ctx: TransactionContext) -> None:
        """트랜잭션 커밋 (동기)"""
        if ctx.committed or ctx.rolled_back:
            return

        try:
            ctx.session.commit()
            ctx.committed = True
        finally:
            pop_transaction()
            ctx.session.close()

    def rollback_transaction_sync(self, ctx: TransactionContext) -> None:
        """트랜잭션 롤백 (동기)"""
        if ctx.committed or ctx.rolled_back:
            return

        try:
            ctx.session.rollback()
            ctx.rolled_back = True
        finally:
            pop_transaction()
            ctx.session.close()

    # =========================================================================
    # 비동기 버전
    # =========================================================================

    async def begin_transaction_async(
        self,
        container: HandlerContainer,
        call_depth: int,
    ) -> tuple[TransactionContext | None, bool]:
        """트랜잭션 시작 (비동기)

        Args:
            container: 핸들러 컨테이너
            call_depth: 현재 콜스택 깊이

        Returns:
            (트랜잭션 컨텍스트, 새로 시작했는지 여부)
        """
        element = self._get_element(container)
        propagation = element.propagation
        read_only = element.read_only

        current_tx = get_current_transaction()

        if propagation == Propagation.REQUIRED:
            if has_active_transaction():
                return current_tx, False
            else:
                return (
                    await self._start_new_transaction_async(call_depth, read_only),
                    True,
                )

        elif propagation == Propagation.REQUIRES_NEW:
            return await self._start_new_transaction_async(call_depth, read_only), True

        elif propagation == Propagation.SUPPORTS:
            if has_active_transaction():
                return current_tx, False
            else:
                return None, False

        elif propagation == Propagation.NOT_SUPPORTED:
            return None, False

        elif propagation == Propagation.MANDATORY:
            if not has_active_transaction():
                raise TransactionRequiredError(
                    f"Propagation.MANDATORY requires an existing transaction"
                )
            return current_tx, False

        elif propagation == Propagation.NEVER:
            if has_active_transaction():
                raise TransactionNotAllowedError(
                    f"Propagation.NEVER does not allow existing transaction"
                )
            return None, False

        return None, False

    async def _start_new_transaction_async(
        self,
        call_depth: int,
        read_only: bool,
    ) -> TransactionContext:
        """새 트랜잭션 시작 (비동기)"""
        session = await self._session_factory.create_async()
        ctx = TransactionContext(
            session=session,
            depth=call_depth,
            read_only=read_only,
        )
        push_transaction(ctx)
        return ctx

    async def commit_transaction_async(self, ctx: TransactionContext) -> None:
        """트랜잭션 커밋 (비동기)"""
        if ctx.committed or ctx.rolled_back:
            return

        try:
            await ctx.session.commit()
            ctx.committed = True
        finally:
            pop_transaction()
            await ctx.session.close()

    async def rollback_transaction_async(self, ctx: TransactionContext) -> None:
        """트랜잭션 롤백 (비동기)"""
        if ctx.committed or ctx.rolled_back:
            return

        try:
            await ctx.session.rollback()
            ctx.rolled_back = True
        finally:
            pop_transaction()
            await ctx.session.close()


# =============================================================================
# MethodAdvice 구현
# =============================================================================


def create_transaction_method_advice(session_factory: Any) -> Any:
    """TransactionMethodAdvice 팩토리

    MethodAdvice 프로토콜을 구현한 트랜잭션 어드바이스를 생성합니다.

    사용법:
        @Component
        class TransactionConfig:
            @Factory
            def transaction_advice(
                self,
                session_factory: SessionFactory
            ) -> MethodAdvice:
                return create_transaction_method_advice(session_factory)
    """
    from bloom.core.advice import MethodAdvice, InvocationContext
    from bloom.core.advice.tracing.context import get_call_depth

    class TransactionMethodAdvice(MethodAdvice):
        """트랜잭션 MethodAdvice 구현"""

        def __init__(self):
            self._tx_advice = TransactionAdvice(session_factory)

        def supports(self, container: HandlerContainer) -> bool:
            return self._tx_advice.supports(container)

        # === 동기 버전 ===

        def before_sync(self, context: InvocationContext) -> None:
            call_depth = get_call_depth()
            tx_ctx, is_new = self._tx_advice.begin_transaction_sync(
                context.container, call_depth
            )
            context.set_attribute("__tx_ctx__", tx_ctx)
            context.set_attribute("__tx_is_new__", is_new)

        def after_sync(self, context: InvocationContext, result: Any) -> Any:
            tx_ctx = context.get_attribute("__tx_ctx__")
            is_new = context.get_attribute("__tx_is_new__", False)

            if tx_ctx is not None and is_new:
                self._tx_advice.commit_transaction_sync(tx_ctx)

            return result

        def on_error_sync(self, context: InvocationContext, error: Exception) -> Any:
            tx_ctx = context.get_attribute("__tx_ctx__")
            is_new = context.get_attribute("__tx_is_new__", False)

            if tx_ctx is not None and is_new:
                self._tx_advice.rollback_transaction_sync(tx_ctx)

            raise error

        # === 비동기 버전 ===

        async def before(self, context: InvocationContext) -> None:
            call_depth = get_call_depth()
            tx_ctx, is_new = await self._tx_advice.begin_transaction_async(
                context.container, call_depth
            )
            context.set_attribute("__tx_ctx__", tx_ctx)
            context.set_attribute("__tx_is_new__", is_new)

        async def after(self, context: InvocationContext, result: Any) -> Any:
            tx_ctx = context.get_attribute("__tx_ctx__")
            is_new = context.get_attribute("__tx_is_new__", False)

            if tx_ctx is not None and is_new:
                await self._tx_advice.commit_transaction_async(tx_ctx)

            return result

        async def on_error(self, context: InvocationContext, error: Exception) -> Any:
            tx_ctx = context.get_attribute("__tx_ctx__")
            is_new = context.get_attribute("__tx_is_new__", False)

            if tx_ctx is not None and is_new:
                await self._tx_advice.rollback_transaction_async(tx_ctx)

            raise error

    return TransactionMethodAdvice()


# =============================================================================
# Export
# =============================================================================

__all__ = [
    # Enum
    "Propagation",
    # Exceptions
    "TransactionError",
    "TransactionRequiredError",
    "TransactionNotAllowedError",
    # Element & Decorator
    "TransactionalElement",
    "Transactional",
    # Context
    "TransactionContext",
    "get_current_transaction",
    "has_active_transaction",
    "get_transaction_depth",
    # Advice
    "TransactionAdvice",
    "create_transaction_method_advice",
]
