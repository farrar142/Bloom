"""콜스택 추적 테스트"""

import asyncio
import pytest

from bloom import Application, Component
from bloom.core.decorators import Factory, Handler
from bloom.core.advice import (
    MethodAdvice,
    MethodAdviceRegistry,
    CallFrame,
    CallStackTraceAdvice,
    get_call_stack,
    get_current_frame,
    get_call_depth,
    get_trace_id,
    set_trace_id,
)
from bloom.core.advice.tracing.context import clear_stack


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_tracing():
    """각 테스트 전후로 트레이싱 상태 초기화"""
    clear_stack()
    yield
    clear_stack()


# =============================================================================
# CallFrame 테스트
# =============================================================================


class TestCallFrame:
    """CallFrame 단위 테스트"""

    def test_create_frame(self):
        """CallFrame 생성"""
        import time

        frame = CallFrame(
            instance_type="MyService",
            method_name="my_method",
            start_time=time.time(),
            trace_id="abc123",
            depth=0,
        )

        assert frame.instance_type == "MyService"
        assert frame.method_name == "my_method"
        assert frame.trace_id == "abc123"
        assert frame.depth == 0
        assert frame.full_name == "MyService.my_method"

    def test_frame_is_immutable(self):
        """CallFrame은 불변"""
        import time

        frame = CallFrame(
            instance_type="MyService",
            method_name="my_method",
            start_time=time.time(),
            trace_id="abc123",
            depth=0,
        )

        with pytest.raises(AttributeError):
            frame.depth = 1  # type: ignore

    def test_frame_elapsed_time(self):
        """경과 시간 계산"""
        import time

        start = time.time()
        frame = CallFrame(
            instance_type="MyService",
            method_name="my_method",
            start_time=start,
            trace_id="abc123",
            depth=0,
        )

        time.sleep(0.01)  # 10ms
        elapsed = frame.elapsed_ms
        assert elapsed >= 10  # 최소 10ms


# =============================================================================
# Context API 테스트
# =============================================================================


class TestContextAPI:
    """콜스택 컨텍스트 API 테스트"""

    def test_empty_stack(self):
        """빈 스택"""
        assert get_call_stack() == ()
        assert get_current_frame() is None
        assert get_call_depth() == 0

    def test_push_and_pop(self):
        """프레임 push/pop"""
        from bloom.core.advice.tracing.context import push_frame, pop_frame

        class FakeService:
            pass

        instance = FakeService()

        # Push
        frame1 = push_frame(instance, "method1")
        assert get_call_depth() == 1
        assert get_current_frame() == frame1
        assert frame1.depth == 0

        frame2 = push_frame(instance, "method2")
        assert get_call_depth() == 2
        assert get_current_frame() == frame2
        assert frame2.depth == 1

        # Pop
        popped = pop_frame()
        assert popped == frame2
        assert get_call_depth() == 1
        assert get_current_frame() == frame1

        popped = pop_frame()
        assert popped == frame1
        assert get_call_depth() == 0

    def test_trace_id(self):
        """추적 ID 관리"""
        assert get_trace_id() == ""

        # 자동 생성
        tid = set_trace_id()
        assert len(tid) == 8
        assert get_trace_id() == tid

        # 수동 설정
        set_trace_id("my-trace-123")
        assert get_trace_id() == "my-trace-123"


# =============================================================================
# 멀티 코루틴 독립성 테스트
# =============================================================================


