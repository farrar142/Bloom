"""LocalEventBus 테스트"""

import pytest
import asyncio
from typing import Any

from bloom.core.event import (
    LocalEventBus,
    Event,
    EventResult,
    EventStatus,
    SubscriptionMode,
)


class TestLocalEventBus:
    """LocalEventBus 기본 기능 테스트"""

    @pytest.fixture
    async def event_bus(self):
        """이벤트 버스 픽스처"""
        bus = LocalEventBus()
        await bus.start()
        yield bus
        await bus.stop()

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """시작/종료 테스트"""
        bus = LocalEventBus()
        assert not bus.is_running

        await bus.start()
        assert bus.is_running

        await bus.stop()
        assert not bus.is_running

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, event_bus: LocalEventBus):
        """구독 및 발행 테스트"""
        received_events: list[Event] = []

        async def handler(event: Event):
            received_events.append(event)

        # 구독
        subscription = await event_bus.subscribe("test.event", handler)
        assert subscription is not None
        assert event_bus.subscription_count == 1

        # 발행
        event = Event(event_type="test.event", payload={"key": "value"})
        await event_bus.publish(event, wait_for_handlers=True)

        assert len(received_events) == 1
        assert received_events[0].payload == {"key": "value"}

    @pytest.mark.asyncio
    async def test_unsubscribe(self, event_bus: LocalEventBus):
        """구독 해제 테스트"""
        received_events: list[Event] = []

        async def handler(event: Event):
            received_events.append(event)

        subscription = await event_bus.subscribe("test.event", handler)
        assert event_bus.subscription_count == 1

        # 구독 해제
        result = await event_bus.unsubscribe(subscription)
        assert result is True
        assert event_bus.subscription_count == 0

        # 이벤트 발행 - 핸들러 호출 안됨
        event = Event(event_type="test.event", payload="test")
        await event_bus.publish(event, wait_for_handlers=True)

        assert len(received_events) == 0

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, event_bus: LocalEventBus):
        """다중 핸들러 테스트"""
        results: list[str] = []

        async def handler1(event: Event):
            results.append("handler1")

        async def handler2(event: Event):
            results.append("handler2")

        async def handler3(event: Event):
            results.append("handler3")

        await event_bus.subscribe("test.event", handler1)
        await event_bus.subscribe("test.event", handler2)
        await event_bus.subscribe("test.event", handler3)

        event = Event(event_type="test.event", payload=None)
        await event_bus.publish(event, wait_for_handlers=True)

        assert len(results) == 3
        assert set(results) == {"handler1", "handler2", "handler3"}

    @pytest.mark.asyncio
    async def test_priority_ordering(self, event_bus: LocalEventBus):
        """우선순위 순서 테스트"""
        results: list[int] = []

        async def handler_low(event: Event):
            results.append(1)

        async def handler_normal(event: Event):
            results.append(2)

        async def handler_high(event: Event):
            results.append(3)

        # 우선순위 역순으로 등록
        await event_bus.subscribe("test.event", handler_low, priority=0)
        await event_bus.subscribe("test.event", handler_high, priority=100)
        await event_bus.subscribe("test.event", handler_normal, priority=50)

        event = Event(event_type="test.event", payload=None)
        await event_bus.publish(event, wait_for_handlers=True)

        # 높은 우선순위가 먼저 실행
        assert results == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_get_subscriptions(self, event_bus: LocalEventBus):
        """구독 목록 조회 테스트"""
        async def handler(event: Event):
            pass

        await event_bus.subscribe("event.a", handler)
        await event_bus.subscribe("event.b", handler)
        await event_bus.subscribe("event.a", handler)

        # 전체 조회
        all_subs = event_bus.get_subscriptions()
        assert len(all_subs) == 3

        # 특정 이벤트 타입 조회
        a_subs = event_bus.get_subscriptions("event.a")
        assert len(a_subs) == 2

        b_subs = event_bus.get_subscriptions("event.b")
        assert len(b_subs) == 1


