"""이벤트 데코레이터 테스트"""

import pytest
from typing import Any
from dataclasses import dataclass

from bloom.core.event import (
    Event,
    DomainEvent,
    EventListener,
    SyncEventListener,
    AsyncEventListener,
    EventEmitter,
    SubscriptionMode,
    get_event_listeners,
    get_event_emitters,
    has_event_listener,
    has_event_emitter,
    resolve_event_type,
    EventListenerInfo,
)


class TestEventListenerDecorator:
    """@EventListener 데코레이터 테스트"""

    def test_basic_decoration(self):
        """기본 데코레이션"""

        @EventListener("user.created")
        async def on_user_created(event: Event):
            pass

        assert has_event_listener(on_user_created)
        listeners = get_event_listeners(on_user_created)
        assert len(listeners) == 1

        info = listeners[0]
        assert info.event_type == "user.created"
        assert info.mode == SubscriptionMode.ASYNC
        assert info.priority == 0
        assert info.condition is None

    def test_sync_mode(self):
        """동기 모드 설정"""

        @EventListener("order.created", mode=SubscriptionMode.SYNC)
        async def on_order_created(event: Event):
            pass

        info = get_event_listeners(on_order_created)[0]
        assert info.mode == SubscriptionMode.SYNC

    def test_priority(self):
        """우선순위 설정"""

        @EventListener("test.event", priority=100)
        async def high_priority_handler(event: Event):
            pass

        info = get_event_listeners(high_priority_handler)[0]
        assert info.priority == 100

    def test_condition(self):
        """조건 설정"""

        @EventListener("order.created", condition="payload.total > 10000")
        async def on_large_order(event: Event):
            pass

        info = get_event_listeners(on_large_order)[0]
        assert info.condition == "payload.total > 10000"

    def test_multiple_listeners(self):
        """다중 리스너"""

        @EventListener("event.a")
        @EventListener("event.b")
        async def multi_handler(event: Event):
            pass

        listeners = get_event_listeners(multi_handler)
        assert len(listeners) == 2
        event_types = {l.event_type for l in listeners}
        assert event_types == {"event.a", "event.b"}

    def test_class_type_event(self):
        """클래스 타입 이벤트"""

        @dataclass
        class UserCreatedEvent(DomainEvent):
            event_type: str = "user.created"

        @EventListener(UserCreatedEvent)
        async def on_user_created(event: UserCreatedEvent):
            pass

        info = get_event_listeners(on_user_created)[0]
        assert info.event_type == UserCreatedEvent


class TestSyncAsyncEventListenerShortcuts:
    """SyncEventListener/AsyncEventListener 축약 데코레이터 테스트"""

    def test_sync_event_listener(self):
        """@SyncEventListener"""

        @SyncEventListener("test.event")
        async def handler(event: Event):
            pass

        info = get_event_listeners(handler)[0]
        assert info.mode == SubscriptionMode.SYNC

    def test_async_event_listener(self):
        """@AsyncEventListener"""

        @AsyncEventListener("test.event")
        async def handler(event: Event):
            pass

        info = get_event_listeners(handler)[0]
        assert info.mode == SubscriptionMode.ASYNC


class TestEventEmitterDecorator:
    """@EventEmitter 데코레이터 테스트"""

    def test_basic_decoration(self):
        """기본 데코레이션"""

        @EventEmitter("user.created")
        async def create_user(name: str):
            return {"id": 1, "name": name}

        assert has_event_emitter(create_user)
        emitters = get_event_emitters(create_user)
        assert len(emitters) == 1

        info = emitters[0]
        assert info.event_type == "user.created"
        assert info.condition is None
        assert info.payload_extractor is None

    def test_condition(self):
        """조건부 발행"""

        @EventEmitter("order.large", condition="result.total > 10000")
        async def create_order(items: list):
            return {"total": sum(items)}

        info = get_event_emitters(create_order)[0]
        assert info.condition == "result.total > 10000"

    def test_payload_extractor(self):
        """페이로드 추출기"""

        @EventEmitter(
            "user.updated",
            payload_extractor=lambda u: {"id": u["id"], "name": u["name"]},
        )
        async def update_user(user: dict):
            return user

        info = get_event_emitters(update_user)[0]
        assert info.payload_extractor is not None

        # 추출기 테스트
        result = info.payload_extractor({"id": 1, "name": "John", "email": "john@example.com"})
        assert result == {"id": 1, "name": "John"}

    def test_multiple_emitters(self):
        """다중 이벤트 발행"""

        @EventEmitter("user.created")
        @EventEmitter("audit.user_created")
        async def create_user(name: str):
            return {"name": name}

        emitters = get_event_emitters(create_user)
        assert len(emitters) == 2


class TestResolveEventType:
    """resolve_event_type 테스트"""

    def test_string_event_type(self):
        """문자열 이벤트 타입"""

        @EventListener("user.created")
        async def handler(event: Event):
            pass

        info = get_event_listeners(handler)[0]
        event_type = resolve_event_type(info, handler)
        assert event_type == "user.created"

    def test_class_event_type(self):
        """클래스 이벤트 타입"""

        @dataclass
        class MyEvent(DomainEvent):
            event_type: str = "my.event"

        @EventListener(MyEvent)
        async def handler(event: MyEvent):
            pass

        info = get_event_listeners(handler)[0]
        event_type = resolve_event_type(info, handler)
        assert event_type == "my.event"

    def test_infer_from_parameter_type(self):
        """파라미터 타입에서 추론"""

        @dataclass
        class UserEvent(DomainEvent):
            event_type: str = "user.event"

        @EventListener()  # event_type 생략
        async def handler(event: UserEvent):
            pass

        info = get_event_listeners(handler)[0]
        event_type = resolve_event_type(info, handler)
        assert event_type == "user.event"


class TestNoDecoratorMethods:
    """데코레이터가 없는 메서드 테스트"""

    def test_no_event_listener(self):
        """EventListener 없음"""

        async def regular_method():
            pass

        assert not has_event_listener(regular_method)
        assert get_event_listeners(regular_method) == []

    def test_no_event_emitter(self):
        """EventEmitter 없음"""

        async def regular_method():
            pass

        assert not has_event_emitter(regular_method)
        assert get_event_emitters(regular_method) == []


class TestCombinedDecorators:
    """데코레이터 조합 테스트"""

    def test_listener_and_emitter(self):
        """리스너와 이미터 조합"""

        @EventListener("order.created")
        @EventEmitter("notification.sent")
        async def process_order(event: Event):
            return {"notification": "sent"}

        assert has_event_listener(process_order)
        assert has_event_emitter(process_order)

        listeners = get_event_listeners(process_order)
        emitters = get_event_emitters(process_order)

        assert len(listeners) == 1
        assert len(emitters) == 1
        assert listeners[0].event_type == "order.created"
        assert emitters[0].event_type == "notification.sent"
