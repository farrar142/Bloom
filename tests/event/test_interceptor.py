"""이벤트 인터셉터 테스트"""

import pytest
from unittest.mock import MagicMock
from typing import Any

from bloom.event import Event, LocalEventBus
from bloom.event.bus import SubscriptionMode
from bloom.event.interceptor import EventEmitterInterceptor
from bloom.event.decorators import EventEmitter


class MockMethodInvocation:
    """테스트용 MethodInvocation Mock"""

    def __init__(
        self,
        target: Any,
        method_name: str,
        args: tuple,
        kwargs: dict,
        return_value: Any = None,
    ):
        self.target = target
        self.method_name = method_name
        self.args = args
        self.kwargs = kwargs
        self._return_value = return_value
        # 실제 메서드 참조
        self.method = getattr(target, method_name, None)

    async def proceed(self):
        return self._return_value


class MockService:
    """테스트용 서비스"""

    @EventEmitter("user.created")
    async def create_user(self, name: str) -> dict:
        return {"id": 1, "name": name}

    @EventEmitter("order.placed", payload_extractor=lambda r: r.get("order_data", r))
    async def place_order(self, order_data: dict) -> dict:
        return {"status": "placed", "order_data": order_data}

    @EventEmitter("notification.sent", condition="result.get('sent', False)")
    async def send_notification(self, message: str) -> dict:
        return {"sent": True, "message": message}

    @EventEmitter("notification.failed", condition="not result.get('sent', True)")
    async def fail_notification(self, message: str) -> dict:
        return {"sent": False, "message": message}

    async def no_emitter_method(self):
        return "no event"


@pytest.fixture
def event_bus():
    """이벤트 버스 픽스처"""
    return LocalEventBus()


@pytest.fixture
def interceptor(event_bus):
    """인터셉터 픽스처"""
    return EventEmitterInterceptor(event_bus)


@pytest.fixture
def service():
    """서비스 픽스처"""
    return MockService()


class TestEventEmitterInterceptor:
    """EventEmitterInterceptor 테스트"""

    @pytest.mark.asyncio
    async def test_invoke_emitter_method(self, interceptor, service, event_bus):
        """@EventEmitter 메서드 invoke"""
        published_events = []

        async def capture_event(event: Event):
            published_events.append(event)

        # SYNC 모드로 구독해야 즉시 실행됨
        await event_bus.subscribe(
            "user.created", capture_event, mode=SubscriptionMode.SYNC
        )

        invocation = MockMethodInvocation(
            target=service,
            method_name="create_user",
            args=("john",),
            kwargs={},
            return_value={"id": 1, "name": "john"},
        )

        result = await interceptor.invoke(invocation)

        assert result == {"id": 1, "name": "john"}
        assert len(published_events) == 1
        assert published_events[0].event_type == "user.created"

    @pytest.mark.asyncio
    async def test_invoke_no_emitter_method(self, interceptor, service, event_bus):
        """@EventEmitter 없는 메서드 invoke"""
        published_events = []

        async def capture_all(event: Event):
            published_events.append(event)

        invocation = MockMethodInvocation(
            target=service,
            method_name="no_emitter_method",
            args=(),
            kwargs={},
            return_value="no event",
        )

        result = await interceptor.invoke(invocation)

        assert result == "no event"
        assert len(published_events) == 0

    @pytest.mark.asyncio
    async def test_payload_extractor(self, interceptor, service, event_bus):
        """payload_extractor로 특정 필드 추출"""
        published_events = []

        async def capture_event(event: Event):
            published_events.append(event)

        await event_bus.subscribe(
            "order.placed", capture_event, mode=SubscriptionMode.SYNC
        )

        order_data = {"product": "item-1", "quantity": 2}
        invocation = MockMethodInvocation(
            target=service,
            method_name="place_order",
            args=(),
            kwargs={"order_data": order_data},
            return_value={"status": "placed", "order_data": order_data},
        )

        result = await interceptor.invoke(invocation)

        assert len(published_events) == 1
        # payload_extractor가 order_data를 추출
        assert published_events[0].payload == order_data

    @pytest.mark.asyncio
    async def test_condition_true(self, interceptor, service, event_bus):
        """condition이 True면 이벤트 발행"""
        published_events = []

        async def capture_event(event: Event):
            published_events.append(event)

        await event_bus.subscribe(
            "notification.sent", capture_event, mode=SubscriptionMode.SYNC
        )

        invocation = MockMethodInvocation(
            target=service,
            method_name="send_notification",
            args=("Hello",),
            kwargs={},
            return_value={"sent": True, "message": "Hello"},
        )

        result = await interceptor.invoke(invocation)

        assert len(published_events) == 1
        assert published_events[0].payload == {"sent": True, "message": "Hello"}

    @pytest.mark.asyncio
    async def test_condition_false(self, interceptor, service, event_bus):
        """condition이 False면 이벤트 미발행"""
        published_events = []

        async def capture_event(event: Event):
            published_events.append(event)

        await event_bus.subscribe(
            "notification.sent", capture_event, mode=SubscriptionMode.SYNC
        )

        # 조건: result.get('sent', False) -> False이면 미발행
        invocation = MockMethodInvocation(
            target=service,
            method_name="send_notification",
            args=("Hello",),
            kwargs={},
            return_value={"sent": False, "message": "Hello"},  # sent=False
        )

        result = await interceptor.invoke(invocation)

        # 조건이 False라 이벤트 미발행
        assert len(published_events) == 0

    @pytest.mark.asyncio
    async def test_invoke_with_error(self, interceptor, service, event_bus):
        """에러 발생 시 이벤트 미발행"""
        published_events = []

        async def capture_event(event: Event):
            published_events.append(event)

        await event_bus.subscribe(
            "user.created", capture_event, mode=SubscriptionMode.SYNC
        )

        class ErrorInvocation(MockMethodInvocation):
            async def proceed(self):
                raise ValueError("Test error")

        invocation = ErrorInvocation(
            target=service,
            method_name="create_user",
            args=("john",),
            kwargs={},
        )

        with pytest.raises(ValueError, match="Test error"):
            await interceptor.invoke(invocation)

        # 에러 시 이벤트 미발행
        assert len(published_events) == 0


class TestInterceptorEdgeCases:
    """인터셉터 엣지 케이스 테스트"""

    @pytest.mark.asyncio
    async def test_invoke_method_not_found(self, interceptor):
        """존재하지 않는 메서드"""
        mock_target = MagicMock()
        mock_target.nonexistent = None  # 메서드가 없는 것처럼

        invocation = MockMethodInvocation(
            target=mock_target,
            method_name="nonexistent",
            args=(),
            kwargs={},
            return_value=None,
        )

        # 메서드 없으면 그냥 진행
        result = await interceptor.invoke(invocation)
        assert result is None

    @pytest.mark.asyncio
    async def test_event_source_includes_class_and_method(
        self, interceptor, service, event_bus
    ):
        """이벤트 source에 클래스/메서드명 포함"""
        published_events = []

        async def capture_event(event: Event):
            published_events.append(event)

        await event_bus.subscribe(
            "user.created", capture_event, mode=SubscriptionMode.SYNC
        )

        invocation = MockMethodInvocation(
            target=service,
            method_name="create_user",
            args=("john",),
            kwargs={},
            return_value={"id": 1, "name": "john"},
        )

        await interceptor.invoke(invocation)

        assert len(published_events) == 1
        assert "MockService" in published_events[0].source
        assert "create_user" in published_events[0].source
