"""라이프사이클 관리자"""

import asyncio
import inspect
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Container
    from .handler import HandlerContainer


class LifecycleManager[T]:
    """
    컨테이너의 라이프사이클(@PostConstruct, @PreDestroy)을 관리하는 클래스

    Container에서 라이프사이클 관련 로직을 분리하여 단일 책임 원칙을 준수한다.
    """

    def __init__(self, container: "Container[T]"):
        self.container = container

    def _get_lifecycle_handlers(self, lifecycle_key: str) -> list["HandlerContainer"]:
        """
        클래스의 메서드 중 특정 라이프사이클 키를 가진 HandlerContainer들을 반환

        Args:
            lifecycle_key: "post_construct" 또는 "pre_destroy"
        """
        from .handler import HandlerContainer

        handlers: list[HandlerContainer] = []
        for attr_name in dir(self.container.target):
            try:
                attr = getattr(self.container.target, attr_name, None)
            except Exception:
                continue

            if container := HandlerContainer.get_container(attr):
                # Element의 metadata에서 lifecycle 키 확인
                lifecycle = container.get_metadata("lifecycle", raise_exception=False)
                if lifecycle == lifecycle_key:
                    handlers.append(container)
        return handlers

    def _invoke_lifecycle_methods(self, instance: T, lifecycle_key: str) -> None:
        """라이프사이클 메서드들 호출"""
        handlers = self._get_lifecycle_handlers(lifecycle_key)
        for handler in handlers:
            method = getattr(instance, handler.handler_method.__name__)
            result = method()
            # 비동기 메서드인 경우 실행
            if inspect.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    asyncio.run(result)

    def invoke_post_construct(self, instance: T) -> None:
        """@PostConstruct 메서드들 호출"""
        self._invoke_lifecycle_methods(instance, "post_construct")

    def invoke_pre_destroy(self, instance: T) -> None:
        """@PreDestroy 메서드들 호출"""
        self._invoke_lifecycle_methods(instance, "pre_destroy")
