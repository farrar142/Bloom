"""
Scope 모듈 - 인스턴스 스코프 및 CallStack 관리

스코프 종류:
- SINGLETON: 앱 전체에서 하나의 인스턴스
- CALL: 메서드 호출마다 새로 생성, 호출 끝나면 close
- REQUEST: HTTP 요청 단위로 인스턴스 공유

CallStack:
- CallFrame: 각 핸들러 호출마다 생성되는 프레임
- CallStackTracker: CallFrame 스택 관리 및 이벤트 리스너
"""

from contextvars import ContextVar
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar, overload, Literal, Awaitable, Callable
from uuid import uuid4
import asyncio

if TYPE_CHECKING:
    from .factory import FactoryContainer


# =============================================================================
# CallStack - 기존 call_scope.py에서 통합
# =============================================================================


class CallFrame:
    """핸들러 호출 프레임"""

    datas: list

    def __init__(self):
        self.id = id(self)
        self.datas = []

    def __repr__(self) -> str:
        return f"<CallFrame id={self.id} datas={self.datas}>"

    def add_data(self, data: Any) -> None:
        self.datas.append(data)


class CallStackTracker:
    """CallFrame 스택 관리자"""

    def __init__(self):
        self.__stack: list[CallFrame] = []
        self.__aadd_event_listeners: list[Callable[[CallFrame], Awaitable]] = []
        self.__aexit_event_listeners: list[Callable[[CallFrame], Awaitable]] = []

        self.__add_event_listeners: list[Callable[[CallFrame], None]] = []
        self.__exit_event_listeners: list[Callable[[CallFrame], None]] = []

    async def aadd_frame(self, frame: CallFrame) -> CallFrame:
        self.__stack.append(frame)
        await asyncio.gather(
            *[listener(frame) for listener in self.__aadd_event_listeners]
        )
        return frame

    async def aremove_frame(self, frame: CallFrame) -> None:
        self.__stack.remove(frame)
        await asyncio.gather(
            *[listener(frame) for listener in self.__aexit_event_listeners]
        )

    def aadd_event_listener(self, listener: Callable[[CallFrame], Awaitable]) -> None:
        self.__aadd_event_listeners.append(listener)

    def aexit_event_listener(self, listener: Callable[[CallFrame], Awaitable]) -> None:
        self.__aexit_event_listeners.append(listener)

    def aremove_event_listener(self, listener: Callable[[CallFrame], Awaitable]):
        self.__aexit_event_listeners.remove(listener)

    def aremove_add_event_listener(self, listener: Callable[[CallFrame], Awaitable]):
        self.__aadd_event_listeners.remove(listener)

    def add_event_listener(self, listener: Callable[[CallFrame], None]) -> None:
        self.__add_event_listeners.append(listener)

    def exit_event_listener(self, listener: Callable[[CallFrame], None]) -> None:
        self.__exit_event_listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[CallFrame], None]):
        self.__exit_event_listeners.remove(listener)

    def remove_add_event_listener(self, listener: Callable[[CallFrame], None]):
        self.__add_event_listeners.remove(listener)

    @overload
    async def current_frame(self) -> CallFrame | None: ...
    @overload
    async def current_frame(self, required: Literal[True]) -> CallFrame: ...
    async def current_frame(self, required: bool = False) -> CallFrame | None:
        if self.__stack:
            return self.__stack[-1]
        if required:
            raise RuntimeError("No active CallFrame in the current CallStack")
        return None

    async def __aenter__(self):
        frame = CallFrame()
        await self.aadd_frame(frame)
        return frame

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aremove_frame(await self.current_frame(True))

    def __enter__(self):
        frame = CallFrame()
        self.__stack.append(frame)
        for listener in self.__add_event_listeners:
            listener(frame)
        return frame

    def __exit__(self, exc_type, exc_val, exc_tb):
        frame = self.__stack.pop()
        for listener in self.__exit_event_listeners:
            listener(frame)


_call_stack_tracker_contextvar: ContextVar[CallStackTracker] = ContextVar[
    CallStackTracker
]("call_stack_tracker", default=CallStackTracker())


