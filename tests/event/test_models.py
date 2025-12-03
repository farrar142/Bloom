"""이벤트 모델 테스트"""

import pytest
from datetime import datetime
from dataclasses import dataclass

from bloom.core.event import (
    Event,
    DomainEvent,
    EventPriority,
    EventStatus,
    EventResult,
    UserCreatedEvent,
    UserCreatedPayload,
    get_event_type,
    create_event,
)


class TestEvent:
    """Event 클래스 테스트"""

    def test_event_creation(self):
        """이벤트 생성"""
        event = Event(event_type="user.created", payload={"user_id": 1})

        assert event.event_type == "user.created"
        assert event.payload == {"user_id": 1}
        assert event.event_id is not None
        assert event.timestamp is not None
        assert event.priority == EventPriority.NORMAL

    def test_event_with_metadata(self):
        """메타데이터 포함 이벤트"""
        event = Event(
            event_type="test.event",
            payload="test",
            metadata={"source": "test", "version": 1},
        )

        assert event.metadata["source"] == "test"
        assert event.metadata["version"] == 1

    def test_event_with_correlation(self):
        """상관 ID 포함 이벤트"""
        parent_event = Event(event_type="parent.event", payload=None)
        child_event = Event(
            event_type="child.event",
            payload=None,
            correlation_id=parent_event.event_id,
            causation_id=parent_event.event_id,
        )

        assert child_event.correlation_id == parent_event.event_id
        assert child_event.causation_id == parent_event.event_id

    def test_with_correlation_method(self):
        """with_correlation 메서드"""
        event = Event(event_type="test.event", payload=None)
        new_event = event.with_correlation("corr-123")

        assert new_event.correlation_id == "corr-123"
        assert new_event.event_type == event.event_type

    def test_with_causation_method(self):
        """with_causation 메서드"""
        event = Event(event_type="test.event", payload=None)
        new_event = event.with_causation("cause-456")

        assert new_event.causation_id == "cause-456"

    def test_event_to_dict(self):
        """딕셔너리 변환"""
        event = Event(
            event_type="test.event",
            payload={"key": "value"},
            priority=EventPriority.HIGH,
        )
        data = event.to_dict()

        assert data["event_type"] == "test.event"
        assert data["payload"] == {"key": "value"}
        assert data["priority"] == EventPriority.HIGH.value
        assert "event_id" in data
        assert "timestamp" in data

    def test_event_from_dict(self):
        """딕셔너리에서 생성"""
        data = {
            "event_type": "test.event",
            "payload": {"key": "value"},
            "timestamp": datetime.now().isoformat(),
            "priority": EventPriority.HIGH.value,
        }
        event = Event.from_dict(data)

        assert event.event_type == "test.event"
        assert event.payload == {"key": "value"}
        assert event.priority == EventPriority.HIGH


class TestDomainEvent:
    """DomainEvent 클래스 테스트"""

    def test_user_created_event(self):
        """UserCreatedEvent 테스트"""
        payload = UserCreatedPayload(user_id=1, username="john", email="john@example.com")
        event = UserCreatedEvent(payload=payload)

        assert event.event_type == "user.created"
        assert event.payload.user_id == 1
        assert event.payload.username == "john"

    def test_custom_domain_event(self):
        """커스텀 도메인 이벤트"""

        @dataclass
        class OrderPayload:
            order_id: int
            total: float

        @dataclass
        class OrderCreatedEvent(DomainEvent[OrderPayload]):
            event_type: str = "order.created"

        payload = OrderPayload(order_id=100, total=500.0)
        event = OrderCreatedEvent(payload=payload)

        assert event.event_type == "order.created"
        assert event.payload.order_id == 100


class TestEventResult:
    """EventResult 테스트"""

    def test_success_result(self):
        """성공 결과"""
        result = EventResult(
            event_id="event-123",
            status=EventStatus.COMPLETED,
            handler_name="test_handler",
            result={"processed": True},
            duration_ms=10.5,
        )

        assert result.is_success
        assert not result.is_failure
        assert result.result == {"processed": True}

    def test_failure_result(self):
        """실패 결과"""
        error = ValueError("Test error")
        result = EventResult(
            event_id="event-123",
            status=EventStatus.FAILED,
            handler_name="test_handler",
            error=error,
        )

        assert result.is_failure
        assert not result.is_success
        assert result.error == error


class TestGetEventType:
    """get_event_type 함수 테스트"""

    def test_from_string(self):
        """문자열에서 추출"""
        assert get_event_type("user.created") == "user.created"

    def test_from_event_instance(self):
        """이벤트 인스턴스에서 추출"""
        event = Event(event_type="test.event", payload=None)
        assert get_event_type(event) == "test.event"

    def test_from_event_class(self):
        """이벤트 클래스에서 추출"""
        assert get_event_type(UserCreatedEvent) == "user.created"

    def test_from_custom_event_class(self):
        """커스텀 이벤트 클래스에서 추출"""

        @dataclass
        class CustomEvent(DomainEvent):
            event_type: str = "custom.event"

        assert get_event_type(CustomEvent) == "custom.event"


class TestCreateEvent:
    """create_event 함수 테스트"""

    def test_create_with_string(self):
        """문자열 타입으로 생성"""
        event = create_event("test.event", {"key": "value"})

        assert isinstance(event, Event)
        assert event.event_type == "test.event"
        assert event.payload == {"key": "value"}

    def test_create_with_class(self):
        """클래스 타입으로 생성"""
        payload = UserCreatedPayload(user_id=1, username="john")
        event = create_event(UserCreatedEvent, payload)

        assert isinstance(event, UserCreatedEvent)
        assert event.payload == payload

    def test_create_with_extra_kwargs(self):
        """추가 인자로 생성"""
        event = create_event(
            "test.event",
            "payload",
            source="test_source",
            priority=EventPriority.HIGH,
        )

        assert event.source == "test_source"
        assert event.priority == EventPriority.HIGH


class TestEventPriority:
    """EventPriority 테스트"""

    def test_priority_values(self):
        """우선순위 값"""
        assert EventPriority.LOW.value == 0
        assert EventPriority.NORMAL.value == 1
        assert EventPriority.HIGH.value == 2
        assert EventPriority.CRITICAL.value == 3

    def test_priority_comparison(self):
        """우선순위 비교"""
        assert EventPriority.LOW.value < EventPriority.NORMAL.value
        assert EventPriority.NORMAL.value < EventPriority.HIGH.value
        assert EventPriority.HIGH.value < EventPriority.CRITICAL.value
