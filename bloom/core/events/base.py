"""이벤트 시스템 베이스 클래스"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Generic, TypeVar


# =============================================================================
# Event 베이스
# =============================================================================


@dataclass
class Event:
    """
    모든 이벤트의 베이스 클래스

    Attributes:
        timestamp: 이벤트 발생 시간
    """

    timestamp: datetime = field(default_factory=datetime.now)


E = TypeVar("E", bound=Event)


# =============================================================================
# EventBus 추상 인터페이스
# =============================================================================


class EventBus(ABC, Generic[E]):
    """
    이벤트 버스 추상 인터페이스

    이벤트를 발행하고 구독하는 pub/sub 패턴을 제공합니다.
    """

    @abstractmethod
    def publish(self, event: E) -> None:
        """
        이벤트 발행

        Args:
            event: 발행할 이벤트
        """
        ...

    @abstractmethod
    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """
        이벤트 구독

        Args:
            event_type: 구독할 이벤트 타입
            handler: 이벤트 핸들러 함수
        """
        ...

    @abstractmethod
    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """
        구독 해제

        Args:
            event_type: 구독 해제할 이벤트 타입
            handler: 제거할 핸들러 함수
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """모든 구독 해제"""
        ...


# =============================================================================
# InMemoryEventBus 구현
# =============================================================================


class InMemoryEventBus(EventBus[E]):
    """
    메모리 기반 이벤트 버스 구현

    동기적으로 이벤트를 처리합니다.
    이벤트 타입의 상속 계층을 고려하여 부모 타입 핸들러도 호출합니다.
    """

    def __init__(self):
        self._handlers: dict[type, list[Callable[[Any], None]]] = {}

    def publish(self, event: E) -> None:
        """
        이벤트 발행

        이벤트 타입과 그 부모 타입에 등록된 모든 핸들러를 호출합니다.
        """
        event_type = type(event)
        called_handlers: set[int] = set()  # 중복 호출 방지

        # 이벤트 타입 계층을 순회 (자기 자신 → 부모들)
        for cls in event_type.__mro__:
            if cls is object:
                continue

            handlers = self._handlers.get(cls, [])
            for handler in handlers:
                handler_id = id(handler)
                if handler_id not in called_handlers:
                    handler(event)
                    called_handlers.add(handler_id)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """이벤트 구독"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """구독 해제"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass  # 핸들러가 없으면 무시

    def clear(self) -> None:
        """모든 구독 해제"""
        self._handlers.clear()

    def __len__(self) -> int:
        """등록된 총 핸들러 수"""
        return sum(len(handlers) for handlers in self._handlers.values())
