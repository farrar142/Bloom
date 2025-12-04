"""bloom.db.decorators - 데이터베이스 관련 데코레이터

트랜잭션 관리를 위한 데코레이터를 제공합니다.
"""

from __future__ import annotations

import asyncio
from enum import Enum, auto
from functools import wraps
from typing import Any, Callable, TypeVar, overload

from bloom.core.manager import get_container_manager

F = TypeVar("F", bound=Callable[..., Any])


class Propagation(Enum):
    """트랜잭션 전파 옵션

    Spring의 Propagation과 유사한 개념을 구현합니다.

    - REQUIRED: 기존 트랜잭션이 있으면 참여, 없으면 새로 생성 (기본값)
    - REQUIRES_NEW: 항상 새 트랜잭션 생성
    - MANDATORY: 반드시 기존 트랜잭션이 있어야 함 (없으면 예외)
    - SUPPORTS: 기존 트랜잭션이 있으면 참여, 없으면 트랜잭션 없이 실행
    - NOT_SUPPORTED: 트랜잭션 없이 실행 (기존 트랜잭션 일시 중단)
    - NEVER: 트랜잭션이 있으면 예외
    """

    REQUIRED = auto()  # propagate=True (기본)
    REQUIRES_NEW = auto()  # propagate=False
    MANDATORY = auto()  # propagate=True + 부모 필수
    # SUPPORTS = auto()     # 나중에 필요시 구현
    # NOT_SUPPORTED = auto()
    # NEVER = auto()


class TransactionError(Exception):
    """트랜잭션 관련 예외"""

    pass


class NoActiveTransactionError(TransactionError):
    """활성 트랜잭션이 없을 때 발생 (MANDATORY 전파)"""

    pass


@overload
def Transactional(func: F) -> F:
    """@Transactional - 기본 REQUIRED 전파"""
    ...


@overload
def Transactional(
    *,
    propagation: Propagation = Propagation.REQUIRED,
    read_only: bool = False,
) -> Callable[[F], F]:
    """@Transactional(...) - 옵션 지정"""
    ...


def Transactional(
    func: F | None = None,
    *,
    propagation: Propagation = Propagation.REQUIRED,
    read_only: bool = False,
) -> F | Callable[[F], F]:
    """
    트랜잭션 관리 데코레이터.

    CALL 스코프와 함께 동작하여 같은 트랜잭션 내에서
    동일한 세션/커넥션을 공유합니다.

    기본적으로 propagation=REQUIRED로 동작하여:
    - 기존 트랜잭션이 있으면 해당 트랜잭션에 참여
    - 기존 트랜잭션이 없으면 새 트랜잭션 생성

    Args:
        propagation: 트랜잭션 전파 방식
            - REQUIRED (기본): 기존 트랜잭션 참여 또는 새로 생성
            - REQUIRES_NEW: 항상 새 트랜잭션 생성
            - MANDATORY: 기존 트랜잭션 필수 (없으면 예외)
        read_only: 읽기 전용 트랜잭션 여부 (힌트, 현재 미구현)

    사용 예:
        @Component
        class UserService:
            session: AsyncProxy[AsyncSession]

            @Transactional
            async def create_user(self, name: str):
                s = await self.session.resolve()
                # ... 작업
                await s.commit()  # 한 번에 커밋

            @Transactional(propagation=Propagation.REQUIRES_NEW)
            async def audit_log(self, message: str):
                # 별도 트랜잭션에서 실행
                s = await self.session.resolve()
                # ...

            @Transactional(propagation=Propagation.MANDATORY)
            async def internal_work(self):
                # 반드시 기존 트랜잭션 내에서만 호출 가능
                pass
    """

    def decorator(fn: F) -> F:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            manager = get_container_manager()
            scope_manager = manager.scope_manager

            # 전파 옵션에 따라 propagate 결정
            if propagation == Propagation.REQUIRED:
                # 기존 스코프 있으면 참여, 없으면 새로 생성
                propagate = True
            elif propagation == Propagation.REQUIRES_NEW:
                # 항상 새 스코프
                propagate = False
            elif propagation == Propagation.MANDATORY:
                # 기존 스코프 필수
                propagate = True
                # 기존 스코프가 없으면 예외
                existing_frame = scope_manager._get_current_frame_id()
                if existing_frame is None:
                    raise NoActiveTransactionError(
                        f"@Transactional(propagation=MANDATORY) requires an existing transaction. "
                        f"Method '{fn.__name__}' was called outside of a transaction context."
                    )
            else:
                propagate = True

            # Call 스코프 시작
            frame_id, is_owner = scope_manager.start_call(propagate=propagate)

            try:
                result = fn(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            finally:
                # Call 스코프 종료
                await scope_manager.end_call(frame_id, is_owner=is_owner)

        # 메타데이터 보존
        wrapper.__bloom_transactional__ = True  # type: ignore
        wrapper.__bloom_transactional_propagation__ = propagation  # type: ignore
        wrapper.__bloom_transactional_read_only__ = read_only  # type: ignore

        return wrapper  # type: ignore

    # @Transactional 또는 @Transactional()
    if func is not None:
        return decorator(func)
    return decorator


# 편의를 위한 별칭
def RequiresNew(func: F) -> F:
    """@RequiresNew = @Transactional(propagation=Propagation.REQUIRES_NEW)"""
    return Transactional(propagation=Propagation.REQUIRES_NEW)(func)


def Mandatory(func: F) -> F:
    """@Mandatory = @Transactional(propagation=Propagation.MANDATORY)"""
    return Transactional(propagation=Propagation.MANDATORY)(func)
