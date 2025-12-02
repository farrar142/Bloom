"""DistributedEventBus 테스트"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from bloom.core.events import Event, EventMixin
from bloom.core.events.distributed import (
    DistributedEventBus,
    EventMessage,
    EventTypeRegistry,
)
from bloom.task.broker import InMemoryBroker


# =============================================================================
# 테스트용 이벤트 (EventMixin 사용)
# =============================================================================


@dataclass
class UserCreatedEvent(EventMixin):
    user_id: str = ""
    username: str = ""


@dataclass
class OrderPlacedEvent(EventMixin):
    order_id: str = ""
    amount: float = 0.0
    items: list[str] = field(default_factory=list)


@dataclass
class ComplexEvent(EventMixin):
    data: dict[str, int] = field(default_factory=dict)
    created_at: str = ""  # datetime은 ISO 문자열로


# =============================================================================
# EventMessage 테스트
# =============================================================================


class TestEventMessage:
    """EventMessage 직렬화/역직렬화 테스트"""

    async def test_simple_event_serialization(self):
        """단순 이벤트 직렬화"""
        event = UserCreatedEvent(user_id="123", username="alice")
        message = EventMessage.from_event(event)

        assert message.event_type.endswith("UserCreatedEvent")
        assert message.event_data["user_id"] == "123"
        assert message.event_data["username"] == "alice"

    async def test_json_round_trip(self):
        """JSON 직렬화/역직렬화 왕복"""
        event = UserCreatedEvent(user_id="456", username="bob")
        message = EventMessage.from_event(event)

        # JSON으로 직렬화
        json_str = message.to_json()
        assert isinstance(json_str, str)

        # 역직렬화
        restored = EventMessage.from_json(json_str)
        assert restored.event_type == message.event_type
        assert restored.event_data == message.event_data

    async def test_list_field_serialization(self):
        """리스트 필드 직렬화"""
        event = OrderPlacedEvent(
            order_id="ORD-001",
            amount=99.99,
            items=["item1", "item2", "item3"],
        )
        message = EventMessage.from_event(event)

        json_str = message.to_json()
        restored = EventMessage.from_json(json_str)

        assert restored.event_data["items"] == ["item1", "item2", "item3"]

    async def test_datetime_field_serialization(self):
        """datetime 필드는 ISO 문자열로 직렬화됨"""
        now = datetime(2024, 1, 15, 10, 30, 0)
        # ComplexEvent.created_at은 str 타입이므로 ISO 문자열 전달
        event = ComplexEvent(data={"a": 1, "b": 2}, created_at=now.isoformat())
        message = EventMessage.from_event(event)

        json_str = message.to_json()
        restored = EventMessage.from_json(json_str)

        # EventMixin.model_dump()는 datetime을 ISO 문자열로 변환
        assert restored.event_data["created_at"] == now.isoformat()


# =============================================================================
# EventTypeRegistry 테스트
# =============================================================================


class TestEventTypeRegistry:
    """이벤트 타입 레지스트리 테스트"""

    def setup_method(self):
        """각 테스트 전 레지스트리 초기화"""
        EventTypeRegistry._registry.clear()

    async def test_register_and_get(self):
        """이벤트 타입 등록 및 조회"""
        EventTypeRegistry.register(UserCreatedEvent)

        type_name = f"{UserCreatedEvent.__module__}.{UserCreatedEvent.__name__}"
        assert EventTypeRegistry.get(type_name) == UserCreatedEvent

    async def test_get_unregistered_returns_none(self):
        """미등록 타입 조회 시 None 반환"""
        assert EventTypeRegistry.get("nonexistent.Event") is None

    async def test_reconstruct_event(self):
        """EventMessage에서 Event 복원"""
        EventTypeRegistry.register(UserCreatedEvent)

        event = UserCreatedEvent(user_id="789", username="charlie")
        message = EventMessage.from_event(event)

        restored = EventTypeRegistry.reconstruct(message)
        assert isinstance(restored, UserCreatedEvent)
        assert restored.user_id == "789"
        assert restored.username == "charlie"


# =============================================================================
# DistributedEventBus 테스트
# =============================================================================


class TestDistributedEventBus:
    """DistributedEventBus 테스트"""

    def setup_method(self):
        """각 테스트 전 레지스트리 초기화"""
        EventTypeRegistry._registry.clear()

    @pytest.mark.asyncio
    async def test_sync_publish(self):
        """동기 발행 테스트"""
        broker = InMemoryBroker()
        await broker.connect()

        bus: DistributedEventBus[Event] = DistributedEventBus(
            broker, queue="test-events"
        )

        # 동기 발행
        event = UserCreatedEvent(user_id="1", username="test")
        bus.publish(event)

        # 브로커에 메시지가 들어가 있음
        raw = await broker.dequeue_raw("test-events", timeout=0.1)
        assert raw is not None
        assert "test" in raw

        await broker.disconnect()

    @pytest.mark.asyncio
    async def test_async_publish_to_broker(self):
        """브로커로 비동기 발행"""
        broker = InMemoryBroker()
        await broker.connect()

        bus: DistributedEventBus[Event] = DistributedEventBus(
            broker, queue="test-events"
        )

        # 비동기 발행
        event = UserCreatedEvent(user_id="2", username="async-test")
        await bus.publish_async(event)

        # 브로커에 메시지가 들어가 있음
        raw = await broker.dequeue_raw("test-events", timeout=0.1)
        assert raw is not None
        assert "async-test" in raw

        await broker.disconnect()

    @pytest.mark.asyncio
    async def test_consumer_receives_events(self):
        """컨슈머가 브로커에서 이벤트 수신"""
        broker = InMemoryBroker()
        await broker.connect()

        # Publisher
        publisher: DistributedEventBus[Event] = DistributedEventBus(
            broker, queue="shared-events"
        )

        # Consumer
        consumer: DistributedEventBus[Event] = DistributedEventBus(
            broker, queue="shared-events"
        )

        received: list[Any] = []
        consumer.subscribe(UserCreatedEvent, lambda e: received.append(e))

        # 발행
        await publisher.publish_async(
            UserCreatedEvent(user_id="3", username="distributed")
        )

        # 수동으로 메시지 처리 (start_consumer 대신)
        raw = await broker.dequeue_raw("shared-events", timeout=0.1)
        assert raw is not None
        consumer._process_message(raw)

        assert len(received) == 1
        assert received[0].username == "distributed"

        await broker.disconnect()

    @pytest.mark.asyncio
    async def test_multiple_event_types(self):
        """여러 이벤트 타입 발행"""
        broker = InMemoryBroker()
        await broker.connect()

        bus: DistributedEventBus[Event] = DistributedEventBus(
            broker, queue="multi-events"
        )

        # 두 가지 이벤트 발행
        await bus.publish_async(UserCreatedEvent(user_id="u1", username="user1"))
        await bus.publish_async(
            OrderPlacedEvent(order_id="o1", amount=100.0, items=["a", "b"])
        )

        # 브로커에서 메시지 확인
        raw1 = await broker.dequeue_raw("multi-events", timeout=0.1)
        raw2 = await broker.dequeue_raw("multi-events", timeout=0.1)

        assert raw1 is not None
        assert raw2 is not None
        assert "u1" in raw1
        assert "o1" in raw2

        await broker.disconnect()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """컨텍스트 매니저 사용"""
        broker = InMemoryBroker()

        async with DistributedEventBus(broker, queue="ctx-events") as bus:
            assert broker.is_connected

            await bus.publish_async(UserCreatedEvent(user_id="ctx", username="context"))

            # 브로커에 메시지 확인
            raw = await broker.dequeue_raw("ctx-events", timeout=0.1)
            assert raw is not None
            assert "ctx" in raw

        # 컨텍스트 종료 후 연결 해제됨
        assert not broker.is_connected


# =============================================================================
# 성능 테스트 (선택적)
# =============================================================================


class TestDistributedEventBusPerformance:
    """성능 벤치마크"""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_publish_throughput(self):
        """발행 처리량 측정"""
        import time

        broker = InMemoryBroker()
        await broker.connect()

        bus: DistributedEventBus[Event] = DistributedEventBus(
            broker, queue="perf-events"
        )

        iterations = 10000
        start = time.perf_counter()

        for i in range(iterations):
            await bus.publish_async(UserCreatedEvent(user_id=str(i), username=f"u{i}"))

        elapsed = time.perf_counter() - start
        ops_per_sec = iterations / elapsed

        print(f"\n[DistributedEventBus] 처리량: {ops_per_sec:,.0f} ops/sec")
        print(f"  총 {iterations:,}건 / {elapsed:.3f}s")

        await broker.disconnect()
