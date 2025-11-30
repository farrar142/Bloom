"""
콜스택 추적 모듈

async/multithread 환경에서 안전한 콜스택 추적을 제공합니다.
ContextVar와 불변 튜플을 사용하여 각 코루틴/스레드별로 독립적인 콜스택을 관리합니다.

사용법:
    # 1. Application 설정
    app = Application("myapp", enable_tracing=True)

    # 2. 코드에서 콜스택 조회
    from bloom.core.advice.tracing import get_call_stack, get_current_frame

    @Component
    class MyService:
        def my_method(self):
            stack = get_call_stack()
            for frame in stack:
                print(f"{frame.instance_type}.{frame.method_name}")

    # 3. 커스텀 트레이싱 Advice 등록 (선택)
    @Component
    class MyTracingAdvice(CallStackTraceAdvice):
        def on_enter(self, frame: CallFrame) -> None:
            logger.info(f"Enter: {frame}")

        def on_exit(self, frame: CallFrame, duration_ms: float) -> None:
            logger.info(f"Exit: {frame} ({duration_ms:.2f}ms)")
"""

from .frame import CallFrame
from .context import (
    get_call_stack,
    get_current_frame,
    get_call_depth,
    push_frame,
    pop_frame,
    get_trace_id,
    set_trace_id,
)
from .advice import CallStackTraceAdvice

__all__ = [
    "CallFrame",
    "get_call_stack",
    "get_current_frame",
    "get_call_depth",
    "push_frame",
    "pop_frame",
    "get_trace_id",
    "set_trace_id",
    "CallStackTraceAdvice",
]
