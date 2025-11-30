"""
이벤트 시스템 모듈

시스템 이벤트와 애플리케이션 이벤트를 동일한 추상 계층으로 제공합니다.

- SystemEvent: 프레임워크 내부 이벤트 (인스턴스 생성, 메서드 호출 등)
- DomainEvent: 비즈니스 도메인 이벤트 (주문 생성, 사용자 등록 등)

사용 예시:
    # 시스템 이벤트 구독
    @Component
    class LifecycleLogger:
        system_events: SystemEventBus

        @PostConstruct
        def setup(self):
            self.system_events.subscribe(InstanceCreatedEvent, self.on_created)

        def on_created(self, event: InstanceCreatedEvent):
            print(f"Created: {event.instance_type}")

    # 애플리케이션 이벤트 발행/구독
    @Component
    class OrderService:
        event_bus: ApplicationEventBus

        def create_order(self, data):
            order = Order(**data)
            self.event_bus.publish(OrderCreatedEvent(order))

    @Component
    class EmailService:
        @EventListener(OrderCreatedEvent)
        def on_order_created(self, event: OrderCreatedEvent):
            self.send_email(event.order.email)
"""

from .base import Event, EventBus, InMemoryEventBus
from .system import (
    SystemEvent,
    SystemEventBus,
    ContainerRegisteredEvent,
    InstanceCreatedEvent,
    InstanceDestroyingEvent,
    MethodEnteredEvent,
    MethodExitedEvent,
    MethodErrorEvent,
)
from .application import (
    DomainEvent,
    ApplicationEventBus,
    EventListener,
    EventListenerElement,
    is_event_listener,
    get_event_listener_type,
)

__all__ = [
    # Base
    "Event",
    "EventBus",
    "InMemoryEventBus",
    # System Events
    "SystemEvent",
    "SystemEventBus",
    "ContainerRegisteredEvent",
    "InstanceCreatedEvent",
    "InstanceDestroyingEvent",
    "MethodEnteredEvent",
    "MethodExitedEvent",
    "MethodErrorEvent",
    # Application Events
    "DomainEvent",
    "ApplicationEventBus",
    "EventListener",
    "EventListenerElement",
    "is_event_listener",
    "get_event_listener_type",
]
