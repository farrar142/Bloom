"""이벤트 시스템 테스트"""

import pytest
from dataclasses import dataclass

from bloom import Application, Component
from bloom.core.decorators import PostConstruct
from bloom.core.events import (
    Event,
    EventBus,
    InMemoryEventBus,
    SystemEvent,
    SystemEventBus,
    DomainEvent,
    ApplicationEventBus,
    EventListener,
    InstanceCreatedEvent,
    MethodEnteredEvent,
)


# =============================================================================
# 베이스 클래스 테스트
# =============================================================================


class TestInMemoryEventBus:
    """InMemoryEventBus 단위 테스트"""

    async def test_publish_and_subscribe(self):
        """이벤트 발행 및 구독"""

        @dataclass
        class TestEvent(Event):
            value: str = ""

        bus = InMemoryEventBus[TestEvent]()
        received = []

        def handler(event: TestEvent):
            received.append(event.value)

        bus.subscribe(TestEvent, handler)
        bus.publish(TestEvent(value="hello"))

        assert received == ["hello"]

    async def test_multiple_handlers(self):
        """여러 핸들러 구독"""

        @dataclass
        class TestEvent(Event):
            value: int = 0

        bus = InMemoryEventBus[TestEvent]()
        results = []

        def handler1(event: TestEvent):
            results.append(event.value * 2)

        def handler2(event: TestEvent):
            results.append(event.value * 3)

        bus.subscribe(TestEvent, handler1)
        bus.subscribe(TestEvent, handler2)
        bus.publish(TestEvent(value=5))

        assert 10 in results
        assert 15 in results

    async def test_inheritance_handler(self):
        """부모 타입 핸들러도 호출"""

        @dataclass
        class ParentEvent(Event):
            pass

        @dataclass
        class ChildEvent(ParentEvent):
            value: str = ""

        bus = InMemoryEventBus[Event]()
        parent_received = []
        child_received = []

        def parent_handler(event: Event):
            parent_received.append(event)

        def child_handler(event: Event):
            if isinstance(event, ChildEvent):
                child_received.append(event.value)

        bus.subscribe(ParentEvent, parent_handler)
        bus.subscribe(ChildEvent, child_handler)

        child_event = ChildEvent(value="test")
        bus.publish(child_event)

        # ChildEvent 발행 시 ParentEvent 핸들러도 호출됨
        assert len(parent_received) == 1
        assert len(child_received) == 1
        assert child_received[0] == "test"

    async def test_unsubscribe(self):
        """구독 해제"""

        @dataclass
        class TestEvent(Event):
            pass

        bus = InMemoryEventBus[TestEvent]()
        called = []

        def handler(event: TestEvent):
            called.append(True)

        bus.subscribe(TestEvent, handler)
        bus.publish(TestEvent())
        assert len(called) == 1

        bus.unsubscribe(TestEvent, handler)
        bus.publish(TestEvent())
        assert len(called) == 1  # 더 이상 호출되지 않음

    async def test_clear(self):
        """모든 구독 해제"""

        @dataclass
        class TestEvent(Event):
            pass

        bus = InMemoryEventBus[TestEvent]()
        bus.subscribe(TestEvent, lambda e: None)
        bus.subscribe(TestEvent, lambda e: None)

        assert len(bus) == 2
        bus.clear()
        assert len(bus) == 0


# =============================================================================
# 시스템 이벤트 테스트
# =============================================================================


class TestSystemEventBus:
    """SystemEventBus DI 통합 테스트"""

    async def test_system_event_bus_injectable(self):
        """SystemEventBus를 DI로 주입받을 수 있음"""

        received_events = []

        @Component
        class EventLogger:
            system_events: SystemEventBus

            @PostConstruct
            def setup(self):
                self.system_events.subscribe(
                    InstanceCreatedEvent, self.on_created  # type: ignore
                )

            def on_created(self, event: InstanceCreatedEvent):
                received_events.append(event.instance_type.__name__)

        @Component
        class SomeService:
            pass

        app = Application("test_system_events")
        app.scan(EventLogger)
        app.scan(SomeService)
        await app.ready_async()

        # EventLogger가 주입받은 SystemEventBus 확인
        logger = app.manager.get_instance(EventLogger)
        assert logger.system_events is not None
        assert isinstance(logger.system_events, SystemEventBus)


# =============================================================================
# 애플리케이션 이벤트 테스트
# =============================================================================


