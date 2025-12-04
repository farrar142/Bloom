"""Event 모듈 통합 테스트

이 테스트는 Event 시스템의 전체 흐름을 검증합니다:
- EventBus + EventListener + EventEmitter 통합
- EventListenerRegistrar를 통한 자동 등록
- DomainEvent 사용 시나리오
- 우선순위 기반 핸들러 실행 순서
- 조건부 이벤트 처리
- Sync/Async 핸들러 혼합 사용
- 에러 핸들링 및 격리
"""

import pytest
import asyncio
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

from bloom.event import (
    Event,
    DomainEvent,
    EventPriority,
    EventStatus,
    EventResult,
    LocalEventBus,
    EventBus,
    EventListener,
    SyncEventListener,
    AsyncEventListener,
    EventEmitter,
    UserCreatedEvent,
    UserUpdatedEvent,
    UserDeletedEvent,
    Subscription,
    SubscriptionMode,
    SubscriptionGroup,
    EventHandler,
    SyncEventHandler,
)
from bloom.event.models import create_event, get_event_type
from bloom.event.registrar import EventListenerRegistrar, EventListenerScanner
from bloom.event.interceptor import EventEmitterInterceptor


# =============================================================================
# 테스트용 이벤트 및 서비스 클래스
# =============================================================================


@dataclass
class OrderCreatedPayload:
    """주문 생성 페이로드"""

    order_id: str
    user_id: str
    items: list[str]
    total_amount: float


@dataclass
class OrderCreatedEvent(Event):
    """주문 생성 이벤트 (커스텀 이벤트 타입)"""

    event_type: str = field(default="order.created", init=False)


@dataclass
class PaymentCompletedPayload:
    """결제 완료 페이로드"""

    payment_id: str
    order_id: str
    amount: float
    method: str


class OrderService:
    """주문 서비스 - 이벤트 리스너와 발행자 통합 테스트용"""

    def __init__(self):
        self.processed_orders: list[str] = []
        self.notifications_sent: list[str] = []
        self.audit_logs: list[dict] = []

    @SyncEventListener("order.created", priority=100)
    async def validate_order(self, event: Event) -> str:
        """주문 검증 - 가장 먼저 실행"""
        payload = event.payload
        if payload.get("total_amount", 0) <= 0:
            raise ValueError("Invalid order amount")
        return f"validated:{payload.get('order_id')}"

    @EventListener("order.created", priority=50)
    async def process_order(self, event: Event):
        """주문 처리 - 검증 후 실행"""
        order_id = event.payload.get("order_id")
        self.processed_orders.append(order_id)
        return f"processed:{order_id}"

    @AsyncEventListener("order.created", priority=10)
    async def send_notification(self, event: Event):
        """알림 전송 - 낮은 우선순위로 백그라운드 실행"""
        order_id = event.payload.get("order_id")
        self.notifications_sent.append(f"notification:{order_id}")
        return f"notified:{order_id}"

    @EventListener("user.created")
    async def on_user_created(self, event: Event):
        """사용자 생성 이벤트 핸들러"""
        user_id = event.payload.get("user_id")
        return f"user_created:{user_id}"


class AuditService:
    """감사 로그 서비스 - 모든 이벤트 기록"""

    def __init__(self):
        self.logs: list[dict] = []

    @EventListener("order.created")
    async def audit_order_created(self, event: Event):
        """주문 생성 감사 로그"""
        self.logs.append({
            "event_type": event.event_type,
            "event_id": event.event_id,
            "payload": event.payload,
            "action": "order_created",
        })

    @EventListener("user.created")
    async def audit_user_created(self, event: Event):
        """사용자 생성 감사 로그"""
        self.logs.append({
            "event_type": event.event_type,
            "event_id": event.event_id,
            "payload": event.payload,
            "action": "user_created",
        })

    @EventListener("payment.completed", condition="payload.get('amount', 0) >= 1000")
    async def audit_high_value_payment(self, event: Event):
        """고액 결제만 기록 (조건부)"""
        self.logs.append({
            "event_type": event.event_type,
            "amount": event.payload.get("amount"),
            "action": "high_value_payment",
        })