def call_stack() -> CallStackTracker:
    """현재 CallStackTracker 반환"""
    return _call_stack_tracker_contextvar.get()


# =============================================================================
# Scope - 인스턴스 스코프
# =============================================================================


class Scope(Enum):
    """인스턴스 스코프"""

    SINGLETON = "singleton"  # 앱 전체에서 하나
    CALL = "call"  # 메서드 호출마다 새로 생성, 호출 끝나면 close
    REQUEST = "request"  # HTTP 요청 단위로 공유


def get_scope(target: Any, default: Scope = Scope.SINGLETON) -> Scope:
    """대상에서 @Scoped 데코레이터로 지정된 스코프 가져오기

    Args:
        target: 클래스 또는 함수
        default: @Scoped가 없을 때 기본값

    Returns:
        스코프 값
    """
    return getattr(target, "__scope__", default)


T = TypeVar("T")


class ScopeContext:
    """스코프 컨텍스트 - 스코프 내 인스턴스 저장소"""

    def __init__(self, scope: Scope, context_id: str | None = None):
        self.scope = scope
        self.context_id = context_id or str(uuid4())
        self._instances: dict[str, Any] = {}  # component_id -> instance
        self._closeables: list[Any] = []  # AutoCloseable 인스턴스들

    def get(self, component_id: str) -> Any | None:
        """스코프 내 인스턴스 조회"""
        return self._instances.get(component_id)

    def set(self, component_id: str, instance: Any) -> None:
        """스코프 내 인스턴스 저장"""
        self._instances[component_id] = instance

    def register_closeable(self, instance: Any) -> None:
        """AutoCloseable 인스턴스 등록"""
        self._closeables.append(instance)

    def close_all(self) -> None:
        """모든 AutoCloseable 인스턴스 close (sync)"""
        from ..abstract.autocloseable import AutoCloseable

        for instance in reversed(self._closeables):
            if isinstance(instance, AutoCloseable):
                try:
                    instance.__exit__(None, None, None)
                except Exception:
                    pass  # 에러 무시하고 계속 진행
        self._closeables.clear()
        self._instances.clear()

    async def aclose_all(self) -> None:
        """모든 AutoCloseable/AsyncAutoCloseable 인스턴스 close (async)"""
        from ..abstract.autocloseable import AsyncAutoCloseable, AutoCloseable

        for instance in reversed(self._closeables):
            try:
                if isinstance(instance, AsyncAutoCloseable):
                    await instance.__aexit__(None, None, None)
                elif isinstance(instance, AutoCloseable):
                    instance.__exit__(None, None, None)
            except Exception:
                pass
        self._closeables.clear()
        self._instances.clear()

    def __repr__(self) -> str:
        return f"<ScopeContext scope={self.scope.value} id={self.context_id[:8]}... instances={len(self._instances)}>"


# =============================================================================
# 스코프 컨텍스트 관리
# =============================================================================

# REQUEST 스코프용 ContextVar
_request_scope_context: ContextVar[ScopeContext | None] = ContextVar(
    "request_scope_context", default=None
)

# CALL 스코프용 ContextVar (CallFrame별로 관리)
_call_scope_context: ContextVar[ScopeContext | None] = ContextVar(
    "call_scope_context", default=None
)

# Transactional 스코프용 ContextVar
_transactional_context: ContextVar[ScopeContext | None] = ContextVar(
    "transactional_context", default=None
)


def get_request_scope() -> ScopeContext | None:
    """현재 REQUEST 스코프 컨텍스트 조회"""
    return _request_scope_context.get()


def set_request_scope(context: ScopeContext | None) -> None:
    """REQUEST 스코프 컨텍스트 설정"""
    _request_scope_context.set(context)


def get_call_scope() -> ScopeContext | None:
    """현재 CALL 스코프 컨텍스트 조회"""
    return _call_scope_context.get()


def set_call_scope(context: ScopeContext | None) -> None:
    """CALL 스코프 컨텍스트 설정"""
    _call_scope_context.set(context)


def get_transactional_scope() -> ScopeContext | None:
    """현재 Transactional 스코프 컨텍스트 조회"""
    return _transactional_context.get()


