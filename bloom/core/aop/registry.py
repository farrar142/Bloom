"""
InterceptorRegistry: 인터셉터를 관리하는 레지스트리

타입별 인터셉터와 글로벌 인터셉터를 등록/관리.
"""

from typing import Any, Callable
from collections.abc import Awaitable
import inspect

from .interceptor import (
    MethodInterceptor,
    MethodInvocation,
    BeforeInterceptor,
    AfterInterceptor,
    AfterReturningInterceptor,
    AfterThrowingInterceptor,
    AroundInterceptor,
)
from .descriptor import MethodDescriptor, InterceptorInfo


class InterceptorRegistry:
    """
    인터셉터 레지스트리.

    인터셉터 타입에 따른 핸들러를 등록하고,
    MethodDescriptor에서 인터셉터 인스턴스를 생성.
    """

    def __init__(self):
        # 글로벌 인터셉터 (모든 메서드에 적용)
        self._global_interceptors: list[MethodInterceptor] = []

        # 타입별 인터셉터 팩토리
        # interceptor_type -> (info: InterceptorInfo) -> MethodInterceptor
        self._interceptor_factories: dict[
            str, Callable[[InterceptorInfo], MethodInterceptor | None]
        ] = {}

        # 기본 팩토리 등록
        self._register_default_factories()

    def _register_default_factories(self) -> None:
        """기본 인터셉터 팩토리 등록"""

        @self.register_factory("before")
        def before_factory(info: InterceptorInfo) -> MethodInterceptor | None:
            if info.callback is None:
                return None
            return BeforeInterceptor(info.callback, info.order)

        @self.register_factory("after")
        def after_factory(info: InterceptorInfo) -> MethodInterceptor | None:
            if info.callback is None:
                return None
            return AfterInterceptor(info.callback, info.order)

        @self.register_factory("after_returning")
        def after_returning_factory(info: InterceptorInfo) -> MethodInterceptor | None:
            if info.callback is None:
                return None
            return AfterReturningInterceptor(info.callback, info.order)

        @self.register_factory("after_throwing")
        def after_throwing_factory(info: InterceptorInfo) -> MethodInterceptor | None:
            if info.callback is None:
                return None
            exc_type = info.metadata.get("exception_type", Exception)
            return AfterThrowingInterceptor(info.callback, exc_type, info.order)

        @self.register_factory("around")
        def around_factory(info: InterceptorInfo) -> MethodInterceptor | None:
            if info.callback is None:
                return None
            return AroundInterceptor(info.callback, info.order)

    def register_factory(
        self,
        interceptor_type: str,
    ) -> Callable[
        [Callable[[InterceptorInfo], MethodInterceptor | None]],
        Callable[[InterceptorInfo], MethodInterceptor | None],
    ]:
        """인터셉터 팩토리 등록 데코레이터"""

        def decorator(
            factory: Callable[[InterceptorInfo], MethodInterceptor | None],
        ) -> Callable[[InterceptorInfo], MethodInterceptor | None]:
            self._interceptor_factories[interceptor_type] = factory
            return factory

        return decorator

    def add_global_interceptor(self, interceptor: MethodInterceptor) -> None:
        """글로벌 인터셉터 추가"""
        self._global_interceptors.append(interceptor)
        self._global_interceptors.sort(key=lambda i: i.order)

    def remove_global_interceptor(self, interceptor: MethodInterceptor) -> None:
        """글로벌 인터셉터 제거"""
        self._global_interceptors.remove(interceptor)

    def get_global_interceptors(self) -> list[MethodInterceptor]:
        """글로벌 인터셉터 목록 반환"""
        return list(self._global_interceptors)

    def create_interceptors_from_descriptor(
        self,
        descriptor: MethodDescriptor,
    ) -> list[MethodInterceptor]:
        """MethodDescriptor에서 인터셉터 인스턴스 목록 생성"""
        interceptors: list[MethodInterceptor] = []

        for info in descriptor.interceptors:
            factory = self._interceptor_factories.get(info.interceptor_type)
            if factory:
                interceptor = factory(info)
                if interceptor:
                    interceptors.append(interceptor)

        return interceptors

    def clear(self) -> None:
        """모든 인터셉터 제거 (테스트용)"""
        self._global_interceptors.clear()


# 글로벌 레지스트리 싱글톤
_global_registry: InterceptorRegistry | None = None


def get_interceptor_registry() -> InterceptorRegistry:
    """글로벌 인터셉터 레지스트리 반환"""
    global _global_registry
    if _global_registry is None:
        _global_registry = InterceptorRegistry()
    return _global_registry


def reset_interceptor_registry() -> None:
    """글로벌 레지스트리 리셋 (테스트용)"""
    global _global_registry
    if _global_registry:
        _global_registry.clear()
    _global_registry = None