class TestApplicationEventBus:
    """ApplicationEventBus DI 통합 테스트"""

    async def test_application_event_bus_injectable(self):
        """ApplicationEventBus를 DI로 주입받을 수 있음"""

        @Component
        class Publisher:
            event_bus: ApplicationEventBus

        app = Application("test_app_events")
        app.scan(Publisher)
        await app.ready_async()

        publisher = app.manager.get_instance(Publisher)
        assert publisher.event_bus is not None
        assert isinstance(publisher.event_bus, ApplicationEventBus)

    async def test_event_listener_decorator(self):
        """@EventListener 데코레이터로 이벤트 구독"""

        @dataclass
        class OrderCreatedEvent(DomainEvent):
            order_id: str = ""

        received = []

        @Component
        class OrderService:
            event_bus: ApplicationEventBus

            def create_order(self, order_id: str):
                self.event_bus.publish(OrderCreatedEvent(order_id=order_id))

        @Component
        class EmailService:
            @EventListener(OrderCreatedEvent)
            def on_order_created(self, event: OrderCreatedEvent):
                received.append(f"email:{event.order_id}")

        @Component
        class InventoryService:
            @EventListener(OrderCreatedEvent)
            def on_order_created(self, event: OrderCreatedEvent):
                received.append(f"inventory:{event.order_id}")

        app = Application("test_event_listener")
        app.scan(OrderService)
        app.scan(EmailService)
        app.scan(InventoryService)
        await app.ready_async()

        # 주문 생성
        order_service = app.manager.get_instance(OrderService)
        order_service.create_order("ORD-001")

        # 두 서비스 모두 이벤트 수신
        assert "email:ORD-001" in received
        assert "inventory:ORD-001" in received

    async def test_multiple_events(self):
        """여러 종류의 이벤트 처리"""

        @dataclass
        class UserRegisteredEvent(DomainEvent):
            user_id: str = ""

        @dataclass
        class UserDeletedEvent(DomainEvent):
            user_id: str = ""

        log = []

        @Component
        class AuditService:
            @EventListener(UserRegisteredEvent)
            def on_registered(self, event: UserRegisteredEvent):
                log.append(f"registered:{event.user_id}")

            @EventListener(UserDeletedEvent)
            def on_deleted(self, event: UserDeletedEvent):
                log.append(f"deleted:{event.user_id}")

        @Component
        class UserService:
            event_bus: ApplicationEventBus

            def register(self, user_id: str):
                self.event_bus.publish(UserRegisteredEvent(user_id=user_id))

            def delete(self, user_id: str):
                self.event_bus.publish(UserDeletedEvent(user_id=user_id))

        app = Application("test_multi_events")
        app.scan(AuditService)
        app.scan(UserService)
        await app.ready_async()

        user_service = app.manager.get_instance(UserService)
        user_service.register("user-1")
        user_service.delete("user-2")

        assert log == ["registered:user-1", "deleted:user-2"]


# =============================================================================
# 시스템 이벤트와 애플리케이션 이벤트 동시 사용
# =============================================================================


class TestMixedEvents:
    """시스템 이벤트와 애플리케이션 이벤트 혼합 사용"""

    async def test_both_event_buses_available(self):
        """두 이벤트 버스 모두 주입 가능"""

        @Component
        class MixedService:
            system_events: SystemEventBus
            app_events: ApplicationEventBus

        app = Application("test_mixed")
        app.scan(MixedService)
        await app.ready_async()

        service = app.manager.get_instance(MixedService)
        assert service.system_events is not None
        assert service.app_events is not None
        assert service.system_events is not service.app_events


# =============================================================================
# 커스텀 ApplicationEventBus (@Factory로 생성)
# =============================================================================


class TestCustomApplicationEventBus:
    """사용자가 @Factory로 커스텀 ApplicationEventBus를 생성"""

    async def test_factory_creates_custom_event_bus(self):
        """@Factory로 생성한 ApplicationEventBus가 사용됨"""
        from bloom.core.decorators import Factory

        # 커스텀 이벤트 버스 (로깅 등 추가 기능)
        class CustomEventBus(ApplicationEventBus):
            def __init__(self):
                super().__init__()
                self.published_events: list[DomainEvent] = []

            def publish(self, event: DomainEvent) -> None:
                self.published_events.append(event)
                super().publish(event)

        @dataclass
        class TestEvent(DomainEvent):
            message: str = ""

        @Component
        class EventBusConfig:
            @Factory
            def event_bus(self) -> ApplicationEventBus:
                return CustomEventBus()

        @Component
        class Publisher:
            event_bus: ApplicationEventBus

            def emit(self, message: str):
                self.event_bus.publish(TestEvent(message=message))

        app = Application("test_custom_bus")
        app.scan(EventBusConfig)
        app.scan(Publisher)
        await app.ready_async()

        publisher = app.manager.get_instance(Publisher)
        publisher.emit("hello")

        # CustomEventBus가 사용되었는지 확인
        event_bus = app.manager.get_instance(ApplicationEventBus)
        assert isinstance(event_bus, CustomEventBus)
        assert len(event_bus.published_events) == 1
        # TestEvent로 캐스팅하여 message 접근
        published = event_bus.published_events[0]
        assert isinstance(published, TestEvent)
        assert published.message == "hello"

    async def test_default_event_bus_when_no_factory(self):
        """@Factory가 없으면 기본 ApplicationEventBus 생성"""

        @Component
        class SimpleService:
            event_bus: ApplicationEventBus

        app = Application("test_default_bus")
        app.scan(SimpleService)
        await app.ready_async()

        service = app.manager.get_instance(SimpleService)
        assert service.event_bus is not None
        assert type(service.event_bus) is ApplicationEventBus  # 정확히 기본 타입
