"""
Advice 모듈

메서드 호출 시 Element 기반으로 before/after/on_error 훅을 실행하는 AOP 패턴입니다.

사용 예시:
    from bloom.core.advice import MethodAdvice, MethodAdviceRegistry, MethodInvocationManager

    # 1. Advice 정의
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

        async def on_error(self, context: InvocationContext, error: Exception) -> Any:
            await context.get_attribute("tx").rollback()
            raise error

    # 2. Registry/Manager 설정 (자동 주입)
    @Component
    class AdviceConfig:
        @Factory
        def invocation_manager(self, *advices: MethodAdvice) -> MethodInvocationManager:
            registry = MethodAdviceRegistry()
            for advice in advices:
                registry.register(advice)
            return MethodInvocationManager(registry)
"""

from .base import MethodAdvice
from .context import InvocationContext
from .registry import MethodAdviceRegistry
from .manager import MethodInvocationManager
from .proxy import MethodProxy

__all__ = [
    "MethodAdvice",
    "InvocationContext",
    "MethodAdviceRegistry",
    "MethodInvocationManager",
    "MethodProxy",
]
