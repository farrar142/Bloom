"""bloom.event.registrar - 이벤트 리스너 자동 등록

@EventListener가 붙은 메서드를 자동으로 EventBus에 등록합니다.
"""

from __future__ import annotations

import inspect
import logging
from functools import partial
from typing import Any, Callable, TYPE_CHECKING

from .bus import EventBus, SubscriptionMode, Subscription
from .decorators import (
    get_event_listeners,
    has_event_listener,
    resolve_event_type,
    EventListenerInfo,
)
from .models import Event

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager


logger = logging.getLogger(__name__)


class EventListenerRegistrar:
    """이벤트 리스너 자동 등록기

    DI 컨테이너의 컴포넌트에서 @EventListener가 붙은 메서드를 찾아
    EventBus에 자동으로 구독합니다.

    Examples:
        # ApplicationContext에서 사용
        registrar = EventListenerRegistrar(event_bus)
        await registrar.register_all(container)

        # 특정 컴포넌트만 등록
        await registrar.register_component(notification_service)
    """

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._subscriptions: list[Subscription] = []

    async def register_all(self, container: "ContainerManager") -> int:
        """컨테이너의 모든 컴포넌트에서 리스너 등록

        Args:
            container: DI 컨테이너

        Returns:
            등록된 리스너 수
        """
        registered_count = 0

        # 모든 컨테이너에서 인스턴스 가져오기
        for component_container in container.get_all_containers():
            try:
                # 컴포넌트 인스턴스 가져오기
                instance = await container.get_instance_async(
                    component_container.target
                )
                if instance is not None:
                    count = await self.register_component(instance)
                    registered_count += count
            except Exception as e:
                logger.warning(
                    f"Failed to register listeners from {component_container.target.__name__}: {e}"
                )

        logger.info(f"Registered {registered_count} event listeners")
        return registered_count

    async def register_component(self, component: Any) -> int:
        """컴포넌트의 이벤트 리스너 등록

        Args:
            component: 컴포넌트 인스턴스

        Returns:
            등록된 리스너 수
        """
        registered_count = 0
        component_name = component.__class__.__name__

        for method_name in dir(component):
            if method_name.startswith("_"):
                continue

            method = getattr(component, method_name, None)
            if not callable(method):
                continue

            if not has_event_listener(method):
                continue

            # 원본 함수 가져오기 (bound method에서)
            original_func = getattr(method, "__func__", method)
            listeners = get_event_listeners(original_func)

            for listener_info in listeners:
                try:
                    subscription = await self._register_listener(
                        component, method, listener_info
                    )
                    self._subscriptions.append(subscription)
                    registered_count += 1

                    logger.debug(
                        f"Registered listener: {component_name}.{method_name} "
                        f"for '{subscription.event_type}'"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to register listener {component_name}.{method_name}: {e}"
                    )

        return registered_count

    async def _register_listener(
        self,
        component: Any,
        method: Callable[..., Any],
        info: EventListenerInfo,
    ) -> Subscription:
        """단일 리스너 등록"""
        # 이벤트 타입 해석
        original_func = getattr(method, "__func__", method)
        event_type = resolve_event_type(info, original_func)

        # 핸들러 래퍼 생성
        async def handler_wrapper(event: Event) -> Any:
            return await self._invoke_handler(method, event)

        handler_wrapper.__name__ = f"{component.__class__.__name__}.{method.__name__}"

        # 구독
        subscription = await self._event_bus.subscribe(
            event_type,
            handler_wrapper,
            mode=info.mode,
            priority=info.priority,
            condition=info.condition,
        )

        return subscription

    async def _invoke_handler(
        self,
        method: Callable[..., Any],
        event: Event,
    ) -> Any:
        """핸들러 호출"""
        # 비동기 함수인지 확인
        if inspect.iscoroutinefunction(method):
            return await method(event)
        else:
            return method(event)

    async def register_instance(self, instance: Any) -> list[Subscription]:
        """인스턴스의 이벤트 리스너 등록 (테스트용 별칭)

        Args:
            instance: 컴포넌트 인스턴스

        Returns:
            등록된 구독 목록
        """
        before_count = len(self._subscriptions)
        await self.register_component(instance)
        return self._subscriptions[before_count:]

    async def unregister_instance(self, instance: Any) -> int:
        """인스턴스의 이벤트 리스너 해제

        Args:
            instance: 컴포넌트 인스턴스

        Returns:
            해제된 리스너 수
        """
        instance_name = instance.__class__.__name__
        count = 0
        to_remove = []

        for subscription in self._subscriptions:
            # 핸들러 이름이 인스턴스 클래스명으로 시작하는지 확인
            handler_name = subscription.handler_name or ""
            if handler_name.startswith(f"{instance_name}."):
                if await self._event_bus.unsubscribe(subscription):
                    count += 1
                to_remove.append(subscription)

        for sub in to_remove:
            self._subscriptions.remove(sub)

        return count

    async def unregister_all(self) -> int:
        """모든 등록된 리스너 해제

        Returns:
            해제된 리스너 수
        """
        count = 0
        for subscription in self._subscriptions:
            if await self._event_bus.unsubscribe(subscription):
                count += 1

        self._subscriptions.clear()
        logger.info(f"Unregistered {count} event listeners")
        return count

    async def clear(self) -> None:
        """모든 등록 해제 (별칭)"""
        await self.unregister_all()

    @property
    def subscription_count(self) -> int:
        """등록된 구독 수"""
        return len(self._subscriptions)


class EventListenerScanner:
    """이벤트 리스너 스캐너

    클래스에서 @EventListener가 붙은 메서드를 스캔합니다.
    """

    @staticmethod
    def scan_class(target_cls: type) -> list[tuple[str, EventListenerInfo]]:
        """클래스의 이벤트 리스너 스캔

        Args:
            target_cls: 스캔할 클래스

        Returns:
            (메서드명, EventListenerInfo) 튜플 리스트
        """
        results: list[tuple[str, EventListenerInfo]] = []

        for method_name in dir(target_cls):
            if method_name.startswith("_"):
                continue

            method = getattr(target_cls, method_name, None)
            if not callable(method):
                continue

            listeners = get_event_listeners(method)
            for listener_info in listeners:
                results.append((method_name, listener_info))

        return results

    @staticmethod
    def has_listeners(target_cls: type) -> bool:
        """클래스에 이벤트 리스너가 있는지 확인"""
        for method_name in dir(target_cls):
            if method_name.startswith("_"):
                continue

            method = getattr(target_cls, method_name, None)
            if callable(method) and has_event_listener(method):
                return True

        return False
