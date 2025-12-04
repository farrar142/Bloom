"""bloom.core.scope_manager - 스코프별 인스턴스 관리"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, TypeVar, TYPE_CHECKING, AsyncIterator

from .scope import ScopeEnum
from .lifecycle import LifecycleManager
from .exceptions import RequestScopeError, CallScopeError

if TYPE_CHECKING:
    from .container import Container


T = TypeVar("T")


# === Context Variables ===

# Request 스코프: 요청당 인스턴스 저장소
_request_instances: ContextVar[dict[type, Any] | None] = ContextVar(
    "bloom_request_instances", default=None
)

# Request 스코프: 생성 순서 추적 (역순 정리용)
_request_creation_order: ContextVar[list[type] | None] = ContextVar(
    "bloom_request_creation_order", default=None
)

# Call 스코프: frame_id → {type → instance}
_call_instances: ContextVar[dict[str, dict[type, Any]] | None] = ContextVar(
    "bloom_call_instances", default=None
)

# Call 스코프: frame_id → 생성 순서
_call_creation_order: ContextVar[dict[str, list[type]] | None] = ContextVar(
    "bloom_call_creation_order", default=None
)

# 현재 활성 frame_id 스택 (중첩 Handler 지원)
_frame_id_stack: ContextVar[list[str] | None] = ContextVar(
    "bloom_frame_id_stack", default=None
)


class ScopeManager:
    """
    스코프별 인스턴스 저장/조회/정리.

    - SINGLETON: 앱 전체에서 단일 인스턴스
    - REQUEST: HTTP 요청마다 새 인스턴스 (ContextVar)
    - CALL: @Handler 메서드 호출마다 새 인스턴스 (ContextVar + frame_id)
    """

    def __init__(self) -> None:
        # Singleton 인스턴스 저장소
        self._singletons: dict[type, Any] = {}
        # Singleton 생성 순서 (역순 정리용)
        self._singleton_order: list[type] = []

    # === SINGLETON ===

    def get_singleton[T](self, cls: type[T]) -> T | None:
        """싱글톤 인스턴스 조회"""
        return self._singletons.get(cls)

    def set_singleton[T](self, cls: type[T], instance: T) -> None:
        """싱글톤 인스턴스 저장"""
        if cls not in self._singletons:
            self._singleton_order.append(cls)
        self._singletons[cls] = instance

    def has_singleton(self, cls: type) -> bool:
        """싱글톤 존재 여부"""
        return cls in self._singletons

    async def destroy_singletons(self) -> None:
        """모든 싱글톤 정리 (역순)"""
        for cls in reversed(self._singleton_order):
            instance = self._singletons.get(cls)
            if instance:
                await LifecycleManager.invoke_pre_destroy(instance)
        self._singletons.clear()
        self._singleton_order.clear()

    # === REQUEST SCOPE ===

    def start_request(self) -> None:
        """요청 시작 - 미들웨어에서 호출"""
        _request_instances.set({})
        _request_creation_order.set([])

    async def end_request(self) -> None:
        """요청 종료 - @PreDestroy 호출 후 정리"""
        instances = _request_instances.get()
        order = _request_creation_order.get()

        if instances and order:
            # 역순으로 정리
            for cls in reversed(order):
                instance = instances.get(cls)
                if instance:
                    await LifecycleManager.invoke_pre_destroy(instance)

        _request_instances.set(None)
        _request_creation_order.set(None)

    def get_request_scoped[T](self, cls: type[T]) -> T | None:
        """REQUEST 스코프 인스턴스 조회"""
        instances = _request_instances.get()
        if instances is None:
            return None
        return instances.get(cls)

    def set_request_scoped[T](self, cls: type[T], instance: T) -> None:
        """REQUEST 스코프 인스턴스 저장"""
        instances = _request_instances.get()
        order = _request_creation_order.get()

        if instances is None:
            raise RequestScopeError(cls)

        if cls not in instances and order is not None:
            order.append(cls)
        instances[cls] = instance

    def has_request_scoped(self, cls: type) -> bool:
        """REQUEST 스코프 인스턴스 존재 여부"""
        instances = _request_instances.get()
        return instances is not None and cls in instances

    def is_in_request_context(self) -> bool:
        """현재 요청 컨텍스트 내부인지 확인"""
        return _request_instances.get() is not None

    @asynccontextmanager
    async def request_scope(self) -> AsyncIterator[None]:
        """
        REQUEST 스코프 컨텍스트 매니저.

        사용 예:
            async with scope_manager.request_scope():
                # REQUEST 스코프 인스턴스 사용
                instance = await manager.get_instance_async(RequestScopedService)
        """
        self.start_request()
        try:
            yield
        finally:
            await self.end_request()

    # === CALL SCOPE ===

    def _get_current_frame_id(self) -> str | None:
        """현재 활성 frame_id 반환 (스택 최상단)"""
        stack = _frame_id_stack.get()
        if stack and len(stack) > 0:
            return stack[-1]
        return None

    def _push_frame_id(self, frame_id: str) -> None:
        """frame_id를 스택에 푸시"""
        stack = _frame_id_stack.get()
        if stack is None:
            stack = []
            _frame_id_stack.set(stack)
        stack.append(frame_id)

    def _pop_frame_id(self) -> str | None:
        """frame_id를 스택에서 팝"""
        stack = _frame_id_stack.get()
        if stack and len(stack) > 0:
            return stack.pop()
        return None

    def start_call(
        self, *, inherit_parent: bool = False, propagate: bool = False
    ) -> tuple[str, bool]:
        """
        메서드 호출 시작 - @Handler 진입 시.

        Args:
            inherit_parent: True면 부모 컨텍스트의 CALL 스코프 인스턴스를 상속 (복사)
                           (중첩 Handler에서 부모 인스턴스를 스냅샷으로 가져올 때)
            propagate: True면 기존 CALL 스코프가 있을 경우 그대로 재사용
                      (트랜잭션 전파처럼 같은 스코프를 공유하고 싶을 때)

        Returns:
            tuple[frame_id, is_owner]: frame_id와 이 호출이 스코프 소유자인지 여부
                                       propagate로 기존 스코프를 재사용하면 is_owner=False
        """
        # propagate 옵션: 기존 스코프가 있으면 재사용
        if propagate:
            existing_frame_id = self._get_current_frame_id()
            if existing_frame_id is not None:
                # 기존 스코프 재사용 - 새 frame_id 생성하지 않음
                return existing_frame_id, False

        frame_id = str(uuid.uuid4())

        instances = _call_instances.get()
        order = _call_creation_order.get()

        if instances is None:
            instances = {}
            _call_instances.set(instances)
        if order is None:
            order = {}
            _call_creation_order.set(order)

        # 부모 컨텍스트 상속 옵션 (복사)
        if inherit_parent:
            parent_frame_id = self._get_current_frame_id()
            if parent_frame_id and parent_frame_id in instances:
                # 부모의 인스턴스 복사 (얕은 복사)
                instances[frame_id] = dict(instances[parent_frame_id])
                order[frame_id] = []  # 생성 순서는 새로 시작
            else:
                instances[frame_id] = {}
                order[frame_id] = []
        else:
            instances[frame_id] = {}
            order[frame_id] = []

        # frame_id를 스택에 푸시 (중첩 호출 지원)
        self._push_frame_id(frame_id)

        return frame_id, True

    async def end_call(
        self, frame_id: str, *, destroy_instances: bool = True, is_owner: bool = True
    ) -> None:
        """
        메서드 호출 종료 - @PreDestroy 호출 후 정리.

        Args:
            frame_id: 종료할 frame_id
            destroy_instances: False면 @PreDestroy를 호출하지 않음
                              (부모 컨텍스트에서 정리하게 위임할 때)
            is_owner: False면 스코프 정리를 하지 않음
                     (propagate로 기존 스코프를 재사용한 경우)
        """
        # propagate로 기존 스코프를 재사용한 경우 정리하지 않음
        if not is_owner:
            return

        instances = _call_instances.get()
        order = _call_creation_order.get()

        if instances and frame_id in instances:
            if destroy_instances:
                frame_instances = instances[frame_id]
                frame_order = order.get(frame_id, []) if order else []

                # 역순으로 정리
                for cls in reversed(frame_order):
                    instance = frame_instances.get(cls)
                    if instance:
                        await LifecycleManager.invoke_pre_destroy(instance)

            del instances[frame_id]
            if order and frame_id in order:
                del order[frame_id]

        # frame_id를 스택에서 팝
        self._pop_frame_id()

    def get_call_scoped[T](self, cls: type[T], frame_id: str | None = None) -> T | None:
        """CALL 스코프 인스턴스 조회"""
        if frame_id is None:
            frame_id = self._get_current_frame_id()
        if frame_id is None:
            return None

        instances = _call_instances.get()
        if instances is None or frame_id not in instances:
            return None

        return instances[frame_id].get(cls)

    def set_call_scoped[T](
        self, cls: type[T], instance: T, frame_id: str | None = None
    ) -> None:
        """CALL 스코프 인스턴스 저장"""
        if frame_id is None:
            frame_id = self._get_current_frame_id()
        if frame_id is None:
            raise CallScopeError(cls)

        instances = _call_instances.get()
        order = _call_creation_order.get()

        if instances is None or frame_id not in instances:
            raise CallScopeError(cls)

        if cls not in instances[frame_id]:
            if order and frame_id in order:
                order[frame_id].append(cls)
        instances[frame_id][cls] = instance

    def has_call_scoped(self, cls: type, frame_id: str | None = None) -> bool:
        """CALL 스코프 인스턴스 존재 여부"""
        if frame_id is None:
            frame_id = self._get_current_frame_id()
        if frame_id is None:
            return False

        instances = _call_instances.get()
        return (
            instances is not None
            and frame_id in instances
            and cls in instances[frame_id]
        )

    def is_in_call_context(self) -> bool:
        """현재 Call 컨텍스트 내부인지 확인"""
        return self._get_current_frame_id() is not None

    def get_current_frame_id(self) -> str | None:
        """현재 활성 frame_id 반환"""
        return self._get_current_frame_id()

    def get_frame_stack_depth(self) -> int:
        """현재 frame 스택 깊이 반환 (중첩 Handler 깊이)"""
        stack = _frame_id_stack.get()
        return len(stack) if stack else 0

    @asynccontextmanager
    async def call_scope(
        self,
        *,
        inherit_parent: bool = False,
        destroy_instances: bool = True,
        propagate: bool = False,
    ) -> AsyncIterator[str]:
        """
        CALL 스코프 컨텍스트 매니저.

        Args:
            inherit_parent: True면 부모 컨텍스트의 인스턴스를 상속 (복사)
            destroy_instances: False면 종료 시 @PreDestroy를 호출하지 않음
            propagate: True면 기존 CALL 스코프가 있을 경우 그대로 재사용
                      (트랜잭션 전파처럼 같은 스코프를 공유하고 싶을 때)

        Yields:
            frame_id: 생성된 또는 재사용된 frame ID

        사용 예:
            async with scope_manager.call_scope() as frame_id:
                # CALL 스코프 인스턴스 사용
                instance = await manager.get_instance_async(CallScopedService)
            # 종료 시 자동으로 @PreDestroy 호출

            # 부모 인스턴스 상속 (복사)
            async with scope_manager.call_scope(inherit_parent=True):
                # 부모 컨텍스트의 인스턴스를 복사해서 사용
                pass

            # 트랜잭션 전파 (기존 스코프 재사용)
            async with scope_manager.call_scope(propagate=True) as frame_id:
                # 기존 스코프가 있으면 같은 인스턴스 공유
                # 없으면 새 스코프 생성
                pass
        """
        frame_id, is_owner = self.start_call(
            inherit_parent=inherit_parent, propagate=propagate
        )
        try:
            yield frame_id
        finally:
            await self.end_call(
                frame_id, destroy_instances=destroy_instances, is_owner=is_owner
            )

    # === 통합 조회 ===

    def get_instance[T](
        self,
        cls: type[T],
        scope: ScopeEnum,
        frame_id: str | None = None,
    ) -> T | None:
        """스코프에 따라 인스턴스 조회"""
        match scope:
            case ScopeEnum.SINGLETON:
                return self.get_singleton(cls)
            case ScopeEnum.REQUEST:
                return self.get_request_scoped(cls)
            case ScopeEnum.CALL:
                return self.get_call_scoped(cls, frame_id)

    def set_instance[T](
        self,
        cls: type[T],
        instance: T,
        scope: ScopeEnum,
        frame_id: str | None = None,
    ) -> None:
        """스코프에 따라 인스턴스 저장"""
        match scope:
            case ScopeEnum.SINGLETON:
                self.set_singleton(cls, instance)
            case ScopeEnum.REQUEST:
                self.set_request_scoped(cls, instance)
            case ScopeEnum.CALL:
                self.set_call_scoped(cls, instance, frame_id)

    def has_instance(
        self, cls: type, scope: ScopeEnum, frame_id: str | None = None
    ) -> bool:
        """스코프에 따라 인스턴스 존재 여부 확인"""
        match scope:
            case ScopeEnum.SINGLETON:
                return self.has_singleton(cls)
            case ScopeEnum.REQUEST:
                return self.has_request_scoped(cls)
            case ScopeEnum.CALL:
                return self.has_call_scoped(cls, frame_id)
        return False
