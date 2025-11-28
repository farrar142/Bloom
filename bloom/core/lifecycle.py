"""라이프사이클 관리자"""

import asyncio
import inspect
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import ContainerManager
    from .container import Container
    from .container.handler import HandlerContainer


class LifecycleManager:
    """
    애플리케이션 레벨에서 컨테이너들의 라이프사이클을 관리하는 클래스

    ContainerManager에서 라이프사이클 관련 로직을 분리하여 단일 책임 원칙을 준수한다.
    - @PostConstruct: 컨테이너 인스턴스 생성 후 호출
    - @PreDestroy: 애플리케이션 종료 시 역순으로 호출
    """

    def __init__(self, manager: "ContainerManager"):
        self.manager = manager

    def _get_lifecycle_handlers(
        self, container: "Container", lifecycle_key: str
    ) -> list["HandlerContainer"]:
        """
        컨테이너의 target 클래스에서 특정 라이프사이클 키를 가진 HandlerContainer들을 반환

        Args:
            container: 대상 컨테이너
            lifecycle_key: "post_construct" 또는 "pre_destroy"
        """
        from .container.handler import HandlerContainer

        handlers: list[HandlerContainer] = []
        for attr_name in dir(container.target):
            try:
                attr = getattr(container.target, attr_name, None)
            except Exception:
                continue

            if handler_container := HandlerContainer.get_container(attr):
                # Element의 metadata에서 lifecycle 키 확인
                lifecycle = handler_container.get_metadata(
                    "lifecycle", raise_exception=False
                )
                if lifecycle == lifecycle_key:
                    handlers.append(handler_container)
        return handlers

    def _invoke_lifecycle_methods(
        self, container: "Container", instance: Any, lifecycle_key: str
    ) -> None:
        """특정 컨테이너의 라이프사이클 메서드들 호출"""
        handlers = self._get_lifecycle_handlers(container, lifecycle_key)
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

    def invoke_post_construct(self, container: "Container", instance: Any) -> None:
        """특정 컨테이너 인스턴스의 @PostConstruct 메서드들 호출"""
        self._invoke_lifecycle_methods(container, instance, "post_construct")

    def invoke_pre_destroy(self, container: "Container", instance: Any) -> None:
        """특정 컨테이너 인스턴스의 @PreDestroy 메서드들 호출"""
        self._invoke_lifecycle_methods(container, instance, "pre_destroy")

    def invoke_all_pre_destroy(self, containers_order: list["Container"]) -> None:
        """
        모든 컨테이너의 @PreDestroy 메서드들을 역순으로 호출

        Args:
            containers_order: 초기화 순서대로 정렬된 컨테이너 리스트 (역순으로 호출됨)
        """
        for container in reversed(containers_order):
            instance = self.manager.get_instance(
                container.target, raise_exception=False
            )
            if instance:
                self.invoke_pre_destroy(container, instance)