class NotificationService:
    """알림 서비스 - 다양한 이벤트 핸들링"""

    def __init__(self):
        self.sent_notifications: list[dict] = []

    @SyncEventListener("user.created")
    async def send_welcome_email(self, event: Event):
        """환영 이메일 - 동기 처리"""
        self.sent_notifications.append({
            "type": "email",
            "template": "welcome",
            "user_id": event.payload.get("user_id"),
        })

    @AsyncEventListener("user.updated")
    async def notify_profile_change(self, event: Event):
        """프로필 변경 알림 - 비동기 처리"""
        self.sent_notifications.append({
            "type": "push",
            "message": "profile_updated",
            "user_id": event.payload.get("user_id"),
        })


# =============================================================================
# 통합 테스트 Fixtures
# =============================================================================


@pytest.fixture
async def event_bus():
    """LocalEventBus 픽스처 - 테스트 전후 자동 시작/종료"""
    bus = LocalEventBus()
    await bus.start()
    yield bus
    await bus.stop()


@pytest.fixture
def registrar(event_bus):
    """EventListenerRegistrar 픽스처"""
    return EventListenerRegistrar(event_bus)


# =============================================================================
# 통합 테스트: 전체 Event 시스템 흐름
# =============================================================================


class TestEventSystemIntegration:
    """Event 시스템 전체 통합 테스트"""

    @pytest.mark.asyncio
    async def test_full_event_lifecycle(self, event_bus, registrar):
        """이벤트의 전체 생명주기 테스트
        
        1. 서비스들의 이벤트 리스너 자동 등록
        2. 이벤트 발행
        3. 우선순위에 따른 핸들러 실행
        4. 결과 수집 및 검증
        """
        # 서비스 인스턴스 생성 및 등록
        order_service = OrderService()
        audit_service = AuditService()
        
        await registrar.register_instance(order_service)
        await registrar.register_instance(audit_service)
        
        # 등록된 구독 확인: OrderService 4개 + AuditService 3개 = 7개
        assert registrar.subscription_count == 7
        
        # 주문 생성 이벤트 발행
        order_event = Event(
            event_type="order.created",
            payload={
                "order_id": "ORD-001",
                "user_id": "USR-001",
                "total_amount": 5000.00,
                "items": ["item1", "item2"],
            },
        )
        
        results = await event_bus.publish(order_event, wait_for_handlers=True)
        
        # 모든 핸들러가 실행되었는지 확인
        assert len(results) >= 3  # OrderService의 order.created 핸들러 3개 + AuditService 1개
        
        # 핸들러 실행 결과 확인
        assert "ORD-001" in order_service.processed_orders
        assert any("notification:ORD-001" in n for n in order_service.notifications_sent)
        assert any(log.get("action") == "order_created" for log in audit_service.logs)

    @pytest.mark.asyncio
    async def test_priority_based_handler_execution(self, event_bus, registrar):
        """우선순위 기반 핸들러 실행 순서 테스트"""
        execution_order: list[str] = []
        
        class PriorityTestService:
            @SyncEventListener("test.priority", priority=10)
            async def low_priority(self, event: Event):
                execution_order.append("low")
            
            @SyncEventListener("test.priority", priority=50)
            async def medium_priority(self, event: Event):
                execution_order.append("medium")
            
            @SyncEventListener("test.priority", priority=100)
            async def high_priority(self, event: Event):
                execution_order.append("high")
        
        service = PriorityTestService()
        await registrar.register_instance(service)
        
        event = Event(event_type="test.priority", payload={})
        await event_bus.publish_sync(event)
        
        # 높은 우선순위가 먼저 실행됨
        assert execution_order == ["high", "medium", "low"]

    @pytest.mark.asyncio
    async def test_conditional_event_handling(self, event_bus, registrar):
        """조건부 이벤트 처리 테스트"""
        audit_service = AuditService()
        await registrar.register_instance(audit_service)
        
        # 고액 결제 이벤트 (조건 충족)
        high_payment = Event(
            event_type="payment.completed",
            payload={"payment_id": "PAY-001", "amount": 5000},
        )
        await event_bus.publish(high_payment, wait_for_handlers=True)
        
        # 소액 결제 이벤트 (조건 미충족)
        low_payment = Event(
            event_type="payment.completed",
            payload={"payment_id": "PAY-002", "amount": 500},
        )
        await event_bus.publish(low_payment, wait_for_handlers=True)
        
        # 고액 결제만 로그됨
        high_value_logs = [
            log for log in audit_service.logs
            if log.get("action") == "high_value_payment"
        ]
        assert len(high_value_logs) == 1
        assert high_value_logs[0]["amount"] == 5000

    @pytest.mark.asyncio
    async def test_sync_async_handler_isolation(self, event_bus, registrar):
        """동기/비동기 핸들러 분리 실행 테스트"""
        sync_results: list[str] = []
        async_results: list[str] = []
        async_event = asyncio.Event()
        
        class MixedHandlerService:
            @SyncEventListener("mixed.event")
            async def sync_handler(self, event: Event):
                sync_results.append("sync_executed")
            
            @AsyncEventListener("mixed.event")
            async def async_handler(self, event: Event):
                await asyncio.sleep(0.01)  # 비동기 작업 시뮬레이션
                async_results.append("async_executed")
                async_event.set()
        
        service = MixedHandlerService()
        await registrar.register_instance(service)
        
        event = Event(event_type="mixed.event", payload={})
        
        # publish_sync는 동기 핸들러만 실행
        await event_bus.publish_sync(event)
        assert sync_results == ["sync_executed"]
        assert async_results == []  # 비동기 핸들러는 아직 실행 안됨
        
        # publish는 모든 핸들러 실행 (wait_for_handlers=True)
        sync_results.clear()
        event2 = Event(event_type="mixed.event", payload={})
        await event_bus.publish(event2, wait_for_handlers=True)
        
        assert "sync_executed" in sync_results
        assert "async_executed" in async_results

    @pytest.mark.asyncio
    async def test_error_isolation_between_handlers(self, event_bus, registrar):
        """핸들러 간 에러 격리 테스트"""
        results: list[str] = []
        
        class ErrorProneService:
            @SyncEventListener("error.test", priority=100)
            async def failing_handler(self, event: Event):
                raise ValueError("Intentional error")
            
            @SyncEventListener("error.test", priority=50)
            async def success_handler_after_error(self, event: Event):
                results.append("success_after_error")
            
            @SyncEventListener("error.test", priority=10)
            async def another_success(self, event: Event):
                results.append("another_success")
        
        service = ErrorProneService()
        await registrar.register_instance(service)
        
        event = Event(event_type="error.test", payload={})
        event_results = await event_bus.publish_sync(event)
        
        # 에러가 발생해도 다른 핸들러는 계속 실행됨
        assert len(results) == 2
        assert "success_after_error" in results
        assert "another_success" in results
        
        # 결과에 실패와 성공이 모두 포함됨
        failed_results = [r for r in event_results if r.status == EventStatus.FAILED]
        success_results = [r for r in event_results if r.status == EventStatus.COMPLETED]
        assert len(failed_results) == 1
        assert len(success_results) == 2


