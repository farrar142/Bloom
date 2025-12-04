"""bloom.event - 이벤트 시스템

이벤트 기반 아키텍처를 위한 EventBus 시스템입니다.

Features:
    - 동기/비동기 이벤트 처리
    - 우선순위 기반 핸들러 실행
    - 조건부 이벤트 처리
    - @EventListener, @EventEmitter 데코레이터
    - LocalEventBus (인메모리) / RedisEventBus (분산) 백엔드

Usage:
    # 1. 이벤트 버스 생성 및 시작
    from bloom.event import LocalEventBus, Event

    event_bus = LocalEventBus()
    await event_bus.start()

    # 2. 이벤트 구독
    @event_bus.subscribe("user.created")
    async def on_user_created(event: Event):
        print(f"User created: {event.payload}")

    # 3. 이벤트 발행
    await event_bus.publish(Event(
        event_type="user.created",
        payload={"user_id": 1, "name": "John"}
    ))

    # 4. 데코레이터 사용 (Spring-style)
    from bloom.event import EventListener, EventEmitter

    @Component
    class UserService:
        @EventEmitter("user.created")
        async def create_user(self, name: str) -> User:
            return User(name=name)

    @Component
    class NotificationService:
        @EventListener("user.created")
        async def send_welcome_email(self, event: Event):
            await self.email.send(event.payload.email, "Welcome!")
"""

from typing import TYPE_CHECKING

__all__ = [
    # Models
    "Event",
    "DomainEvent",
    "EventPriority",
    "EventStatus",
    "EventResult",
    "UserCreatedEvent",
    "UserCreatedPayload",
    "UserUpdatedEvent",
    "UserUpdatedPayload",
    "UserDeletedEvent",
    "UserDeletedPayload",
    "get_event_type",
    "create_event",
    # Bus
    "EventBus",
    "EventHandler",
    "SyncEventHandler",
    "Subscription",
    "SubscriptionGroup",
    "SubscriptionMode",
    "EventPublisher",
    # Decorators
    "EventListener",
    "SyncEventListener",
    "AsyncEventListener",
    "EventEmitter",
    "EventListenerInfo",
    "EventEmitterInfo",
    "get_event_listeners",
    "get_event_emitters",
    "has_event_listener",
    "has_event_emitter",
    "resolve_event_type",
    # Interceptor
    "EventEmitterInterceptor",
    # Registrar
    "EventListenerRegistrar",
    "EventListenerScanner",
    # Backends
    "LocalEventBus",
]


def __getattr__(name: str):
    """Lazy import"""

    # Models
    if name in (
        "Event",
        "DomainEvent",
        "EventPriority",
        "EventStatus",
        "EventResult",
        "UserCreatedEvent",
        "UserCreatedPayload",
        "UserUpdatedEvent",
        "UserUpdatedPayload",
        "UserDeletedEvent",
        "UserDeletedPayload",
        "get_event_type",
        "create_event",
    ):
        from . import models

        return getattr(models, name)

    # Bus
    if name in (
        "EventBus",
        "EventHandler",
        "SyncEventHandler",
        "Subscription",
        "SubscriptionGroup",
        "SubscriptionMode",
        "EventPublisher",
    ):
        from . import bus

        return getattr(bus, name)

    # Decorators
    if name in (
        "EventListener",
        "SyncEventListener",
        "AsyncEventListener",
        "EventEmitter",
        "EventListenerInfo",
        "EventEmitterInfo",
        "get_event_listeners",
        "get_event_emitters",
        "has_event_listener",
        "has_event_emitter",
        "resolve_event_type",
    ):
        from . import decorators

        return getattr(decorators, name)

    # Interceptor
    if name == "EventEmitterInterceptor":
        from .interceptor import EventEmitterInterceptor

        return EventEmitterInterceptor

    # Registrar
    if name in ("EventListenerRegistrar", "EventListenerScanner"):
        from . import registrar

        return getattr(registrar, name)

    # Backends
    if name == "LocalEventBus":
        from .backends import LocalEventBus

        return LocalEventBus

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# TYPE_CHECKING용 (IDE 지원)
if TYPE_CHECKING:
    from .models import (
        Event,
        DomainEvent,
        EventPriority,
        EventStatus,
        EventResult,
        UserCreatedEvent,
        UserCreatedPayload,
        UserUpdatedEvent,
        UserUpdatedPayload,
        UserDeletedEvent,
        UserDeletedPayload,
        get_event_type,
        create_event,
    )
    from .bus import (
        EventBus,
        EventHandler,
        SyncEventHandler,
        Subscription,
        SubscriptionGroup,
        SubscriptionMode,
        EventPublisher,
    )
    from .decorators import (
        EventListener,
        SyncEventListener,
        AsyncEventListener,
        EventEmitter,
        EventListenerInfo,
        EventEmitterInfo,
        get_event_listeners,
        get_event_emitters,
        has_event_listener,
        has_event_emitter,
        resolve_event_type,
    )
    from .interceptor import EventEmitterInterceptor
    from .registrar import EventListenerRegistrar, EventListenerScanner
    from .backends import LocalEventBus
