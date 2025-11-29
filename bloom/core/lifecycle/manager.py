"""LifecycleManager - 라이프사이클 관리자

Manager → Registry → Container(Entry) 패턴을 따릅니다.
"""

import asyncio
import inspect
from typing import Any, TYPE_CHECKING

from .container import LifecycleHandlerContainer, LifecycleType, LifecycleTypeElement
from .registry import LifecycleRegistry

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager
    from bloom.core.container import Container


class LifecycleManager:
    """
    애플리케이션 레벨에서 컨테이너들의 라이프사이클을 관리하는 클래스

    Manager → Registry → Container(Entry) 패턴을 따릅니다.

    - @PostConstruct: 컨테이너 인스턴스 생성 후 호출
    - @PreDestroy: 애플리케이션 종료 시 역순으로 호출
    """

    def __init__(self, container_manager: "ContainerManager"):
        self.container_manager = container_manager
        self._registry = LifecycleRegistry()

    @property
    def registry(self) -> LifecycleRegistry:
        """레지스트리 반환"""
        return self._registry

    def _find_lifecycle_handlers(
        self, container: "Container", lifecycle_type: LifecycleType
    ) -> list[LifecycleHandlerContainer]:
        """
        컨테이너의 target 클래스에서 라이프사이클 핸들러 찾기

        Registry에 캐시된 핸들러가 있으면 사용하고, 없으면 동적으로 탐색합니다.
        """
        # Registry에서 먼저 찾기
        cached = self._registry.get_handlers(container, lifecycle_type)
        if cached:
            return cached

        # 동적으로 탐색
        target = container.target
        if not isinstance(target, type):
            return []

        handlers: list[LifecycleHandlerContainer] = []
        for attr_name in dir(target):
            try:
                attr = getattr(target, attr_name, None)
            except Exception:
                continue

            if handler := LifecycleHandlerContainer.get_container(attr):
                if isinstance(handler, LifecycleHandlerContainer):
                    if handler.lifecycle_type == lifecycle_type:
                        handler.owner_cls = target
                        # Registry에 캐시
                        self._registry.register(handler)
                        handlers.append(handler)

        return handlers

    def _invoke_handler(
        self, handler: LifecycleHandlerContainer, instance: Any
    ) -> None:
        """핸들러 메서드 호출"""
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
        """
        특정 컨테이너 인스턴스의 @PostConstruct 메서드들 호출

        Args:
            container: 대상 컨테이너
            instance: 컨테이너의 인스턴스
        """
        handlers = self._find_lifecycle_handlers(
            container, LifecycleType.POST_CONSTRUCT
        )
        for handler in handlers:
            self._invoke_handler(handler, instance)

    def invoke_pre_destroy(self, container: "Container", instance: Any) -> None:
        """
        특정 컨테이너 인스턴스의 @PreDestroy 메서드들 호출

        Args:
            container: 대상 컨테이너
            instance: 컨테이너의 인스턴스
        """
        handlers = self._find_lifecycle_handlers(container, LifecycleType.PRE_DESTROY)
        for handler in handlers:
            self._invoke_handler(handler, instance)

    def invoke_all_pre_destroy(self, containers_order: list["Container"]) -> None:
        """
        모든 컨테이너의 @PreDestroy 메서드들을 역순으로 호출

        Args:
            containers_order: 초기화 순서대로 정렬된 컨테이너 리스트 (역순으로 호출됨)
        """
        for container in reversed(containers_order):
            # Container의 캐시된 인스턴스를 직접 가져옴
            instance = container._get_cached_instance()
            if instance:
                self.invoke_pre_destroy(container, instance)