class TestSyncAsyncHandlers:
    """동기/비동기 핸들러 테스트"""

    @pytest.fixture
    async def event_bus(self):
        bus = LocalEventBus()
        await bus.start()
        yield bus
        await bus.stop()

    @pytest.mark.asyncio
    async def test_sync_handler_immediate_execution(self, event_bus: LocalEventBus):
        """동기 핸들러 즉시 실행 테스트"""
        results: list[str] = []

        async def sync_handler(event: Event):
            results.append("sync")

        await event_bus.subscribe(
            "test.event",
            sync_handler,
            mode=SubscriptionMode.SYNC,
        )

        event = Event(event_type="test.event", payload=None)
        await event_bus.publish_sync(event)

        # 즉시 실행됨
        assert results == ["sync"]

    @pytest.mark.asyncio
    async def test_async_handler_background_execution(self, event_bus: LocalEventBus):
        """비동기 핸들러 백그라운드 실행 테스트"""
        results: list[str] = []
        event_received = asyncio.Event()

        async def async_handler(event: Event):
            results.append("async")
            event_received.set()

        await event_bus.subscribe(
            "test.event",
            async_handler,
            mode=SubscriptionMode.ASYNC,
        )

        event = Event(event_type="test.event", payload=None)
        await event_bus.publish(event)  # wait_for_handlers=False (기본값)

        # 백그라운드에서 실행되므로 대기
        await asyncio.wait_for(event_received.wait(), timeout=2.0)
        assert results == ["async"]

    @pytest.mark.asyncio
    async def test_mixed_sync_async_handlers(self, event_bus: LocalEventBus):
        """동기/비동기 혼합 핸들러 테스트"""
        results: list[str] = []

        async def sync_handler(event: Event):
            results.append("sync")

        async def async_handler(event: Event):
            results.append("async")

        await event_bus.subscribe("test.event", sync_handler, mode=SubscriptionMode.SYNC)
        await event_bus.subscribe("test.event", async_handler, mode=SubscriptionMode.ASYNC)

        event = Event(event_type="test.event", payload=None)
        
        # wait_for_handlers=True로 모든 핸들러 대기
        await event_bus.publish(event, wait_for_handlers=True)

        assert set(results) == {"sync", "async"}


class TestErrorHandling:
    """에러 처리 테스트"""

    @pytest.fixture
    async def event_bus(self):
        bus = LocalEventBus()
        await bus.start()
        yield bus
        await bus.stop()

    @pytest.mark.asyncio
    async def test_handler_error_isolation(self, event_bus: LocalEventBus):
        """핸들러 에러 격리 테스트"""
        results: list[str] = []

        async def failing_handler(event: Event):
            raise ValueError("Test error")

        async def success_handler(event: Event):
            results.append("success")

        # 실패 핸들러가 먼저 실행되도록 우선순위 설정
        await event_bus.subscribe("test.event", failing_handler, priority=100)
        await event_bus.subscribe("test.event", success_handler, priority=0)

        event = Event(event_type="test.event", payload=None)
        event_results = await event_bus.publish(event, wait_for_handlers=True)

        # 하나는 실패, 하나는 성공
        assert len(event_results) == 2
        assert any(r.status == EventStatus.FAILED for r in event_results)
        assert any(r.status == EventStatus.COMPLETED for r in event_results)
        
        # 성공 핸들러는 여전히 실행됨
        assert "success" in results

    @pytest.mark.asyncio
    async def test_error_handler_callback(self):
        """에러 핸들러 콜백 테스트"""
        errors: list[tuple[Event, Exception]] = []

        async def error_handler(event: Event, exc: Exception):
            errors.append((event, exc))

        bus = LocalEventBus(error_handler=error_handler)
        await bus.start()

        async def failing_handler(event: Event):
            raise ValueError("Test error")

        await bus.subscribe("test.event", failing_handler)

        event = Event(event_type="test.event", payload="test")
        await bus.publish(event, wait_for_handlers=True)

        assert len(errors) == 1
        assert errors[0][0].payload == "test"
        assert isinstance(errors[0][1], ValueError)

        await bus.stop()


