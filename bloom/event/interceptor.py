"""bloom.event.interceptor - 이벤트 AOP 인터셉터

@EventEmitter 데코레이터를 처리하는 AOP 인터셉터입니다.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from .models import Event, create_event, get_event_type
from .decorators import get_event_emitters, EventEmitterInfo

if TYPE_CHECKING:
    from .bus import EventBus
    from bloom.core.aop.interceptor import MethodInvocation


logger = logging.getLogger(__name__)


class EventEmitterInterceptor:
    """@EventEmitter 처리 인터셉터

    메서드 실행 후 이벤트를 자동으로 발행합니다.

    Examples:
        # 인터셉터 등록
        interceptor = EventEmitterInterceptor(event_bus)
        registry.register("event_emitter", interceptor)

        # 사용
        @Component
        class UserService:
            @EventEmitter("user.created")
            async def create_user(self, name: str) -> User:
                return User(name=name)
    """

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    async def invoke(self, invocation: "MethodInvocation") -> Any:
        """메서드 실행 후 이벤트 발행"""
        # 메서드 실행
        result = await invocation.proceed()

        # EventEmitter 메타데이터 확인
        method = invocation.method
        # bound method인 경우 원본 함수에서 메타데이터 조회
        if hasattr(method, "__func__"):
            method = method.__func__
        emitters = get_event_emitters(method)

        for emitter_info in emitters:
            await self._emit_event(emitter_info, result, invocation)

        return result

    async def _emit_event(
        self,
        info: EventEmitterInfo,
        result: Any,
        invocation: "MethodInvocation",
    ) -> None:
        """이벤트 발행"""
        try:
            # 조건 체크
            if info.condition and not self._check_condition(info.condition, result):
                logger.debug(
                    f"Event emission skipped due to condition: {info.condition}"
                )
                return

            # payload 추출
            if info.payload_extractor:
                payload = info.payload_extractor(result)
            else:
                payload = result

            # 이벤트 생성
            event_type_str = get_event_type(info.event_type)

            # method 이름 추출 (bound method 지원)
            method = invocation.method
            if hasattr(method, "__func__"):
                method_name = method.__func__.__name__
            elif hasattr(method, "__name__"):
                method_name = method.__name__
            else:
                method_name = str(method)

            event = create_event(
                event_type_str,
                payload=payload,
                source=f"{invocation.target.__class__.__name__}.{method_name}",
            )

            # 이벤트 발행
            await self._event_bus.publish(event)

            logger.debug(f"Event emitted: {event_type_str}")

        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
            # 이벤트 발행 실패는 원래 메서드 결과에 영향을 주지 않음

    def _check_condition(self, condition: str, result: Any) -> bool:
        """조건 체크"""
        try:
            namespace = {"result": result}
            return bool(eval(condition, {"__builtins__": {}}, namespace))
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {condition} - {e}")
            return True
