"""bloom.core.scope_manager - 스코프별 인스턴스 관리"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any, TypeVar, TYPE_CHECKING

from .scope import Scope
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

# 현재 활성 frame_id (Call 스코프용)
_current_frame_id: ContextVar[str | None] = ContextVar(
    "bloom_current_frame_id", default=None
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

    # === CALL SCOPE ===

    def start_call(self) -> str:
        """
        메서드 호출 시작 - @Handler 진입 시.

        Returns:
            생성된 frame_id
        """
        frame_id = str(uuid.uuid4())

        instances = _call_instances.get()
        order = _call_creation_order.get()

        if instances is None:
            instances = {}
            _call_instances.set(instances)
        if order is None:
            order = {}
            _call_creation_order.set(order)

        instances[frame_id] = {}
        order[frame_id] = []

        # 현재 frame_id 설정
        _current_frame_id.set(frame_id)

        return frame_id

    async def end_call(self, frame_id: str) -> None:
        """메서드 호출 종료 - @PreDestroy 호출 후 정리"""
        instances = _call_instances.get()
        order = _call_creation_order.get()

        if instances and frame_id in instances:
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

        # frame_id 초기화
        _current_frame_id.set(None)

    def get_call_scoped[T](self, cls: type[T], frame_id: str | None = None) -> T | None:
        """CALL 스코프 인스턴스 조회"""
        if frame_id is None:
            frame_id = _current_frame_id.get()
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
            frame_id = _current_frame_id.get()
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
            frame_id = _current_frame_id.get()
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
        return _current_frame_id.get() is not None

    def get_current_frame_id(self) -> str | None:
        """현재 활성 frame_id 반환"""
        return _current_frame_id.get()

    # === 통합 조회 ===

    def get_instance[T](
        self,
        cls: type[T],
        scope: Scope,
        frame_id: str | None = None,
    ) -> T | None:
        """스코프에 따라 인스턴스 조회"""
        match scope:
            case Scope.SINGLETON:
                return self.get_singleton(cls)
            case Scope.REQUEST:
                return self.get_request_scoped(cls)
            case Scope.CALL:
                return self.get_call_scoped(cls, frame_id)

    def set_instance[T](
        self,
        cls: type[T],
        instance: T,
        scope: Scope,
        frame_id: str | None = None,
    ) -> None:
        """스코프에 따라 인스턴스 저장"""
        match scope:
            case Scope.SINGLETON:
                self.set_singleton(cls, instance)
            case Scope.REQUEST:
                self.set_request_scoped(cls, instance)
            case Scope.CALL:
                self.set_call_scoped(cls, instance, frame_id)

    def has_instance(
        self, cls: type, scope: Scope, frame_id: str | None = None
    ) -> bool:
        """스코프에 따라 인스턴스 존재 여부 확인"""
        match scope:
            case Scope.SINGLETON:
                return self.has_singleton(cls)
            case Scope.REQUEST:
                return self.has_request_scoped(cls)
            case Scope.CALL:
                return self.has_call_scoped(cls, frame_id)
        return False
