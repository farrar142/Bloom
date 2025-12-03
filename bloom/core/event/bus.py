"""bloom.core.event.bus - 이벤트 버스 인터페이스

이벤트 버스의 추상 인터페이스와 구독 모델을 정의합니다.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Awaitable, TypeVar, Generic, TYPE_CHECKING

from .models import Event, EventResult, EventStatus, get_event_type

if TYPE_CHECKING:
    pass


# =============================================================================
# Type Aliases
# =============================================================================


# 이벤트 핸들러 타입
EventHandler = Callable[[Event], Awaitable[Any]]
SyncEventHandler = Callable[[Event], Any]


# =============================================================================
# Subscription Models
# =============================================================================


class SubscriptionMode(Enum):
    """구독 모드"""

    SYNC = auto()  # 동기 처리 (같은 트랜잭션 내)
    ASYNC = auto()  # 비동기 처리 (백그라운드)


@dataclass
class Subscription:
    """이벤트 구독 정보

    Attributes:
        subscription_id: 고유 구독 ID
        event_type: 구독할 이벤트 타입
        handler: 이벤트 핸들러
        mode: 구독 모드 (동기/비동기)
        priority: 핸들러 우선순위 (높을수록 먼저 실행)
        condition: 조건부 실행 조건
        created_at: 구독 생성 시간
        handler_name: 핸들러 이름 (디버깅용)
    """

    event_type: str
    handler: EventHandler | SyncEventHandler
    subscription_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    mode: SubscriptionMode = SubscriptionMode.ASYNC
    priority: int = 0
    condition: str | None = None
    created_at: datetime = field(default_factory=datetime.now)
    handler_name: str | None = None

    def __post_init__(self):
        if self.handler_name is None:
            self.handler_name = getattr(self.handler, "__name__", "anonymous")

    def __hash__(self) -> int:
        return hash(self.subscription_id)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Subscription):
            return self.subscription_id == other.subscription_id
        return False


@dataclass
class SubscriptionGroup:
    """동일 event_type에 대한 구독 그룹"""

    event_type: str
    subscriptions: list[Subscription] = field(default_factory=list)

    def add(self, subscription: Subscription) -> None:
        """구독 추가 (우선순위 순으로 정렬)"""
        self.subscriptions.append(subscription)
        self.subscriptions.sort(key=lambda s: -s.priority)

    def remove(self, subscription_id: str) -> bool:
        """구독 제거"""
        for i, sub in enumerate(self.subscriptions):
            if sub.subscription_id == subscription_id:
                self.subscriptions.pop(i)
                return True
        return False

    def get_sync_handlers(self) -> list[Subscription]:
        """동기 핸들러 목록"""
        return [s for s in self.subscriptions if s.mode == SubscriptionMode.SYNC]

    def get_async_handlers(self) -> list[Subscription]:
        """비동기 핸들러 목록"""
        return [s for s in self.subscriptions if s.mode == SubscriptionMode.ASYNC]


# =============================================================================
# EventBus Interface
# =============================================================================


class EventBus(ABC):
    """이벤트 버스 추상 인터페이스

    이벤트의 발행과 구독을 관리하는 핵심 인터페이스입니다.

    구현체:
        - LocalEventBus: 인메모리 이벤트 버스 (단일 프로세스)
        - RedisEventBus: Redis Pub/Sub 기반 (분산 환경)

    Examples:
        # 구독
        async def on_user_created(event: Event):
            print(f"User created: {event.payload}")

        subscription = await event_bus.subscribe("user.created", on_user_created)

        # 발행
        await event_bus.publish(Event(event_type="user.created", payload={"id": 1}))

        # 구독 해제
        await event_bus.unsubscribe(subscription)
    """

    @abstractmethod
    async def publish(
        self,
        event: Event,
        *,
        wait_for_handlers: bool = False,
    ) -> list[EventResult]:
        """이벤트 발행

        Args:
            event: 발행할 이벤트
            wait_for_handlers: True면 모든 핸들러 완료까지 대기

        Returns:
            이벤트 처리 결과 리스트 (wait_for_handlers=True인 경우)
        """
        pass

    @abstractmethod
    async def publish_sync(self, event: Event) -> list[EventResult]:
        """동기 이벤트 발행 (동기 핸들러만 실행)

        같은 트랜잭션 내에서 처리해야 하는 경우 사용합니다.

        Args:
            event: 발행할 이벤트

        Returns:
            동기 핸들러 처리 결과 리스트
        """
        pass

    @abstractmethod
    async def subscribe(
        self,
        event_type: str | type[Event],
        handler: EventHandler | SyncEventHandler,
        *,
        mode: SubscriptionMode = SubscriptionMode.ASYNC,
        priority: int = 0,
        condition: str | None = None,
    ) -> Subscription:
        """이벤트 구독

        Args:
            event_type: 구독할 이벤트 타입
            handler: 이벤트 핸들러
            mode: 구독 모드 (SYNC: 동기, ASYNC: 비동기)
            priority: 핸들러 우선순위 (높을수록 먼저 실행)
            condition: 조건부 실행 조건

        Returns:
            구독 정보
        """
        pass

    @abstractmethod
    async def unsubscribe(self, subscription: Subscription | str) -> bool:
        """구독 해제

        Args:
            subscription: 구독 정보 또는 구독 ID

        Returns:
            해제 성공 여부
        """
        pass

    @abstractmethod
    def get_subscriptions(self, event_type: str | None = None) -> list[Subscription]:
        """구독 목록 조회

        Args:
            event_type: 특정 이벤트 타입의 구독만 조회 (None이면 전체)

        Returns:
            구독 목록
        """
        pass

    @abstractmethod
    async def start(self) -> None:
        """이벤트 버스 시작

        백그라운드 워커 등을 시작합니다.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """이벤트 버스 종료

        대기 중인 이벤트를 처리하고 종료합니다.
        """
        pass

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """이벤트 버스 실행 중 여부"""
        pass


# =============================================================================
# EventPublisher (Simplified Interface)
# =============================================================================


class EventPublisher:
    """이벤트 발행 전용 인터페이스

    서비스에서 이벤트 버스의 발행 기능만 주입받을 때 사용합니다.

    Examples:
        @Component
        class UserService:
            def __init__(self, event_publisher: EventPublisher):
                self.event_publisher = event_publisher

            async def create_user(self, name: str) -> User:
                user = await self.repo.save(User(name=name))
                await self.event_publisher.publish(
                    Event(event_type="user.created", payload=user)
                )
                return user
    """

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

    async def publish(
        self,
        event: Event,
        *,
        wait_for_handlers: bool = False,
    ) -> list[EventResult]:
        """이벤트 발행"""
        return await self._event_bus.publish(event, wait_for_handlers=wait_for_handlers)

    async def publish_sync(self, event: Event) -> list[EventResult]:
        """동기 이벤트 발행"""
        return await self._event_bus.publish_sync(event)

    def emit(
        self,
        event_type: str | type[Event],
        payload: Any = None,
        **kwargs: Any,
    ) -> Awaitable[list[EventResult]]:
        """간편한 이벤트 발행

        Args:
            event_type: 이벤트 타입
            payload: 페이로드
            **kwargs: 추가 이벤트 속성

        Examples:
            await publisher.emit("user.created", {"user_id": 1})
            await publisher.emit(UserCreatedEvent, UserCreatedPayload(user_id=1))
        """
        from .models import create_event

        event = create_event(event_type, payload, **kwargs)
        return self.publish(event)