class TestConditions:
    """조건부 실행 테스트"""

    @pytest.fixture
    async def event_bus(self):
        bus = LocalEventBus()
        await bus.start()
        yield bus
        await bus.stop()

    @pytest.mark.asyncio
    async def test_condition_true(self, event_bus: LocalEventBus):
        """조건 충족 시 실행"""
        results: list[Any] = []

        async def handler(event: Event):
            results.append(event.payload)

        await event_bus.subscribe(
            "test.event",
            handler,
            condition="payload.get('amount', 0) > 100",
        )

        # 조건 충족
        event1 = Event(event_type="test.event", payload={"amount": 200})
        await event_bus.publish(event1, wait_for_handlers=True)
        assert len(results) == 1

        # 조건 미충족
        event2 = Event(event_type="test.event", payload={"amount": 50})
        await event_bus.publish(event2, wait_for_handlers=True)
        assert len(results) == 1  # 증가하지 않음

    @pytest.mark.asyncio
    async def test_condition_with_metadata(self, event_bus: LocalEventBus):
        """메타데이터 조건 테스트"""
        results: list[Event] = []

        async def handler(event: Event):
            results.append(event)

        await event_bus.subscribe(
            "test.event",
            handler,
            condition="metadata.get('priority') == 'high'",
        )

        # 조건 충족
        event1 = Event(
            event_type="test.event",
            payload="test",
            metadata={"priority": "high"},
        )
        await event_bus.publish(event1, wait_for_handlers=True)
        assert len(results) == 1

        # 조건 미충족
        event2 = Event(
            event_type="test.event",
            payload="test",
            metadata={"priority": "low"},
        )
        await event_bus.publish(event2, wait_for_handlers=True)
        assert len(results) == 1


class TestEventResults:
    """이벤트 결과 테스트"""

    @pytest.fixture
    async def event_bus(self):
        bus = LocalEventBus()
        await bus.start()
        yield bus
        await bus.stop()

    @pytest.mark.asyncio
    async def test_event_result_success(self, event_bus: LocalEventBus):
        """성공 결과 테스트"""
        async def handler(event: Event):
            return {"processed": True}

        await event_bus.subscribe("test.event", handler, mode=SubscriptionMode.SYNC)

        event = Event(event_type="test.event", payload=None)
        results = await event_bus.publish_sync(event)

        assert len(results) == 1
        result = results[0]
        assert result.is_success
        assert result.status == EventStatus.COMPLETED
        assert result.result == {"processed": True}
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_event_result_failure(self, event_bus: LocalEventBus):
        """실패 결과 테스트"""
        async def handler(event: Event):
            raise ValueError("Test error")

        await event_bus.subscribe("test.event", handler, mode=SubscriptionMode.SYNC)

        event = Event(event_type="test.event", payload=None)
        results = await event_bus.publish_sync(event)

        assert len(results) == 1
        result = results[0]
        assert result.is_failure
        assert result.status == EventStatus.FAILED
        assert isinstance(result.error, ValueError)


class TestQueueBehavior:
    """큐 동작 테스트"""

    @pytest.mark.asyncio
    async def test_queue_size(self):
        """큐 크기 테스트"""
        bus = LocalEventBus(max_queue_size=10)
        # 시작하지 않음 - 워커가 이벤트를 처리하지 않도록

        async def handler(event: Event):
            pass

        await bus.subscribe("test.event", handler, mode=SubscriptionMode.ASYNC)

        # 큐가 가득 찰 때까지 이벤트 추가
        for i in range(10):
            event = Event(event_type="test.event", payload=i)
            await bus.publish(event)

        assert bus.queue_size == 10

    @pytest.mark.asyncio
    async def test_drain_on_stop(self):
        """종료 시 큐 비우기 테스트"""
        bus = LocalEventBus()
        await bus.start()

        processed_events: list[int] = []

        async def handler(event: Event):
            await asyncio.sleep(0.01)
            processed_events.append(event.payload)

        await bus.subscribe("test.event", handler, mode=SubscriptionMode.ASYNC)

        # 여러 이벤트 발행
        for i in range(5):
            event = Event(event_type="test.event", payload=i)
            await bus.publish(event)

        # 종료 시 대기 중인 이벤트 처리
        await bus.stop(timeout=5.0)

        assert len(processed_events) == 5
