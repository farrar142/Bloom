"""LifecycleRegistry - 라이프사이클 핸들러 레지스트리

ComponentContainer별로 LifecycleHandlerContainer들을 관리합니다.
"""

from typing import TYPE_CHECKING

from .container import LifecycleHandlerContainer, LifecycleType

if TYPE_CHECKING:
    from bloom.core.container import Container


class LifecycleRegistry:
    """
    라이프사이클 핸들러 레지스트리

    ComponentContainer별로 @PostConstruct, @PreDestroy 메서드를 관리합니다.
    """

    def __init__(self):
        # target 클래스 -> LifecycleHandlerContainer 리스트
        self._handlers: dict[type, list[LifecycleHandlerContainer]] = {}

    def register(self, handler: LifecycleHandlerContainer) -> None:
        """핸들러 등록"""
        owner = handler.owner_cls
        if owner is None:
            return

        if owner not in self._handlers:
            self._handlers[owner] = []

        if handler not in self._handlers[owner]:
            self._handlers[owner].append(handler)

    def unregister(self, handler: LifecycleHandlerContainer) -> bool:
        """핸들러 등록 해제"""
        owner = handler.owner_cls
        if owner is None or owner not in self._handlers:
            return False

        if handler in self._handlers[owner]:
            self._handlers[owner].remove(handler)
            return True
        return False

    def get_handlers(
        self,
        container: "Container",
        lifecycle_type: LifecycleType | None = None,
    ) -> list[LifecycleHandlerContainer]:
        """
        특정 컨테이너의 라이프사이클 핸들러 반환

        Args:
            container: 대상 컨테이너
            lifecycle_type: 필터할 라이프사이클 타입 (None이면 모두)
        """
        target = container.target
        if not isinstance(target, type):
            return []

        handlers = self._handlers.get(target, [])

        if lifecycle_type is None:
            return handlers

        return [h for h in handlers if h.lifecycle_type == lifecycle_type]

    def get_post_construct_handlers(
        self, container: "Container"
    ) -> list[LifecycleHandlerContainer]:
        """@PostConstruct 핸들러 반환"""
        return self.get_handlers(container, LifecycleType.POST_CONSTRUCT)

    def get_pre_destroy_handlers(
        self, container: "Container"
    ) -> list[LifecycleHandlerContainer]:
        """@PreDestroy 핸들러 반환"""
        return self.get_handlers(container, LifecycleType.PRE_DESTROY)

    def all(self) -> list[LifecycleHandlerContainer]:
        """모든 핸들러 반환"""
        handlers = []
        for handler_list in self._handlers.values():
            handlers.extend(handler_list)
        return handlers

    def clear(self) -> None:
        """모든 핸들러 제거"""
        self._handlers.clear()
