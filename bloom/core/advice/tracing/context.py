"""콜스택 컨텍스트 관리

ContextVar 기반으로 각 코루틴/스레드별 독립적인 콜스택을 관리합니다.
불변 튜플을 사용하여 스레드 안전성을 보장합니다.

PROTOTYPE 스코프 인스턴스 자동 정리:
- 메서드 진입 시: 새 depth에 대한 PROTOTYPE 리스트 생성
- PROTOTYPE 생성 시: 현재 depth의 리스트에 추가
- 메서드 종료 시: 해당 depth의 PROTOTYPE들 @PreDestroy 호출
"""

from contextvars import ContextVar
import time
import uuid
from typing import Any, TYPE_CHECKING

from .frame import CallFrame

if TYPE_CHECKING:
    from ...container import Container


# 콜스택 저장 (불변 튜플로 스레드 안전)
_call_stack: ContextVar[tuple[CallFrame, ...]] = ContextVar(
    "bloom_call_stack", default=()
)

# 요청별 추적 ID
_trace_id: ContextVar[str] = ContextVar("bloom_trace_id", default="")

# PROTOTYPE 인스턴스 저장 (depth -> [(instance, container), ...])
# 각 콜스택 깊이별로 생성된 PROTOTYPE 인스턴스들을 추적
_prototype_instances: ContextVar[dict[int, list[tuple[Any, "Container"]]]] = ContextVar(
    "bloom_prototype_instances", default={}
)

# CALL_SCOPED PROTOTYPE 캐시 (frame_id -> {component_type: instance})
# 같은 핸들러 호출(frame_id) 내에서 같은 타입 요청 시 캐시된 인스턴스 반환
_scoped_prototype_cache: ContextVar[dict[str, dict[type, Any]]] = ContextVar(
    "bloom_scoped_prototype_cache", default={}
)


def get_trace_id() -> str:
    """현재 추적 ID 반환 (없으면 빈 문자열)"""
    return _trace_id.get()


def set_trace_id(trace_id: str | None = None) -> str:
    """
    추적 ID 설정

    Args:
        trace_id: 설정할 ID (None이면 UUID 자동 생성)

    Returns:
        설정된 추적 ID
    """
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:8]
    _trace_id.set(trace_id)
    return trace_id


def get_call_stack() -> tuple[CallFrame, ...]:
    """
    현재 코루틴/스레드의 콜스택 반환

    Returns:
        콜 프레임 튜플 (첫 번째가 가장 바깥쪽 호출)
    """
    return _call_stack.get()


def get_current_frame() -> CallFrame | None:
    """
    현재 프레임 반환 (가장 안쪽 호출)

    Returns:
        현재 CallFrame 또는 None
    """
    stack = _call_stack.get()
    return stack[-1] if stack else None


def get_call_depth() -> int:
    """현재 콜스택 깊이 반환"""
    return len(_call_stack.get())


def push_frame(
    instance: Any,
    method_name: str,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    include_args: bool = False,
) -> CallFrame:
    """
    새 프레임을 콜스택에 추가

    Args:
        instance: 메서드가 바인딩된 인스턴스
        method_name: 메서드명
        args: 위치 인자
        kwargs: 키워드 인자
        include_args: 인자 요약 포함 여부

    Returns:
        생성된 CallFrame
    """
    current_stack = _call_stack.get()
    depth = len(current_stack)

    # 인자 요약 생성 (선택적)
    args_summary = ""
    if include_args:
        args_summary = _summarize_args(args, kwargs or {})

    frame = CallFrame(
        instance_type=type(instance).__name__,
        method_name=method_name,
        start_time=time.time(),
        trace_id=get_trace_id() or "no-trace",
        depth=depth,
        args_summary=args_summary,
    )

    # 새 튜플 생성 (불변성 유지)
    _call_stack.set(current_stack + (frame,))

    return frame


def pop_frame() -> CallFrame | None:
    """
    마지막 프레임을 콜스택에서 제거

    해당 프레임에서 생성된 PROTOTYPE 인스턴스들의 @PreDestroy를 호출합니다.

    Returns:
        제거된 CallFrame 또는 None
    """
    current_stack = _call_stack.get()
    if not current_stack:
        return None

    frame = current_stack[-1]
    depth = frame.depth

    # PROTOTYPE 인스턴스 정리 (메서드 스코프 종료)
    cleanup_prototypes_at_depth(depth)

    # 새 튜플 생성 (불변성 유지)
    _call_stack.set(current_stack[:-1])

    return frame


def clear_stack() -> None:
    """콜스택 초기화 (요청 종료 시 사용)"""
    _call_stack.set(())
    _trace_id.set("")
    _prototype_instances.set({})
    _scoped_prototype_cache.set({})


class call_scope:
    """콜스택 컨텍스트 매니저
    
    with 문을 사용해 핸들러 호출 컨텍스트를 시뮬레이션합니다.
    CALL_SCOPED 프로토타입 인스턴스가 같은 컨텍스트 내에서 공유됩니다.
    
    사용법:
        with call_scope(instance, "method_name"):
            # 이 블록 내에서 CALL_SCOPED 인스턴스가 공유됨
            result = instance.method_name()
        
        # 또는 trace_id 지정
        with call_scope(instance, "method_name", trace_id="test-123"):
            ...
            
        # 테스트에서 간단히 사용
        with call_scope():
            # 익명 컨텍스트 - CALL_SCOPED 공유만 필요할 때
            repo1.get()
            repo2.get()  # 같은 Session 공유
    """
    
    def __init__(
        self,
        instance: Any = None,
        method_name: str = "anonymous",
        trace_id: str | None = None,
    ):
        self.instance = instance or object()
        self.method_name = method_name
        self.trace_id = trace_id
        self._frame: CallFrame | None = None
    
    def __enter__(self) -> "call_scope":
        if self.trace_id:
            set_trace_id(self.trace_id)
        elif not get_trace_id():
            set_trace_id()  # 자동 생성
        
        self._frame = push_frame(self.instance, self.method_name)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pop_frame()
        return None  # 예외 전파