class TestMultiServiceEventIntegration:
    """여러 서비스 간 이벤트 통합 테스트"""

    @pytest.mark.asyncio
    async def test_cross_service_event_propagation(self, event_bus, registrar):
        """서비스 간 이벤트 전파 테스트"""
        order_service = OrderService()
        audit_service = AuditService()
        notification_service = NotificationService()
        
        await registrar.register_instance(order_service)
        await registrar.register_instance(audit_service)
        await registrar.register_instance(notification_service)
        
        # 사용자 생성 이벤트 - 여러 서비스에서 처리
        user_event = Event(
            event_type="user.created",
            payload={"user_id": "USR-TEST-001", "name": "Test User"},
        )
        await event_bus.publish(user_event, wait_for_handlers=True)
        
        # OrderService의 핸들러 실행 확인
        # (반환값은 내부적으로 처리되므로 side effect로 확인)
        
        # AuditService 로그 확인
        user_logs = [
            log for log in audit_service.logs
            if log.get("action") == "user_created"
        ]
        assert len(user_logs) == 1
        assert user_logs[0]["payload"]["user_id"] == "USR-TEST-001"
        
        # NotificationService 알림 확인
        welcome_emails = [
            n for n in notification_service.sent_notifications
            if n.get("template") == "welcome"
        ]
        assert len(welcome_emails) == 1
        assert welcome_emails[0]["user_id"] == "USR-TEST-001"

    @pytest.mark.asyncio
    async def test_unregister_service_stops_event_handling(self, event_bus, registrar):
        """서비스 등록 해제 후 이벤트 처리 중단 테스트"""
        order_service = OrderService()
        await registrar.register_instance(order_service)
        
        # 첫 번째 이벤트 - 처리됨
        event1 = Event(
            event_type="order.created",
            payload={"order_id": "ORD-001", "total_amount": 1000},
        )
        await event_bus.publish(event1, wait_for_handlers=True)
        assert "ORD-001" in order_service.processed_orders
        
        # 서비스 등록 해제
        await registrar.unregister_instance(order_service)
        
        # 두 번째 이벤트 - 처리 안됨
        event2 = Event(
            event_type="order.created",
            payload={"order_id": "ORD-002", "total_amount": 2000},
        )
        await event_bus.publish(event2, wait_for_handlers=True)
        assert "ORD-002" not in order_service.processed_orders