class TestAsyncIsolation:
    """async 환경에서 콜스택 독립성 테스트"""

    @pytest.mark.asyncio
    async def test_concurrent_coroutines_have_independent_stacks(self):
        """동시 실행 코루틴들이 독립적인 콜스택을 가짐"""
        from bloom.core.advice.tracing.context import push_frame, pop_frame

        results = {}

        class ServiceA:
            pass

        class ServiceB:
            pass

        async def coroutine_a():
            set_trace_id("trace-A")
            instance = ServiceA()

            push_frame(instance, "method_a1")
            await asyncio.sleep(0.01)  # 다른 코루틴에게 양보

            push_frame(instance, "method_a2")
            await asyncio.sleep(0.01)

            # 이 시점에서 A의 스택만 2개여야 함
            results["a_depth"] = get_call_depth()
            results["a_trace"] = get_trace_id()
            results["a_stack"] = tuple(f.method_name for f in get_call_stack())

            pop_frame()
            pop_frame()

        async def coroutine_b():
            set_trace_id("trace-B")
            instance = ServiceB()

            push_frame(instance, "method_b1")
            await asyncio.sleep(0.015)  # A보다 늦게 체크

            # 이 시점에서 B의 스택만 1개여야 함
            results["b_depth"] = get_call_depth()
            results["b_trace"] = get_trace_id()
            results["b_stack"] = tuple(f.method_name for f in get_call_stack())

            pop_frame()

        # 동시 실행
        await asyncio.gather(coroutine_a(), coroutine_b())

        # 검증: 각 코루틴이 독립적인 스택을 가짐
        assert results["a_depth"] == 2
        assert results["a_trace"] == "trace-A"
        assert results["a_stack"] == ("method_a1", "method_a2")

        assert results["b_depth"] == 1
        assert results["b_trace"] == "trace-B"
        assert results["b_stack"] == ("method_b1",)


# =============================================================================
# CallStackTraceAdvice 통합 테스트
# =============================================================================


class TestCallStackTraceAdviceIntegration:
    """CallStackTraceAdvice 통합 테스트"""

    def test_tracing_with_di(self):
        """DI 컨테이너와 통합 테스트"""

        # 호출 기록
        call_log: list[str] = []

        @Component
        class TracingAdvice(CallStackTraceAdvice):
            include_args = True

            def on_enter(self, frame: CallFrame) -> None:
                call_log.append(f"enter:{frame.full_name}")

            def on_exit(self, frame: CallFrame, duration_ms: float) -> None:
                call_log.append(f"exit:{frame.full_name}")

        @Component
        class InnerService:
            @Handler
            def inner_method(self, value: int) -> int:
                return value * 2

        @Component
        class OuterService:
            inner: InnerService

            @Handler
            def outer_method(self, value: int) -> int:
                return self.inner.inner_method(value) + 1

        @Component
        class AdviceConfig:
            @Factory
            def registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
                reg = MethodAdviceRegistry()
                for a in advices:
                    reg.register(a)
                return reg

        # 앱 초기화
        app = Application("test_tracing")
        app.scan(TracingAdvice)
        app.scan(InnerService)
        app.scan(OuterService)
        app.scan(AdviceConfig)
        app.ready()

        # 실행
        outer = app.manager.get_instance(OuterService)
        result = outer.outer_method(5)

        # 검증
        assert result == 11  # (5 * 2) + 1

        # 콜스택 추적 확인
        assert "enter:OuterService.outer_method" in call_log
        assert "enter:InnerService.inner_method" in call_log
        assert "exit:InnerService.inner_method" in call_log
        assert "exit:OuterService.outer_method" in call_log

        # 순서 확인 (outer 진입 → inner 진입 → inner 종료 → outer 종료)
        outer_enter_idx = call_log.index("enter:OuterService.outer_method")
        inner_enter_idx = call_log.index("enter:InnerService.inner_method")
        inner_exit_idx = call_log.index("exit:InnerService.inner_method")
        outer_exit_idx = call_log.index("exit:OuterService.outer_method")

        assert outer_enter_idx < inner_enter_idx < inner_exit_idx < outer_exit_idx


# =============================================================================
# Args Summary 테스트
# =============================================================================


class TestArgsSummary:
    """인자 요약 기능 테스트"""

    def test_summarize_args(self):
        """인자 요약 문자열 생성"""
        from bloom.core.advice.tracing.context import _summarize_args

        # 기본 타입
        assert _summarize_args((1, "hello", True), {}) == "1, 'hello', True"

        # 긴 문자열 truncate
        long_str = "a" * 100
        result = _summarize_args((long_str,), {})
        assert "..." in result
        assert len(result) < 50

        # 컬렉션
        assert _summarize_args(([1, 2, 3],), {}) == "list[3]"
        assert _summarize_args(((1, 2),), {}) == "tuple[2]"
        assert _summarize_args(({"a": 1},), {}) == "dict[1]"

        # kwargs
        assert "key=" in _summarize_args((), {"key": "value"})

        # 너무 많은 인자
        result = _summarize_args((1, 2, 3, 4, 5), {})
        assert "...+2" in result
