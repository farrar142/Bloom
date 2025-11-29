"""TaskMethodAdvice - 태스크 메서드 어드바이스

@Task 데코레이터가 붙은 메서드에 백엔드를 주입합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from bloom.core.advice import InvocationContext, MethodAdvice
from bloom.core.container import HandlerContainer

from .decorator import TaskElement

if TYPE_CHECKING:
    from .backend import TaskBackend

logger = logging.getLogger(__name__)


class TaskMethodAdvice(MethodAdvice):
    """
    @Task 메서드에 백엔드를 주입하는 어드바이스

    Example:
        @Component
        class TaskConfig:
            @Factory
            def task_backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

            @Factory
            def advice_registry(self, backend: TaskBackend) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(TaskMethodAdvice(backend))
                return registry
    """

    def __init__(self, backend: TaskBackend):
        self._backend = backend

    @property
    def backend(self) -> TaskBackend:
        return self._backend

    def supports(self, container: HandlerContainer) -> bool:
        """@Task 데코레이터가 있는 메서드만 지원"""
        return container.has_element(TaskElement)

    async def before(self, context: InvocationContext) -> None:
        """인스턴스에 백엔드 주입 (동적으로 생성된 인스턴스용)"""
        instance = context.instance
        if instance is not None and not hasattr(instance, "_task_backend"):
            setattr(instance, "_task_backend", self._backend)
            logger.debug(f"TaskBackend injected to {type(instance).__name__}")

    async def after(self, context: InvocationContext, result: Any) -> Any:
        """결과 반환 (수정 없음)"""
        return result

    async def on_error(self, context: InvocationContext, error: Exception) -> Any:
        """에러 재발생"""
        raise error
