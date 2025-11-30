"""콜스택 컨텍스트 관리

ContextVar 기반으로 각 코루틴/스레드별 독립적인 콜스택을 관리합니다.
불변 튜플을 사용하여 스레드 안전성을 보장합니다.
"""

from contextvars import ContextVar
import time
import uuid
from typing import Any

from .frame import CallFrame


# 콜스택 저장 (불변 튜플로 스레드 안전)
_call_stack: ContextVar[tuple[CallFrame, ...]] = ContextVar(
    "bloom_call_stack", default=()
)

# 요청별 추적 ID
_trace_id: ContextVar[str] = ContextVar("bloom_trace_id", default="")


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

    Returns:
        제거된 CallFrame 또는 None
    """
    current_stack = _call_stack.get()
    if not current_stack:
        return None

    frame = current_stack[-1]
    # 새 튜플 생성 (불변성 유지)
    _call_stack.set(current_stack[:-1])

    return frame


def clear_stack() -> None:
    """콜스택 초기화 (요청 종료 시 사용)"""
    _call_stack.set(())
    _trace_id.set("")


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