# =============================================================================
# PROTOTYPE 인스턴스 자동 정리
# =============================================================================


def register_prototype(instance: Any, container: "Container") -> None:
    """
    현재 콜스택 깊이에 PROTOTYPE 인스턴스 등록

    메서드 종료 시 자동으로 @PreDestroy가 호출됩니다.

    Args:
        instance: PROTOTYPE 인스턴스
        container: 컨테이너 (라이프사이클 메서드 조회용)
    """
    depth = get_call_depth()
    if depth == 0:
        # 콜스택 외부에서 생성된 PROTOTYPE은 추적하지 않음
        return

    # 현재 depth - 1에 등록 (현재 메서드 내에서 생성된 것이므로)
    target_depth = depth - 1

    instances = _prototype_instances.get()
    # ContextVar는 코루틴별로 격리되므로 직접 수정해도 안전
    if target_depth not in instances:
        instances[target_depth] = []
    instances[target_depth].append((instance, container))


def cleanup_prototypes_at_depth(depth: int) -> None:
    """
    특정 콜스택 깊이에서 생성된 PROTOTYPE 인스턴스들의 @PreDestroy 호출

    pop_frame 시 자동으로 호출됩니다.

    Args:
        depth: 콜스택 깊이
    """
    instances = _prototype_instances.get()
    prototypes = instances.pop(depth, None)

    # 캐시 정리 (depth=0일 때만)
    _cleanup_scoped_cache_at_depth(depth)

    if not prototypes:
        return

    # 라이프사이클 매니저를 통해 PreDestroy 호출
    from ...manager import try_get_current_manager

    manager = try_get_current_manager()
    if manager is None:
        return

    for instance, container in prototypes:
        try:
            manager.lifecycle.invoke_prototype_pre_destroy(instance, container)
        except Exception:
            pass  # PreDestroy 에러는 무시


def get_prototype_count_at_depth(depth: int) -> int:
    """특정 깊이에 등록된 PROTOTYPE 인스턴스 수 (테스트/디버깅용)"""
    instances = _prototype_instances.get()
    return len(instances.get(depth, []))


def _summarize_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """인자 요약 문자열 생성"""
    parts = []

    for arg in args[:3]:  # 최대 3개
        parts.append(_summarize_value(arg))

    if len(args) > 3:
        parts.append(f"...+{len(args) - 3}")

    for key, value in list(kwargs.items())[:2]:  # 최대 2개
        parts.append(f"{key}={_summarize_value(value)}")

    if len(kwargs) > 2:
        parts.append(f"...+{len(kwargs) - 2} kwargs")

    return ", ".join(parts)


def _summarize_value(value: Any, max_len: int = 20) -> str:
    """값 요약 문자열 생성"""
    if value is None:
        return "None"

    type_name = type(value).__name__

    if isinstance(value, str):
        if len(value) > max_len:
            return f"'{value[:max_len]}...'"
        return f"'{value}'"

    if isinstance(value, (int, float, bool)):
        return str(value)

    if isinstance(value, (list, tuple)):
        return f"{type_name}[{len(value)}]"

    if isinstance(value, dict):
        return f"dict[{len(value)}]"

    return f"<{type_name}>"


# =============================================================================
# CALL_SCOPED PROTOTYPE 캐시
# =============================================================================


def get_current_frame_id() -> str | None:
    """현재 콜스택의 최상위 핸들러 frame_id 반환"""
    stack = _call_stack.get()
    if not stack:
        return None
    # 최상위 핸들러(depth=0)의 frame_id 사용
    return stack[0].frame_id


def get_scoped_prototype(component_type: type) -> Any | None:
    """
    현재 핸들러 호출 내에서 캐시된 PROTOTYPE 인스턴스 조회

    CALL_SCOPED 스코프의 컴포넌트가 같은 핸들러 호출 내에서
    동일한 인스턴스를 반환받기 위해 사용됩니다.

    Args:
        component_type: 컴포넌트 타입

    Returns:
        캐시된 인스턴스 또는 None
    """
    frame_id = get_current_frame_id()
    if frame_id is None:
        return None

    cache = _scoped_prototype_cache.get()
    frame_cache = cache.get(frame_id)
    if frame_cache is None:
        return None

    return frame_cache.get(component_type)


def set_scoped_prototype(component_type: type, instance: Any) -> None:
    """
    현재 핸들러 호출에 PROTOTYPE 인스턴스 캐싱

    Args:
        component_type: 컴포넌트 타입
        instance: 캐시할 인스턴스
    """
    frame_id = get_current_frame_id()
    if frame_id is None:
        return

    cache = _scoped_prototype_cache.get()
    # ContextVar는 코루틴별로 격리되므로 직접 수정해도 안전
    if frame_id not in cache:
        cache[frame_id] = {}

    cache[frame_id][component_type] = instance


def _cleanup_scoped_cache_at_depth(depth: int) -> None:
    """
    특정 depth의 scoped PROTOTYPE 캐시 정리

    depth=0일 때만 캐시 정리 (핸들러 호출 종료 시)
    """
    if depth != 0:
        return

    frame_id = get_current_frame_id()
    if frame_id is None:
        return

    cache = _scoped_prototype_cache.get()
    cache.pop(frame_id, None)
