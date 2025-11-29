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
    캐시된 핸들러가 없으면 동적으로 탐색하여 캐싱합니다.
    """

    def __init__(self):
        # target 클래스 -> LifecycleHandlerContainer 리스트
        self._handlers: dict[type, list[LifecycleHandlerContainer]] = {}
        # 이미 탐색한 클래스 추적 (빈 결과도 캐싱하기 위함)
        self._scanned: set[type] = set()

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

    def find_handlers(
        self,
        container: "Container",
        lifecycle_type: LifecycleType,
    ) -> list[LifecycleHandlerContainer]:
        """
        컨테이너의 라이프사이클 핸들러 찾기

        캐시된 핸들러가 있으면 사용하고, 없으면 동적으로 탐색하여 캐싱합니다.

        Args:
            container: 대상 컨테이너
            lifecycle_type: 라이프사이클 타입
        """
        target = container.target
        if not isinstance(target, type):
            return []

        # 이미 탐색한 경우 캐시에서 반환
        if target in self._scanned:
            handlers = self._handlers.get(target, [])
            return [h for h in handlers if h.lifecycle_type == lifecycle_type]

        # 동적으로 탐색
        self._scan_handlers(target)

        handlers = self._handlers.get(target, [])
        return [h for h in handlers if h.lifecycle_type == lifecycle_type]

    def _scan_handlers(self, target: type) -> None:
        """클래스에서 라이프사이클 핸들러 탐색 및 캐싱"""
        if target in self._scanned:
            return

        self._scanned.add(target)

        for attr_name in dir(target):
            try:
                attr = getattr(target, attr_name, None)
            except Exception:
                continue

            if handler := LifecycleHandlerContainer.get_container(attr):
                if isinstance(handler, LifecycleHandlerContainer):
                    if handler.lifecycle_type is not None:
                        handler.owner_cls = target
                        self.register(handler)

    def get_handlers(
        self,
        container: "Container",
        lifecycle_type: LifecycleType | None = None,
    ) -> list[LifecycleHandlerContainer]:
        """
        특정 컨테이너의 라이프사이클 핸들러 반환 (캐시만 조회)

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
        """@PostConstruct 핸들러 찾기 (탐색 포함)"""
        return self.find_handlers(container, LifecycleType.POST_CONSTRUCT)

    def get_pre_destroy_handlers(
        self, container: "Container"
    ) -> list[LifecycleHandlerContainer]:
        """@PreDestroy 핸들러 찾기 (탐색 포함)"""
        return self.find_handlers(container, LifecycleType.PRE_DESTROY)

    def all(self) -> list[LifecycleHandlerContainer]:
        """모든 핸들러 반환"""
        handlers = []
        for handler_list in self._handlers.values():
            handlers.extend(handler_list)
        return handlers

    def clear(self) -> None:
        """모든 핸들러 제거"""
        self._handlers.clear()
        self._scanned.clear()
