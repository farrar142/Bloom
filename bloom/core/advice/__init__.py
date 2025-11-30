"""
Advice 모듈

메서드 호출 시 Element 기반으로 before/after/on_error 훅을 실행하는 AOP 패턴입니다.

- MethodAdvice: @Component로 등록
- MethodAdviceRegistry: @Factory로 생성하여 Advice들을 수집
- MethodInvocationManager: Application에서 생성, Registry를 조회하여 사용

사용 예시:
    from bloom.core.advice import MethodAdvice, MethodAdviceRegistry

    # 1. Advice 정의 (@Component로 등록)
    @Component
    class TransactionAdvice(MethodAdvice):
        db: Database

        def supports(self, container: HandlerContainer) -> bool:
            return container.has_element(TransactionalElement)

        async def before(self, context: InvocationContext) -> None:
            tx = await self.db.begin()
            context.set_attribute("tx", tx)

        async def after(self, context: InvocationContext, result: Any) -> Any:
            await context.get_attribute("tx").commit()
            return result

    # 2. Registry 생성 (@Factory로 Advice들 수집)
    @Component
    class AdviceConfig:
        @Factory
        def advice_registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
            registry = MethodAdviceRegistry()
            for advice in advices:
                registry.register(advice)
            return registry
"""

from .base import MethodAdvice
from .context import InvocationContext
from .registry import MethodAdviceRegistry
from .manager import MethodInvocationManager
from .proxy import MethodProxy
from .tracing import (
    CallFrame,
    CallStackTraceAdvice,
    get_call_stack,
    get_current_frame,
    get_call_depth,
    get_trace_id,
    set_trace_id,
)

__all__ = [
    "MethodAdvice",
    "InvocationContext",
    "MethodAdviceRegistry",
    "MethodInvocationManager",
    "MethodProxy",
    # Tracing
    "CallFrame",
    "CallStackTraceAdvice",
    "get_call_stack",
    "get_current_frame",
    "get_call_depth",
    "get_trace_id",
    "set_trace_id",
]
