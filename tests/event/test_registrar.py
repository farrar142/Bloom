"""이벤트 리스너 등록기 테스트"""

import pytest
from unittest.mock import MagicMock
from typing import Any

from bloom.core.event import Event, LocalEventBus
from bloom.core.event.bus import SubscriptionMode
from bloom.core.event.decorators import EventListener, SyncEventListener
from bloom.core.event.registrar import EventListenerRegistrar, EventListenerScanner


class SampleService:
    """테스트용 서비스"""

    @EventListener("user.created")
    async def on_user_created(self, event: Event):
        return f"user created: {event.payload}"

    @SyncEventListener("order.placed")
    async def on_order_placed(self, event: Event):
        return f"order placed: {event.payload}"

    @EventListener("payment.completed", priority=100)
    async def on_payment_high_priority(self, event: Event):
        return f"payment completed (high priority)"

    async def no_listener_method(self):
        return "no listener"


class AnotherService:
    """또 다른 테스트 서비스"""

    @EventListener("user.created")
    async def also_on_user_created(self, event: Event):
        return f"another handler for user created"


@pytest.fixture
def event_bus():
    """이벤트 버스 픽스처"""
    return LocalEventBus()


@pytest.fixture
def registrar(event_bus):
    """등록기 픽스처"""
    return EventListenerRegistrar(event_bus)


class TestEventListenerScanner:
    """EventListenerScanner 테스트"""

    def test_scan_class(self):
        """클래스에서 이벤트 리스너 스캔"""
        listeners = EventListenerScanner.scan_class(SampleService)

        assert len(listeners) == 3

        # 메서드 이름 확인
        method_names = {method_name for method_name, _ in listeners}
        assert method_names == {
            "on_user_created",
            "on_order_placed",
            "on_payment_high_priority",
        }

    def test_scan_empty_class(self):
        """리스너 없는 클래스 스캔"""

        class EmptyService:
            async def some_method(self):
                pass

        listeners = EventListenerScanner.scan_class(EmptyService)
        assert len(listeners) == 0

    def test_scan_with_inheritance(self):
        """상속된 클래스에서 스캔"""

        class BaseService:
            @EventListener("base.event")
            async def on_base_event(self, event: Event):
                pass

        class DerivedService(BaseService):
            @EventListener("derived.event")
            async def on_derived_event(self, event: Event):
                pass

        listeners = EventListenerScanner.scan_class(DerivedService)

        # 상속된 메서드와 자체 메서드 모두 포함
        assert len(listeners) == 2
        event_types = {info.event_type for _, info in listeners}
        assert "base.event" in event_types
        assert "derived.event" in event_types

    def test_has_listeners(self):
        """리스너 유무 확인"""
        assert EventListenerScanner.has_listeners(SampleService) is True

        class NoListenerService:
            async def method(self):
                pass

        assert EventListenerScanner.has_listeners(NoListenerService) is False


class TestEventListenerRegistrar:
    """EventListenerRegistrar 테스트"""

    @pytest.mark.asyncio
    async def test_register_instance(self, registrar, event_bus):
        """인스턴스의 이벤트 리스너 등록"""
        service = SampleService()

        subscriptions = await registrar.register_instance(service)

        assert len(subscriptions) == 3

        # 등록된 구독 확인
        all_subs = event_bus.get_subscriptions()
        event_types = {sub.event_type for sub in all_subs}
        assert "user.created" in event_types
        assert "order.placed" in event_types
        assert "payment.completed" in event_types

    @pytest.mark.asyncio
    async def test_register_multiple_instances(self, registrar, event_bus):
        """여러 인스턴스 등록"""
        service1 = SampleService()
        service2 = AnotherService()

        subs1 = await registrar.register_instance(service1)
        subs2 = await registrar.register_instance(service2)

        # user.created에 두 개의 핸들러 등록됨
        user_created_subs = [
            s for s in event_bus.get_subscriptions() if s.event_type == "user.created"
        ]
        assert len(user_created_subs) == 2

    @pytest.mark.asyncio
    async def test_unregister_instance(self, registrar, event_bus):
        """인스턴스의 이벤트 리스너 등록 해제"""
        service = SampleService()

        subscriptions = await registrar.register_instance(service)
        assert len(event_bus.get_subscriptions()) == 3

        # 등록 해제
        await registrar.unregister_instance(service)
        assert len(event_bus.get_subscriptions()) == 0

    @pytest.mark.asyncio
    async def test_priority_preserved(self, registrar, event_bus):
        """우선순위가 유지되는지 확인"""
        service = SampleService()

        await registrar.register_instance(service)

        # payment.completed 핸들러의 우선순위 확인
        payment_sub = next(
            s
            for s in event_bus.get_subscriptions()
            if s.event_type == "payment.completed"
        )
        assert payment_sub.priority == 100

    @pytest.mark.asyncio
    async def test_mode_preserved(self, registrar, event_bus):
        """구독 모드가 유지되는지 확인"""
        service = SampleService()

        await registrar.register_instance(service)

        # order.placed는 SYNC 모드여야 함
        order_sub = next(
            s for s in event_bus.get_subscriptions() if s.event_type == "order.placed"
        )
        assert order_sub.mode == SubscriptionMode.SYNC

    @pytest.mark.asyncio
    async def test_handler_execution(self, registrar, event_bus):
        """등록된 핸들러가 실제로 실행되는지 확인"""
        results = []

        class TrackingService:
            @SyncEventListener("test.event")
            async def on_test(self, event: Event):
                results.append(event.payload)

        service = TrackingService()
        await registrar.register_instance(service)

        # 이벤트 발행
        await event_bus.publish(Event(event_type="test.event", payload="test_data"))

        assert len(results) == 1
        assert results[0] == "test_data"

    @pytest.mark.asyncio
    async def test_clear_all(self, registrar, event_bus):
        """모든 등록 해제"""
        service1 = SampleService()
        service2 = AnotherService()

        await registrar.register_instance(service1)
        await registrar.register_instance(service2)

        assert len(event_bus.get_subscriptions()) == 4

        # 모두 해제
        await registrar.clear()

        assert len(event_bus.get_subscriptions()) == 0

    @pytest.mark.asyncio
    async def test_subscription_count(self, registrar):
        """등록된 구독 수 확인"""
        service = SampleService()

        assert registrar.subscription_count == 0

        await registrar.register_instance(service)

        assert registrar.subscription_count == 3
