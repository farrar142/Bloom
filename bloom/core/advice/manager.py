"""MethodInvocationManager - 메서드 호출 관리자"""

import asyncio
from typing import Any, Callable, Awaitable, TYPE_CHECKING

from .context import InvocationContext

if TYPE_CHECKING:
    from .base import MethodAdvice
    from .registry import MethodAdviceRegistry
    from ..container import HandlerContainer


class MethodInvocationManager:
    """
    메서드 호출 시 Advice 체인을 관리하는 Manager

    Container의 Element 순서에 따라 Advice를 실행합니다.

    실행 흐름:
        @Transactional  # Element 순서: 2
        @Cacheable      # Element 순서: 1
        @Post("/orders")

        Cacheable.before()
          → Transactional.before()
            → handler()
          → Transactional.after()
        → Cacheable.after()

    Example:
        @Component
        class AppConfig:
            @Factory
            def invocation_manager(
                self,
                *advices: MethodAdvice
            ) -> MethodInvocationManager:
                registry = MethodAdviceRegistry()
                for advice in advices:
                    registry.register(advice)
                return MethodInvocationManager(registry)
    """

    def __init__(self, registry: "MethodAdviceRegistry"):
        self._registry = registry

    async def invoke(
        self,
        container: "HandlerContainer",
        instance: Any,
        handler: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Advice 체인을 거쳐 핸들러를 호출합니다.

        Args:
            container: 핸들러 컨테이너
            instance: 메서드가 바인딩된 인스턴스
            handler: 실행할 핸들러 (메서드)
            *args: 위치 인자
            **kwargs: 키워드 인자

        Returns:
            핸들러 실행 결과 (Advice에 의해 수정될 수 있음)
        """
        # 적용 가능한 Advice 수집 (Element 순서대로)
        advices = self._registry.find_applicable(container)

        if not advices:
            # Advice가 없으면 직접 호출
            return await self._call_handler(handler, instance, *args, **kwargs)

        # InvocationContext 생성
        context = InvocationContext(
            container=container, instance=instance, args=args, kwargs=kwargs
        )

        return await self._execute_chain(advices, context, handler)

    async def _execute_chain(
        self,
        advices: list["MethodAdvice"],
        context: InvocationContext,
        handler: Callable[..., Any],
    ) -> Any:
        """
        Advice 체인을 실행합니다.

        before는 순서대로, after는 역순으로 실행됩니다.
        """
        executed_advices: list["MethodAdvice"] = []

        try:
            # before 훅 실행 (순서대로)
            for advice in advices:
                await advice.before(context)
                executed_advices.append(advice)

            # 핸들러 실행
            result = await self._call_handler(
                handler, context.instance, *context.args, **context.kwargs
            )

            # after 훅 실행 (역순)
            for advice in reversed(executed_advices):
                result = await advice.after(context, result)

            return result

        except Exception as error:
            # on_error 훅 실행 (역순, 실행된 것들만)
            for advice in reversed(executed_advices):
                try:
                    result = await advice.on_error(context, error)
                    # on_error가 값을 반환하면 복구된 것으로 간주
                    return result
                except Exception as e:
                    # 새로운 예외가 발생하면 계속 전파
                    error = e

            # 모든 on_error가 예외를 전파하면 최종 예외 발생
            raise error

    async def _call_handler(
        self, handler: Callable[..., Any], instance: Any, *args: Any, **kwargs: Any
    ) -> Any:
        """핸들러를 호출합니다 (동기/비동기 모두 지원)"""
        if instance is not None:
            result = handler(instance, *args, **kwargs)
        else:
            result = handler(*args, **kwargs)

        if asyncio.iscoroutine(result):
            return await result
        return result

    # === 동기 버전 ===

    def invoke_sync(
        self,
        container: "HandlerContainer",
        instance: Any,
        handler: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        동기 메서드용 Advice 체인 실행.

        before_sync, after_sync, on_error_sync를 호출합니다.

        Args:
            container: 핸들러 컨테이너
            instance: 메서드가 바인딩된 인스턴스
            handler: 실행할 핸들러 (메서드)
            *args: 위치 인자
            **kwargs: 키워드 인자

        Returns:
            핸들러 실행 결과 (Advice에 의해 수정될 수 있음)
        """
        # 적용 가능한 Advice 수집 (Element 순서대로)
        advices = self._registry.find_applicable(container)

        if not advices:
            # Advice가 없으면 직접 호출
            return self._call_handler_sync(handler, instance, *args, **kwargs)

        # InvocationContext 생성
        context = InvocationContext(
            container=container, instance=instance, args=args, kwargs=kwargs
        )

        return self._execute_chain_sync(advices, context, handler)

    def _execute_chain_sync(
        self,
        advices: list["MethodAdvice"],
        context: InvocationContext,
        handler: Callable[..., Any],
    ) -> Any:
        """
        동기 Advice 체인을 실행합니다.

        before_sync는 순서대로, after_sync는 역순으로 실행됩니다.
        """
        executed_advices: list["MethodAdvice"] = []

        try:
            # before_sync 훅 실행 (순서대로)
            for advice in advices:
                advice.before_sync(context)
                executed_advices.append(advice)

            # 핸들러 실행
            result = self._call_handler_sync(
                handler, context.instance, *context.args, **context.kwargs
            )

            # after_sync 훅 실행 (역순)
            for advice in reversed(executed_advices):
                result = advice.after_sync(context, result)

            return result

        except Exception as error:
            # on_error_sync 훅 실행 (역순, 실행된 것들만)
            for advice in reversed(executed_advices):
                try:
                    result = advice.on_error_sync(context, error)
                    # on_error_sync가 값을 반환하면 복구된 것으로 간주
                    return result
                except Exception as e:
                    # 새로운 예외가 발생하면 계속 전파
                    error = e

            # 모든 on_error_sync가 예외를 전파하면 최종 예외 발생
            raise error

    def _call_handler_sync(
        self, handler: Callable[..., Any], instance: Any, *args: Any, **kwargs: Any
    ) -> Any:
        """동기 핸들러를 호출합니다"""
        if instance is not None:
            return handler(instance, *args, **kwargs)
        else:
            return handler(*args, **kwargs)
