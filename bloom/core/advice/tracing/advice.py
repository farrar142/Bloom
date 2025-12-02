"""CallStackTraceAdvice - 콜스택 추적 어드바이스"""

from typing import Any, Callable, TYPE_CHECKING

from ..base import MethodAdvice
from .frame import CallFrame
from .context import push_frame, pop_frame, pop_frame_async, get_call_depth

# 성능 최적화: 모듈 수준에서 import (함수 내 동적 import 제거)
from ...events import (
    SystemEventBus,
    MethodEnteredEvent,
    MethodExitedEvent,
    MethodErrorEvent,
)

if TYPE_CHECKING:
    from ..context import InvocationContext
    from ...container import HandlerContainer
    from ...manager import ContainerManager


class CallStackTraceAdvice(MethodAdvice):
    """
    콜스택을 추적하는 기본 어드바이스

    DI 컨테이너로 생성된 클래스의 모든 메서드에 적용되어 콜스택을 기록합니다.
    상속하여 on_enter/on_exit 훅을 오버라이드하면
    로깅, 메트릭 수집, 분산 트레이싱 등을 구현할 수 있습니다.

    Example:
        @Component
        class LoggingTraceAdvice(CallStackTraceAdvice):
            logger: Logger

            def on_enter(self, frame: CallFrame) -> None:
                self.logger.debug(f"→ {frame.full_name}")

            def on_exit(self, frame: CallFrame, duration_ms: float) -> None:
                self.logger.debug(f"← {frame.full_name} ({duration_ms:.2f}ms)")

            def on_error(self, frame: CallFrame, error: Exception) -> None:
                self.logger.error(f"✗ {frame.full_name}: {error}")
    """

    # 인자 요약 포함 여부 (상속 클래스에서 오버라이드 가능)
    include_args: bool = False

    def supports(self, container: "HandlerContainer") -> bool:
        """
        모든 핸들러에 적용 (MethodAdvice 하위 클래스는 무한 재귀 방지를 위해 제외)
        """
        from ..base import MethodAdvice

        # MethodAdvice 서브클래스의 메서드는 제외 (무한 재귀 방지)
        owner_cls = getattr(container, "owner_cls", None)
        if owner_cls is not None and issubclass(owner_cls, MethodAdvice):
            return False
        return True

    # =========================================================================
    # 확장 포인트 - 상속 클래스에서 오버라이드
    # =========================================================================

    def on_enter(self, frame: CallFrame) -> None:
        """
        메서드 진입 시 호출

        Args:
            frame: 현재 콜 프레임
        """
        pass

    def on_exit(self, frame: CallFrame, duration_ms: float) -> None:
        """
        메서드 정상 종료 시 호출

        Args:
            frame: 현재 콜 프레임
            duration_ms: 실행 시간 (밀리초)
        """
        pass

    def on_error_callback(self, frame: CallFrame, error: Exception) -> None:
        """
        메서드에서 예외 발생 시 호출 (상속 클래스에서 오버라이드)

        Args:
            frame: 현재 콜 프레임
            error: 발생한 예외
        """
        pass

    # =========================================================================
    # MethodAdvice 구현
    # =========================================================================

    async def before(self, context: "InvocationContext") -> None:
        """비동기 메서드 진입 전"""
        frame = self._push_frame(context)
        context.set_attribute("_trace_frame", frame)
        self._publish_entered_event(context, frame)
        self.on_enter(frame)

    async def after(self, context: "InvocationContext", result: Any) -> Any:
        """비동기 메서드 정상 종료 후"""
        frame = await self._pop_frame_async(context)
        if frame:
            self._publish_exited_event(context, frame)
            self.on_exit(frame, frame.elapsed_ms)
        return result

    async def on_error(self, context: "InvocationContext", error: Exception) -> Any:
        """비동기 메서드 예외 발생 시"""
        frame = await self._pop_frame_async(context)
        if frame:
            self._publish_error_event(context, frame, error)
            self.on_error_callback(frame, error)
        raise error

    def before_sync(self, context: "InvocationContext") -> None:
        """동기 메서드 진입 전"""
        frame = self._push_frame(context)
        context.set_attribute("_trace_frame", frame)
        self._publish_entered_event(context, frame)
        self.on_enter(frame)

    def after_sync(self, context: "InvocationContext", result: Any) -> Any:
        """동기 메서드 정상 종료 후"""
        frame = self._pop_frame(context)
        if frame:
            self._publish_exited_event(context, frame)
            self.on_exit(frame, frame.elapsed_ms)
        return result

    def on_error_sync(self, context: "InvocationContext", error: Exception) -> Any:
        """동기 메서드 예외 발생 시"""
        frame = self._pop_frame(context)
        if frame:
            self._publish_error_event(context, frame, error)
            self.on_error_callback(frame, error)
        raise error

    # =========================================================================
    # 내부 헬퍼
    # =========================================================================

    def _push_frame(self, context: "InvocationContext") -> CallFrame:
        """프레임 생성 및 스택에 추가"""
        return push_frame(
            instance=context.instance,
            method_name=context.container.target.__name__,
            args=context.args,
            kwargs=context.kwargs,
            include_args=self.include_args,
        )

    def _pop_frame(self, context: "InvocationContext") -> CallFrame | None:
        """스택에서 프레임 제거 (동기 버전)"""
        return pop_frame()

    async def _pop_frame_async(self, context: "InvocationContext") -> CallFrame | None:
        """스택에서 프레임 제거 (비동기 버전) - CALL @PreDestroy async 지원"""
        return await pop_frame_async()

    def _get_manager(self, context: "InvocationContext") -> "ContainerManager | None":
        """ContainerManager 가져오기"""
        return context.container._get_manager()

    def _should_publish_event(self, context: "InvocationContext") -> bool:
        """이벤트 발행 여부 결정 (무한 재귀 방지)"""
        # SystemEventBus 메서드는 이벤트 발행 건너뜀 (무한 재귀 방지)
        if isinstance(context.instance, SystemEventBus):
            return False
        return True

    def _publish_entered_event(
        self, context: "InvocationContext", frame: CallFrame
    ) -> None:
        """MethodEnteredEvent 발행"""
        if not self._should_publish_event(context):
            return

        manager = self._get_manager(context)
        if manager is None:
            return

        # 리스너가 없으면 이벤트 생성도 건너뜀
        bus = manager.system_events
        if MethodEnteredEvent not in bus._handlers:
            return

        event = MethodEnteredEvent(
            frame=frame,
            instance=context.instance,
            method_name=frame.method_name,
        )
        bus.publish(event)

    def _publish_exited_event(
        self, context: "InvocationContext", frame: CallFrame
    ) -> None:
        """MethodExitedEvent 발행"""
        if not self._should_publish_event(context):
            return

        manager = self._get_manager(context)
        if manager is None:
            return

        # 리스너가 없으면 이벤트 생성도 건너뜀
        bus = manager.system_events
        if MethodExitedEvent not in bus._handlers:
            return

        event = MethodExitedEvent(
            frame=frame,
            instance=context.instance,
            method_name=frame.method_name,
            duration_ms=frame.elapsed_ms,
        )
        bus.publish(event)

    def _publish_error_event(
        self, context: "InvocationContext", frame: CallFrame, error: Exception
    ) -> None:
        """MethodErrorEvent 발행"""
        if not self._should_publish_event(context):
            return

        manager = self._get_manager(context)
        if manager is None:
            return

        # 리스너가 없으면 이벤트 생성도 건너뜀
        bus = manager.system_events
        if MethodErrorEvent not in bus._handlers:
            return

        event = MethodErrorEvent(
            frame=frame,
            instance=context.instance,
            method_name=frame.method_name,
            error=error,
        )
        bus.publish(event)
