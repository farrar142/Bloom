"""MethodProxy - 메서드 프록시"""

import asyncio
import inspect
from functools import wraps
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import MethodInvocationManager
    from ..container import HandlerContainer


class MethodProxy:
    """
    메서드 프록시 - 호출 시 Advice 체인을 실행합니다.

    Handler 데코레이터가 적용된 모든 메서드에 프록시가 적용되어,
    메서드 호출 시 자동으로 MethodInvocationManager를 거칩니다.

    동기/비동기 메서드 모두 지원:
    - 동기 메서드: __call__() → invoke_sync()
    - 비동기 메서드: __call__() → invoke() (awaitable 반환)

    Example:
        # DI 초기화 시점에 프록시 적용
        proxy = MethodProxy(
            container=handler_container,
            instance=service_instance,
            original=original_method,
            manager=invocation_manager
        )
        setattr(service_instance, 'save', proxy)

        # 호출
        service.save()  # → Advice 체인 실행 → 원본 메서드 호출
    """

    def __init__(
        self,
        container: "HandlerContainer",
        instance: Any,
        original: Callable[..., Any],
        manager: "MethodInvocationManager",
    ):
        self._container = container
        self._instance = instance
        self._original = original
        self._manager = manager
        self._is_async = asyncio.iscoroutinefunction(original)

        # 원본 메서드의 메타데이터 복사 (functools.wraps 효과)
        self.__name__ = getattr(original, "__name__", "proxy")
        self.__doc__ = getattr(original, "__doc__", None)
        self.__annotations__ = getattr(original, "__annotations__", {})
        self.__wrapped__ = original

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """
        메서드 호출 시 Advice 체인을 실행합니다.

        비동기 메서드는 코루틴을 반환하고,
        동기 메서드는 즉시 결과를 반환합니다.
        """
        if self._is_async:
            # 비동기: 코루틴 반환
            return self._invoke_async(*args, **kwargs)
        else:
            # 동기: 즉시 실행
            return self._manager.invoke_sync(
                self._container, self._instance, self._original, *args, **kwargs
            )

    async def _invoke_async(self, *args: Any, **kwargs: Any) -> Any:
        """비동기 호출"""
        return await self._manager.invoke(
            self._container, self._instance, self._original, *args, **kwargs
        )

    def __repr__(self) -> str:
        return f"<MethodProxy {self.__name__}>"

    def __get__(self, obj: Any, objtype: type | None = None) -> "MethodProxy":
        """디스크립터 프로토콜 - 인스턴스 바인딩 지원"""
        if obj is None:
            return self
        # 이미 instance가 설정되어 있으므로 self 반환
        return self
