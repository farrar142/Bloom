"""분산 이벤트 버스 - 브로커 기반

Task 시스템의 Broker를 재사용하여 분산 환경에서 이벤트를 발행/구독합니다.
이벤트는 JSON으로 직렬화되어 브로커를 통해 전송됩니다.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from .base import Event, EventBus

if TYPE_CHECKING:
    from bloom.task.broker import Broker

E = TypeVar("E", bound=Event)


# =============================================================================
# 이벤트 메시지 (직렬화용)
# =============================================================================


class EventMessage:
    """
    브로커를 통해 전달되는 이벤트 메시지

    Event 프로토콜의 model_dump()/model_validate()를 활용합니다.

    Attributes:
        event_type: 이벤트 클래스의 전체 경로 (module.ClassName)
        event_data: 이벤트 데이터 (model_dump() 결과)
    """

    def __init__(
        self,
        event_type: str,
        event_data: dict[str, Any],
    ):
        self.event_type = event_type
        self.event_data = event_data

    def to_json(self) -> str:
        """JSON 문자열로 직렬화"""
        return json.dumps(
            {
                "event_type": self.event_type,
                "event_data": self.event_data,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "EventMessage":
        """JSON 문자열에서 역직렬화"""
        obj = json.loads(data)
        return cls(
            event_type=obj["event_type"],
            event_data=obj["event_data"],
        )

    @classmethod
    def from_event(cls, event: Event) -> "EventMessage":
        """Event 객체에서 메시지 생성 (Event.model_dump() 사용)"""
        event_type = f"{event.__class__.__module__}.{event.__class__.__name__}"
        event_data = event.model_dump()
        return cls(event_type=event_type, event_data=event_data)


# =============================================================================
# 이벤트 타입 레지스트리
# =============================================================================


class EventTypeRegistry:
    """
    이벤트 타입 레지스트리

    문자열 타입명 → 이벤트 클래스 매핑을 관리합니다.
    역직렬화 시 올바른 클래스를 찾는 데 사용됩니다.
    """

    _registry: dict[str, type[Event]] = {}

    @classmethod
    def register(cls, event_type: type[Event]) -> None:
        """이벤트 타입 등록"""
        type_name = f"{event_type.__module__}.{event_type.__name__}"
        cls._registry[type_name] = event_type

    @classmethod
    def get(cls, type_name: str) -> type[Event] | None:
        """타입명으로 이벤트 클래스 조회"""
        return cls._registry.get(type_name)

    @classmethod
    def reconstruct(cls, message: EventMessage) -> Event | None:
        """EventMessage에서 Event 객체 복원 (model_validate() 사용)"""
        event_cls = cls.get(message.event_type)
        if event_cls is None:
            return None

        try:
            # Event 프로토콜의 model_validate 사용
            return event_cls.model_validate(message.event_data)
        except Exception:
            # 생성 실패 시 None 반환
            return None


# =============================================================================
# 분산 이벤트 버스
# =============================================================================


class DistributedEventBus(EventBus[E]):
    """
    브로커 기반 분산 이벤트 버스

    Task의 Broker를 재사용하여 이벤트를 분산 발행합니다.
    내부 버스 없이 순수하게 브로커만 사용합니다.

    - publish(): 동기 발행 (Broker.enqueue_raw_sync)
    - publish_async(): 비동기 발행 (Broker.enqueue_raw)
    - start_consumer(): 브로커에서 이벤트 수신하여 핸들러 호출

    사용법:
        from bloom.task.broker import RedisBroker

        broker = RedisBroker("redis://localhost:6379/0")
        event_bus = DistributedEventBus(broker, queue="events")

        # 구독 (소비자 측에서만 의미 있음)
        event_bus.subscribe(UserCreatedEvent, handle_user_created)

        # 동기 발행
        event_bus.publish(UserCreatedEvent(user_id="123"))

        # 비동기 발행
        await event_bus.publish_async(UserCreatedEvent(user_id="123"))

        # 소비자 시작
        await event_bus.start_consumer()
    """

    def __init__(
        self,
        broker: "Broker",
        queue: str = "events",
    ):
        """
        Args:
            broker: 메시지 브로커 (RedisBroker 등)
            queue: 이벤트 큐 이름
        """
        self._broker = broker
        self._queue = queue
        self._handlers: dict[type[Event], list[Callable[[Any], None]]] = {}
        self._running = False
        self._consumer_task: asyncio.Task[None] | None = None

    # =========================================================================
    # EventBus 인터페이스 구현
    # =========================================================================

    def publish(self, event: E) -> None:
        """
        동기 발행

        이벤트를 직렬화하여 브로커에 동기적으로 발행합니다.
        """
        message = EventMessage.from_event(event)
        self._broker.enqueue_raw_sync(self._queue, message.to_json())

    async def publish_async(self, event: E) -> None:
        """
        비동기 발행

        이벤트를 직렬화하여 브로커에 발행합니다.
        """
        message = EventMessage.from_event(event)
        await self._broker.enqueue_raw(self._queue, message.to_json())

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """이벤트 구독"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
        # 역직렬화를 위해 타입 등록
        EventTypeRegistry.register(event_type)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """구독 해제"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    def clear(self) -> None:
        """모든 구독 해제"""
        self._handlers.clear()

    # =========================================================================
    # 분산 기능
    # =========================================================================

    async def start_consumer(self) -> None:
        """
        이벤트 소비자 시작

        브로커에서 이벤트를 가져와 등록된 핸들러에 전달합니다.
        """
        self._running = True

        while self._running:
            try:
                raw_message = await self._broker.dequeue_raw(self._queue, timeout=1.0)
                if raw_message:
                    self._process_message(raw_message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Event consumer error: {e}")
                await asyncio.sleep(1.0)

    async def stop_consumer(self) -> None:
        """이벤트 소비자 중지"""
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

    def _process_message(self, raw_message: str) -> None:
        """메시지 처리"""
        try:
            message = EventMessage.from_json(raw_message)
            event = EventTypeRegistry.reconstruct(message)

            if event:
                self._dispatch(event)
        except Exception as e:
            print(f"Failed to process event message: {e}")

    def _dispatch(self, event: Event) -> None:
        """이벤트를 핸들러에 전달"""
        event_type = type(event)

        # 정확한 타입 핸들러
        handlers = self._handlers.get(event_type)
        if handlers:
            for handler in handlers:
                handler(event)

        # 부모 타입 핸들러도 호출
        for cls in event_type.__mro__[1:]:
            if cls is object:
                continue
            parent_handlers = self._handlers.get(cls)
            if parent_handlers:
                for handler in parent_handlers:
                    handler(event)

    # =========================================================================
    # 컨텍스트 매니저
    # =========================================================================

    async def __aenter__(self) -> "DistributedEventBus[E]":
        await self._broker.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop_consumer()
        await self._broker.disconnect()
