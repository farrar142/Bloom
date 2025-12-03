"""bloom.core.lifecycle - 라이프사이클 관리"""

from abc import ABC, abstractmethod
from typing import Any, Callable
import asyncio


# === Lifecycle Decorators ===


def PostConstruct[F: Callable[..., Any]](func: F) -> F:
    """@PostConstruct 데코레이터 - 초기화 완료 후 호출"""
    func.__bloom_post_construct__ = True  # type: ignore
    return func


def PreDestroy[F: Callable[..., Any]](func: F) -> F:
    """@PreDestroy 데코레이터 - 소멸 전 호출"""
    func.__bloom_pre_destroy__ = True  # type: ignore
    return func


# === AutoClosable Interface ===


class AutoClosable(ABC):
    """
    자동 정리가 필요한 리소스를 위한 인터페이스.
    @PreDestroy 대신 이 인터페이스를 구현해도 라이프사이클이 자동 관리됨.

    사용 예:
        @Component
        class DatabasePool(AutoClosable):
            async def close(self):
                await self.pool.close()
    """

    @abstractmethod
    async def close(self) -> None:
        """리소스 정리. 동기 메서드로 구현해도 됨."""
        pass


# === Lifecycle Manager ===


class LifecycleManager:
    """라이프사이클 콜백 관리"""

    @staticmethod
    def get_post_construct_methods(instance: object) -> list[Callable[[], Any]]:
        """@PostConstruct 메서드 목록 반환"""
        methods: list[Callable[[], Any]] = []
        for name in dir(instance):
            if name.startswith("_"):
                continue
            try:
                method = getattr(instance, name)
                if callable(method) and getattr(
                    method, "__bloom_post_construct__", False
                ):
                    methods.append(method)
            except Exception:
                pass
        return methods

    @staticmethod
    def get_pre_destroy_methods(instance: object) -> list[Callable[[], Any]]:
        """@PreDestroy 메서드 목록 반환"""
        methods: list[Callable[[], Any]] = []
        for name in dir(instance):
            if name.startswith("_"):
                continue
            try:
                method = getattr(instance, name)
                if callable(method) and getattr(method, "__bloom_pre_destroy__", False):
                    methods.append(method)
            except Exception:
                pass
        return methods

    @staticmethod
    async def invoke_post_construct(instance: object) -> None:
        """@PostConstruct 메서드들 호출"""
        methods = LifecycleManager.get_post_construct_methods(instance)
        for method in methods:
            result = method()
            if asyncio.iscoroutine(result):
                await result

    @staticmethod
    async def invoke_pre_destroy(instance: object) -> None:
        """@PreDestroy 메서드 및 AutoClosable.close() 호출"""
        # @PreDestroy 메서드 호출
        methods = LifecycleManager.get_pre_destroy_methods(instance)
        for method in methods:
            try:
                result = method()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                # 소멸 시 예외는 로깅만 하고 계속 진행
                pass

        # AutoClosable.close() 호출
        if isinstance(instance, AutoClosable):
            try:
                result = instance.close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass

    @staticmethod
    def is_auto_closable(target: type) -> bool:
        """AutoClosable 구현 여부"""
        return issubclass(target, AutoClosable) if isinstance(target, type) else False