class TestDomainEventIntegration:
    """DomainEvent 통합 테스트"""

    @pytest.mark.asyncio
    async def test_domain_event_with_typed_payload(self, event_bus):
        """타입 안전한 DomainEvent 처리 테스트"""
        received_events: list[Event] = []
        
        async def handler(event: Event):
            received_events.append(event)
        
        # UserCreatedEvent 타입으로 구독
        await event_bus.subscribe(UserCreatedEvent, handler)
        
        # UserCreatedEvent 발행
        user_event = UserCreatedEvent(
            payload={"user_id": "USR-001", "username": "testuser"},
        )
        await event_bus.publish(user_event, wait_for_handlers=True)
        
        assert len(received_events) == 1
        assert received_events[0].event_type == "user.created"
        assert received_events[0].payload["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_event_correlation_and_causation(self, event_bus):
        """이벤트 상관관계 및 인과관계 추적 테스트"""
        events: list[Event] = []
        
        async def handler(event: Event):
            events.append(event)
            
            # 후속 이벤트 생성 시 correlation_id 전파
            if event.event_type == "user.created":
                follow_up = Event(
                    event_type="notification.scheduled",
                    payload={"type": "welcome_email"},
                    correlation_id=event.correlation_id,
                    causation_id=event.event_id,
                )
                await event_bus.publish(follow_up, wait_for_handlers=True)
        
        await event_bus.subscribe("user.created", handler)
        await event_bus.subscribe("notification.scheduled", handler)
        
        # 최초 이벤트
        original_event = UserCreatedEvent(
            payload={"user_id": "USR-001"},
            correlation_id="CORR-12345",
        )
        await event_bus.publish(original_event, wait_for_handlers=True)
        
        # 두 이벤트가 모두 처리됨
        assert len(events) == 2
        
        # 후속 이벤트의 correlation_id가 유지됨
        notification_event = next(e for e in events if e.event_type == "notification.scheduled")
        assert notification_event.correlation_id == "CORR-12345"
        assert notification_event.causation_id == original_event.event_id


class TestEventSubscriptionManagement:
    """이벤트 구독 관리 통합 테스트"""

    @pytest.mark.asyncio
    async def test_subscription_group_priority_ordering(self, event_bus):
        """SubscriptionGroup 우선순위 정렬 테스트"""
        execution_order: list[int] = []
        
        async def handler_10(event: Event):
            execution_order.append(10)
        
        async def handler_50(event: Event):
            execution_order.append(50)
        
        async def handler_100(event: Event):
            execution_order.append(100)
        
        # 역순으로 등록
        await event_bus.subscribe("test.order", handler_10, priority=10, mode=SubscriptionMode.SYNC)
        await event_bus.subscribe("test.order", handler_100, priority=100, mode=SubscriptionMode.SYNC)
        await event_bus.subscribe("test.order", handler_50, priority=50, mode=SubscriptionMode.SYNC)
        
        event = Event(event_type="test.order", payload={})
        await event_bus.publish_sync(event)
        
        # 높은 우선순위가 먼저 실행됨
        assert execution_order == [100, 50, 10]

    @pytest.mark.asyncio
    async def test_dynamic_subscription_management(self, event_bus):
        """동적 구독 추가/제거 테스트"""
        results: list[str] = []
        
        async def handler1(event: Event):
            results.append("handler1")
        
        async def handler2(event: Event):
            results.append("handler2")
        
        # handler1 등록
        sub1 = await event_bus.subscribe("dynamic.event", handler1)
        
        event1 = Event(event_type="dynamic.event", payload={})
        await event_bus.publish(event1, wait_for_handlers=True)
        assert results == ["handler1"]
        
        # handler2 추가
        sub2 = await event_bus.subscribe("dynamic.event", handler2)
        
        results.clear()
        event2 = Event(event_type="dynamic.event", payload={})
        await event_bus.publish(event2, wait_for_handlers=True)
        assert set(results) == {"handler1", "handler2"}
        
        # handler1 제거
        await event_bus.unsubscribe(sub1)
        
        results.clear()
        event3 = Event(event_type="dynamic.event", payload={})
        await event_bus.publish(event3, wait_for_handlers=True)
        assert results == ["handler2"]


class TestEventModelSerialization:
    """이벤트 모델 직렬화 통합 테스트"""

    @pytest.mark.asyncio
    async def test_event_serialization_deserialization(self):
        """이벤트 직렬화/역직렬화 테스트"""
        original_event = Event(
            event_type="test.serialization",
            payload={"key": "value", "nested": {"inner": 123}},
            metadata={"priority": "high"},
            correlation_id="CORR-001",
        )
        
        # 직렬화
        event_dict = original_event.to_dict()
        
        # 역직렬화
        restored_event = Event.from_dict(event_dict)
        
        assert restored_event.event_id == original_event.event_id
        assert restored_event.event_type == original_event.event_type
        assert restored_event.payload == original_event.payload
        assert restored_event.metadata == original_event.metadata
        assert restored_event.correlation_id == original_event.correlation_id

    @pytest.mark.asyncio
    async def test_domain_event_serialization(self):
        """DomainEvent 직렬화 테스트"""
        user_event = UserCreatedEvent(
            payload={"user_id": "USR-001", "email": "test@example.com"},
            metadata={"source": "registration_api"},
        )
        
        event_dict = user_event.to_dict()
        
        assert event_dict["event_type"] == "user.created"
        assert event_dict["payload"]["user_id"] == "USR-001"
        assert event_dict["metadata"]["source"] == "registration_api"


class TestEventResultTracking:
    """이벤트 결과 추적 통합 테스트"""

    @pytest.mark.asyncio
    async def test_event_result_aggregation(self, event_bus):
        """다중 핸들러 결과 집계 테스트"""
        async def handler_success(event: Event):
            return {"status": "processed"}
        
        async def handler_error(event: Event):
            raise RuntimeError("Processing failed")
        
        async def handler_slow(event: Event):
            await asyncio.sleep(0.01)
            return {"status": "slow_processed"}
        
        await event_bus.subscribe("result.test", handler_success, mode=SubscriptionMode.SYNC)
        await event_bus.subscribe("result.test", handler_error, mode=SubscriptionMode.SYNC)
        await event_bus.subscribe("result.test", handler_slow, mode=SubscriptionMode.SYNC)
        
        event = Event(event_type="result.test", payload={})
        results = await event_bus.publish_sync(event)
        
        assert len(results) == 3
        
        # 성공 결과 확인
        success_results = [r for r in results if r.is_success]
        assert len(success_results) == 2
        
        # 실패 결과 확인
        failure_results = [r for r in results if r.is_failure]
        assert len(failure_results) == 1
        assert isinstance(failure_results[0].error, RuntimeError)
        
        # duration_ms 확인
        for result in results:
            assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_event_result_with_custom_error_handler(self):
        """커스텀 에러 핸들러 통합 테스트"""
        error_log: list[tuple[str, str]] = []
        
        async def error_handler(event: Event, exc: Exception):
            error_log.append((event.event_type, str(exc)))
        
        bus = LocalEventBus(error_handler=error_handler)
        await bus.start()
        
        try:
            async def failing_handler(event: Event):
                raise ValueError("Custom error message")
            
            await bus.subscribe("error.custom", failing_handler)
            
            event = Event(event_type="error.custom", payload={})
            await bus.publish(event, wait_for_handlers=True)
            
            assert len(error_log) == 1
            assert error_log[0][0] == "error.custom"
            assert "Custom error message" in error_log[0][1]
        finally:
            await bus.stop()


class TestEventListenerScannerIntegration:
    """EventListenerScanner 통합 테스트"""

    def test_scan_complex_service_class(self):
        """복잡한 서비스 클래스 스캔 테스트"""
        listeners = EventListenerScanner.scan_class(OrderService)
        
        assert len(listeners) >= 4
        
        method_info = {method_name: info for method_name, info in listeners}
        
        # validate_order는 SYNC 모드, 우선순위 100
        assert method_info["validate_order"].mode == SubscriptionMode.SYNC
        assert method_info["validate_order"].priority == 100
        
        # send_notification은 ASYNC 모드
        assert method_info["send_notification"].mode == SubscriptionMode.ASYNC

    def test_scan_inheritance_hierarchy(self):
        """상속 계층 스캔 테스트"""
        class BaseService:
            @EventListener("base.event")
            async def on_base(self, event: Event):
                pass
        
        class DerivedService(BaseService):
            @EventListener("derived.event")
            async def on_derived(self, event: Event):
                pass
        
        class FurtherDerivedService(DerivedService):
            @EventListener("further.event")
            async def on_further(self, event: Event):
                pass
        
        listeners = EventListenerScanner.scan_class(FurtherDerivedService)
        event_types = {info.event_type for _, info in listeners}
        
        assert "base.event" in event_types
        assert "derived.event" in event_types
        assert "further.event" in event_types


class TestBackgroundEventProcessing:
    """백그라운드 이벤트 처리 통합 테스트"""

    @pytest.mark.asyncio
    async def test_async_handler_background_execution(self, event_bus):
        """비동기 핸들러 백그라운드 실행 테스트"""
        processing_started = asyncio.Event()
        processing_completed = asyncio.Event()
        
        async def slow_handler(event: Event):
            processing_started.set()
            await asyncio.sleep(0.05)
            processing_completed.set()
        
        await event_bus.subscribe(
            "background.test",
            slow_handler,
            mode=SubscriptionMode.ASYNC,
        )
        
        event = Event(event_type="background.test", payload={})
        
        # wait_for_handlers=False로 즉시 반환
        await event_bus.publish(event, wait_for_handlers=False)
        
        # 핸들러가 백그라운드에서 시작될 때까지 대기
        await asyncio.wait_for(processing_started.wait(), timeout=2.0)
        
        # 핸들러 완료 대기
        await asyncio.wait_for(processing_completed.wait(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_queue_based_async_processing(self):
        """큐 기반 비동기 처리 테스트"""
        processed_events: list[str] = []
        all_processed = asyncio.Event()
        expected_count = 5
        
        async def queue_handler(event: Event):
            processed_events.append(event.payload["id"])
            if len(processed_events) >= expected_count:
                all_processed.set()
        
        bus = LocalEventBus(worker_count=2)  # 2개의 워커
        await bus.start()
        
        try:
            await bus.subscribe(
                "queue.test",
                queue_handler,
                mode=SubscriptionMode.ASYNC,
            )
            
            # 여러 이벤트 발행
            for i in range(expected_count):
                event = Event(event_type="queue.test", payload={"id": f"event-{i}"})
                await bus.publish(event, wait_for_handlers=False)
            
            # 모든 이벤트 처리 대기
            await asyncio.wait_for(all_processed.wait(), timeout=5.0)
            
            assert len(processed_events) == expected_count
        finally:
            await bus.stop()


class TestEventBusLifecycle:
    """EventBus 생명주기 통합 테스트"""

    @pytest.mark.asyncio
    async def test_start_stop_multiple_times(self):
        """여러 번 시작/종료 테스트"""
        bus = LocalEventBus()
        
        # 첫 번째 사이클
        await bus.start()
        assert bus.is_running
        await bus.stop()
        assert not bus.is_running
        
        # 두 번째 사이클
        await bus.start()
        assert bus.is_running
        await bus.stop()
        assert not bus.is_running

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_pending_events(self):
        """대기 중인 이벤트가 있을 때 정상 종료 테스트"""
        processed: list[str] = []
        
        async def handler(event: Event):
            await asyncio.sleep(0.01)
            processed.append(event.payload["id"])
        
        bus = LocalEventBus()
        await bus.start()
        
        await bus.subscribe("shutdown.test", handler, mode=SubscriptionMode.ASYNC)
        
        # 여러 이벤트 발행
        for i in range(3):
            event = Event(event_type="shutdown.test", payload={"id": f"event-{i}"})
            await bus.publish(event, wait_for_handlers=False)
        
        # 종료 시 대기 중인 이벤트 처리
        await bus.stop(timeout=5.0)
        
        assert len(processed) == 3


class TestRealWorldScenarios:
    """실제 사용 시나리오 통합 테스트"""

    @pytest.mark.asyncio
    async def test_ecommerce_order_flow(self, event_bus, registrar):
        """이커머스 주문 흐름 시나리오"""
        # 상태 추적
        flow_state = {
            "order_validated": False,
            "inventory_reserved": False,
            "payment_initiated": False,
            "notification_sent": False,
        }
        
        class InventoryService:
            @SyncEventListener("order.created", priority=90)
            async def reserve_inventory(self, event: Event):
                flow_state["inventory_reserved"] = True
        
        class PaymentService:
            @SyncEventListener("order.created", priority=80)
            async def initiate_payment(self, event: Event):
                if not flow_state["inventory_reserved"]:
                    raise ValueError("Inventory not reserved")
                flow_state["payment_initiated"] = True
        
        class CustomerNotificationService:
            @AsyncEventListener("order.created", priority=10)
            async def send_order_confirmation(self, event: Event):
                flow_state["notification_sent"] = True
        
        # 서비스 등록
        await registrar.register_instance(InventoryService())
        await registrar.register_instance(PaymentService())
        await registrar.register_instance(CustomerNotificationService())
        
        # 주문 이벤트 발행
        order_event = Event(
            event_type="order.created",
            payload={
                "order_id": "ORD-12345",
                "items": [{"sku": "SKU-001", "qty": 2}],
                "total": 150.00,
            },
        )
        await event_bus.publish(order_event, wait_for_handlers=True)
        
        # 모든 단계가 순서대로 실행됨
        assert flow_state["inventory_reserved"]
        assert flow_state["payment_initiated"]
        assert flow_state["notification_sent"]

    @pytest.mark.asyncio
    async def test_user_registration_with_multiple_side_effects(self, event_bus, registrar):
        """사용자 등록 시 여러 부가 효과 시나리오"""
        side_effects = []
        
        class WelcomeEmailService:
            @SyncEventListener("user.registered")
            async def send_welcome_email(self, event: Event):
                side_effects.append(f"email_sent:{event.payload['email']}")
        
        class AnalyticsService:
            @AsyncEventListener("user.registered")
            async def track_registration(self, event: Event):
                side_effects.append(f"analytics_tracked:{event.payload['user_id']}")
        
        class RewardService:
            @AsyncEventListener("user.registered", condition="payload.get('referral_code') is not None")
            async def credit_referral_bonus(self, event: Event):
                side_effects.append(f"referral_credited:{event.payload['referral_code']}")
        
        await registrar.register_instance(WelcomeEmailService())
        await registrar.register_instance(AnalyticsService())
        await registrar.register_instance(RewardService())
        
        # 추천 코드 있는 사용자 등록
        event1 = Event(
            event_type="user.registered",
            payload={
                "user_id": "USR-001",
                "email": "user1@example.com",
                "referral_code": "REF-123",
            },
        )
        await event_bus.publish(event1, wait_for_handlers=True)
        
        # 추천 코드 없는 사용자 등록
        event2 = Event(
            event_type="user.registered",
            payload={
                "user_id": "USR-002",
                "email": "user2@example.com",
            },
        )
        await event_bus.publish(event2, wait_for_handlers=True)
        
        # 첫 번째 사용자: 이메일, 분석, 추천 보상 모두 실행
        assert "email_sent:user1@example.com" in side_effects
        assert "analytics_tracked:USR-001" in side_effects
        assert "referral_credited:REF-123" in side_effects
        
        # 두 번째 사용자: 이메일, 분석만 실행 (추천 코드 없음)
        assert "email_sent:user2@example.com" in side_effects
        assert "analytics_tracked:USR-002" in side_effects
        assert "referral_credited:None" not in side_effects
