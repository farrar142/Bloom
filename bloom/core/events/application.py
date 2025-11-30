"""애플리케이션 이벤트 정의

비즈니스 도메인에서 사용하는 이벤트들입니다.
@EventListener 데코레이터로 이벤트를 구독할 수 있습니다.
"""

from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

from .base import Event, InMemoryEventBus
from ..container import HandlerContainer
from ..container.element import Element

if TYPE_CHECKING:
    pass


# =============================================================================
# 도메인 이벤트 베이스
# =============================================================================


@dataclass
class DomainEvent(Event):
    """
    도메인 이벤트 베이스 클래스
    
    비즈니스 로직에서 발생하는 이벤트의 베이스입니다.
    
    사용 예시:
        @dataclass
        class OrderCreatedEvent(DomainEvent):
            order_id: str
            customer_id: str
            total_amount: float
    """
    pass


# =============================================================================
# EventListenerElement
# =============================================================================


class EventListenerElement(Element):
    """
    이벤트 리스너 메타데이터를 저장하는 Element
    
    HandlerContainer에 추가되어 이벤트 리스너 정보를 저장합니다.
    """
    key = "event_listener"

    def __init__(self, event_type: type[Event]):
        super().__init__()
        self.metadata["event_type"] = event_type

    @property
    def event_type(self) -> type[Event]:
        return self.metadata["event_type"]


# =============================================================================
# @EventListener 데코레이터
# =============================================================================


def EventListener(event_type: type[Event]) -> Callable[[Callable], Callable]:
    """
    이벤트 리스너 데코레이터
    
    메서드를 특정 이벤트 타입의 리스너로 등록합니다.
    Application 초기화 시 자동으로 ApplicationEventBus에 구독됩니다.
    
    Args:
        event_type: 구독할 이벤트 타입
    
    사용 예시:
        @Component
        class EmailService:
            @EventListener(OrderCreatedEvent)
            def on_order_created(self, event: OrderCreatedEvent):
                self.send_confirmation_email(event.customer_id)
    """
    def decorator(method: Callable) -> Callable:
        # HandlerContainer에 EventListenerElement 추가
        container = HandlerContainer.get_or_create(method)
        container.add_elements(EventListenerElement(event_type))
        return method
    return decorator


def is_event_listener(method: Any) -> bool:
    """메서드가 @EventListener로 장식되었는지 확인"""
    container = HandlerContainer.get_container(method)
    if container is None:
        return False
    return container.has_element(EventListenerElement)


def get_event_listener_type(method: Any) -> type[Event] | None:
    """@EventListener로 등록된 이벤트 타입 반환"""
    container = HandlerContainer.get_container(method)
    if container is None:
        return None
    event_types = container.get_metadatas("event_type")
    return event_types[0] if event_types else None


# =============================================================================
# 애플리케이션 이벤트 버스
# =============================================================================


class ApplicationEventBus(InMemoryEventBus[DomainEvent]):
    """
    애플리케이션 이벤트 버스
    
    비즈니스 도메인 이벤트를 발행하고 구독하는 버스입니다.
    @Component로 DI 컨테이너에 등록되어 주입받아 사용합니다.
    
    사용 예시:
        @Component
        class OrderService:
            event_bus: ApplicationEventBus
            
            def create_order(self, data: dict) -> Order:
                order = Order(**data)
                self.order_repo.save(order)
                
                # 이벤트 발행
                self.event_bus.publish(OrderCreatedEvent(
                    order_id=order.id,
                    customer_id=order.customer_id,
                    total_amount=order.total
                ))
                
                return order
        
        @Component
        class EmailService:
            @EventListener(OrderCreatedEvent)
            def on_order_created(self, event: OrderCreatedEvent):
                self.send_confirmation_email(event.customer_id)
        
        @Component
        class InventoryService:
            @EventListener(OrderCreatedEvent)
            def on_order_created(self, event: OrderCreatedEvent):
                self.decrease_stock(event.order_id)
    """
    pass