def set_transactional_scope(context: ScopeContext | None) -> None:
    """Transactional 스코프 컨텍스트 설정"""
    _transactional_context.set(context)


def get_scope_context(scope: Scope) -> ScopeContext | None:
    """스코프에 해당하는 컨텍스트 조회"""
    if scope == Scope.REQUEST:
        return get_request_scope()
    elif scope == Scope.CALL:
        # Transactional이 있으면 우선 사용
        transactional = get_transactional_scope()
        if transactional is not None:
            return transactional
        return get_call_scope()
    return None


# =============================================================================
# 스코프 컨텍스트 매니저
# =============================================================================


class RequestScopeManager:
    """REQUEST 스코프 관리자"""

    def __init__(self):
        self._context: ScopeContext | None = None

    def __enter__(self) -> ScopeContext:
        self._context = ScopeContext(Scope.REQUEST)
        set_request_scope(self._context)
        return self._context

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._context:
            self._context.close_all()
        set_request_scope(None)

    async def __aenter__(self) -> ScopeContext:
        self._context = ScopeContext(Scope.REQUEST)
        set_request_scope(self._context)
        return self._context

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._context:
            await self._context.aclose_all()
        set_request_scope(None)


class CallScopeManager:
    """CALL 스코프 관리자 - CallStackTracker와 ScopeContext 통합 관리"""

    def __init__(self):
        self._context: ScopeContext | None = None
        self._frame: CallFrame | None = None
        self._tracker: CallStackTracker | None = None

    def __enter__(self) -> ScopeContext:
        self._context = ScopeContext(Scope.CALL)
        set_call_scope(self._context)

        # CallStackTracker 프레임 생성
        self._tracker = call_stack()
        self._frame = self._tracker.__enter__()
        self._frame.add_data({"scope_context": self._context})

        return self._context

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._tracker:
            self._tracker.__exit__(exc_type, exc_val, exc_tb)
        if self._context:
            self._context.close_all()
        set_call_scope(None)

    async def __aenter__(self) -> ScopeContext:
        self._context = ScopeContext(Scope.CALL)
        set_call_scope(self._context)

        # CallStackTracker 프레임 생성 (async)
        self._tracker = call_stack()
        self._frame = await self._tracker.__aenter__()
        self._frame.add_data({"scope_context": self._context})

        return self._context

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._tracker:
            await self._tracker.__aexit__(exc_type, exc_val, exc_tb)
        if self._context:
            await self._context.aclose_all()
        set_call_scope(None)


class TransactionalScopeManager:
    """Transactional 스코프 관리자 - CALL 스코프 내에서 인스턴스 공유"""

    def __init__(self):
        self._context: ScopeContext | None = None
        self._previous_context: ScopeContext | None = None

    def __enter__(self) -> ScopeContext:
        # 기존 transactional context가 있으면 재사용 (중첩 지원)
        existing = get_transactional_scope()
        if existing is not None:
            self._context = existing
            return existing

        self._context = ScopeContext(Scope.CALL)
        self._previous_context = get_transactional_scope()
        set_transactional_scope(self._context)
        return self._context

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # 이 매니저가 생성한 context만 정리
        if self._previous_context is None and self._context:
            self._context.close_all()
            set_transactional_scope(None)

    async def __aenter__(self) -> ScopeContext:
        existing = get_transactional_scope()
        if existing is not None:
            self._context = existing
            return existing

        self._context = ScopeContext(Scope.CALL)
        self._previous_context = get_transactional_scope()
        set_transactional_scope(self._context)
        return self._context

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._previous_context is None and self._context:
            await self._context.aclose_all()
            set_transactional_scope(None)


def request_scope() -> RequestScopeManager:
    """REQUEST 스코프 컨텍스트 매니저"""
    return RequestScopeManager()


def call_scope_manager() -> CallScopeManager:
    """CALL 스코프 컨텍스트 매니저"""
    return CallScopeManager()


def transactional_scope() -> TransactionalScopeManager:
    """Transactional 스코프 컨텍스트 매니저"""
    return TransactionalScopeManager()
