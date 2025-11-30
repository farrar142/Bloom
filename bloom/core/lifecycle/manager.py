"""LifecycleManager - 라이프사이클 관리자

Manager → Registry → Container(Entry) 패턴을 따릅니다.
"""

import asyncio
import inspect
from typing import Any, Callable, TYPE_CHECKING

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
      - 동기 메서드: 즉시 실행
      - 비동기 메서드: 지연 등록 후 start_async()에서 실행
    - @PreDestroy: 애플리케이션 종료 시 역순으로 호출
    """

    def __init__(self, container_manager: "ContainerManager"):
        self.container_manager = container_manager
        self._registry = LifecycleRegistry()
        # 비동기 PostConstruct 핸들러들 (지연 실행용)
        self._pending_async_post_construct: list[Callable[[], Any]] = []
        # 비동기 PreDestroy 핸들러들 (역순 실행용)
        self._pending_async_pre_destroy: list[Callable[[], Any]] = []
        # 초기화 완료 여부
        self._started = False

    @property
    def registry(self) -> LifecycleRegistry:
        """레지스트리 반환"""
        return self._registry

    @property
    def is_started(self) -> bool:
        """async 생명주기 시작 여부"""
        return self._started

    def _invoke_handler(
        self, handler: LifecycleHandlerContainer, instance: Any
    ) -> None:
        """핸들러 메서드 호출 (동기만)"""
        method = getattr(instance, handler.handler_method.__name__)
        result = method()

        # 비동기 메서드인 경우: 지연 등록
        if inspect.iscoroutine(result):
            # 코루틴을 클로저로 캡처하여 나중에 실행
            async def run_coro(coro=result):
                await coro

            self._pending_async_post_construct.append(run_coro)

    def _invoke_handler_for_destroy(
        self, handler: LifecycleHandlerContainer, instance: Any
    ) -> None:
        """PreDestroy 핸들러 메서드 호출 (동기만)"""
        method = getattr(instance, handler.handler_method.__name__)
        result = method()

        # 비동기 메서드인 경우: 지연 등록
        if inspect.iscoroutine(result):

            async def run_coro(coro=result):
                await coro

            self._pending_async_pre_destroy.append(run_coro)

    async def start_async(self) -> None:
        """
        지연된 비동기 PostConstruct 핸들러들을 실행합니다.

        ASGI lifespan startup 또는 asyncio.run() 내에서 호출해야 합니다.
        """
        if self._started:
            return

        # 등록된 순서대로 실행
        for handler in self._pending_async_post_construct:
            await handler()

        self._pending_async_post_construct.clear()
        self._started = True

    async def shutdown_async(self) -> None:
        """
        지연된 비동기 PreDestroy 핸들러들을 실행합니다.

        ASGI lifespan shutdown 또는 asyncio.run() 내에서 호출해야 합니다.
        """
        if not self._started:
            return

        # 역순으로 실행
        for handler in reversed(self._pending_async_pre_destroy):
            try:
                await handler()
            except Exception:
                pass  # PreDestroy 에러는 무시

        self._pending_async_pre_destroy.clear()
        self._started = False

    def invoke_post_construct(self, container: "Container", instance: Any) -> None:
        """
        특정 컨테이너 인스턴스의 @PostConstruct 메서드들 호출

        Args:
            container: 대상 컨테이너
            instance: 컨테이너의 인스턴스
        """
        handlers = self._registry.get_post_construct_handlers(container)
        for handler in handlers:
            self._invoke_handler(handler, instance)

    def invoke_pre_destroy(self, container: "Container", instance: Any) -> None:
        """
        특정 컨테이너 인스턴스의 @PreDestroy 메서드들 호출

        Args:
            container: 대상 컨테이너
            instance: 컨테이너의 인스턴스
        """
        handlers = self._registry.get_pre_destroy_handlers(container)
        for handler in handlers:
            self._invoke_handler_for_destroy(handler, instance)

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
