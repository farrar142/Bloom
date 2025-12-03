"""bloom.core.event.decorators - 이벤트 데코레이터

@EventListener, @EventEmitter 데코레이터를 제공합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, ParamSpec, TYPE_CHECKING
from functools import wraps

from .bus import SubscriptionMode
from .models import Event, get_event_type

if TYPE_CHECKING:
    pass


P = ParamSpec("P")
R = TypeVar("R")
F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# Metadata Classes
# =============================================================================


@dataclass
class EventListenerInfo:
    """이벤트 리스너 메타데이터"""

    event_type: str | type[Event] | None
    mode: SubscriptionMode
    priority: int
    condition: str | None
    method: Callable[..., Any] | None = None


@dataclass
class EventEmitterInfo:
    """이벤트 발행자 메타데이터"""

    event_type: str | type[Event]
    condition: str | None
    payload_extractor: Callable[[Any], Any] | None
    method: Callable[..., Any] | None = None


# =============================================================================
# @EventListener Decorator
# =============================================================================


def EventListener(
    event_type: str | type[Event] | None = None,
    *,
    mode: SubscriptionMode = SubscriptionMode.ASYNC,
    priority: int = 0,
    condition: str | None = None,
) -> Callable[[F], F]:
    """이벤트 리스너 데코레이터

    메서드를 이벤트 리스너로 등록합니다.
    ApplicationContext 시작 시 자동으로 EventBus에 구독됩니다.

    Args:
        event_type: 구독할 이벤트 타입 (문자열 또는 이벤트 클래스)
                   None이면 메서드의 첫 번째 파라미터 타입에서 추론
        mode: 구독 모드
            - SYNC: 동기 처리 (같은 트랜잭션 내)
            - ASYNC: 비동기 처리 (백그라운드)
        priority: 핸들러 우선순위 (높을수록 먼저 실행)
        condition: 조건부 실행 조건 (Python 표현식)

    Examples:
        @Component
        class NotificationService:
            # 비동기 처리 (기본)
            @EventListener("user.created")
            async def send_welcome_email(self, event: Event):
                await self.email.send(event.payload["email"], "Welcome!")

            # 동기 처리 (같은 트랜잭션)
            @EventListener("order.created", mode=SubscriptionMode.SYNC)
            async def reserve_inventory(self, event: Event):
                await self.inventory.reserve(event.payload["items"])

            # 타입에서 이벤트 타입 추론
            @EventListener()
            async def on_user_created(self, event: UserCreatedEvent):
                ...

            # 조건부 실행
            @EventListener("order.created", condition="payload.get('total') > 10000")
            async def notify_large_order(self, event: Event):
                ...

            # 높은 우선순위
            @EventListener("payment.completed", priority=100)
            async def process_payment_first(self, event: Event):
                ...
    """

    def decorator(func: F) -> F:
        # 메타데이터 저장
        info = EventListenerInfo(
            event_type=event_type,
            mode=mode,
            priority=priority,
            condition=condition,
            method=func,
        )

        if not hasattr(func, "__bloom_event_listeners__"):
            func.__bloom_event_listeners__ = []  # type: ignore
        func.__bloom_event_listeners__.append(info)  # type: ignore

        return func

    return decorator


def SyncEventListener(
    event_type: str | type[Event] | None = None,
    *,
    priority: int = 0,
    condition: str | None = None,
) -> Callable[[F], F]:
    """동기 이벤트 리스너 데코레이터

    EventListener(mode=SubscriptionMode.SYNC)의 축약형입니다.
    같은 트랜잭션 내에서 처리해야 하는 경우 사용합니다.

    Examples:
        @Component
        class OrderService:
            @SyncEventListener("order.created")
            async def validate_order(self, event: Event):
                # 주문 생성과 같은 트랜잭션에서 실행
                if not self.is_valid(event.payload):
                    raise ValidationError("Invalid order")
    """
    return EventListener(
        event_type,
        mode=SubscriptionMode.SYNC,
        priority=priority,
        condition=condition,
    )


def AsyncEventListener(
    event_type: str | type[Event] | None = None,
    *,
    priority: int = 0,
    condition: str | None = None,
) -> Callable[[F], F]:
    """비동기 이벤트 리스너 데코레이터

    EventListener(mode=SubscriptionMode.ASYNC)의 축약형입니다.
    백그라운드에서 처리해도 되는 경우 사용합니다.

    Examples:
        @Component
        class NotificationService:
            @AsyncEventListener("user.created")
            async def send_welcome_email(self, event: Event):
                # 백그라운드에서 비동기 처리
                await self.email.send(...)
    """
    return EventListener(
        event_type,
        mode=SubscriptionMode.ASYNC,
        priority=priority,
        condition=condition,
    )


# =============================================================================
# @EventEmitter Decorator
# =============================================================================


def EventEmitter(
    event_type: str | type[Event],
    *,
    condition: str | None = None,
    payload_extractor: Callable[[Any], Any] | None = None,
) -> Callable[[F], F]:
    """이벤트 발행 데코레이터

    메서드 실행 후 자동으로 이벤트를 발행합니다.
    메서드의 반환값이 이벤트의 payload가 됩니다.

    Args:
        event_type: 발행할 이벤트 타입
        condition: 조건부 발행 조건 (Python 표현식, result 변수 사용 가능)
        payload_extractor: 반환값에서 payload 추출 함수

    Examples:
        @Component
        class UserService:
            # 기본 사용
            @EventEmitter("user.created")
            async def create_user(self, name: str) -> User:
                user = User(name=name)
                await self.repo.save(user)
                return user  # 이것이 event.payload가 됨

            # 조건부 발행
            @EventEmitter("order.large", condition="result.total > 10000")
            async def create_order(self, items: list) -> Order:
                return await self.repo.save(Order(items=items))

            # payload 추출
            @EventEmitter(
                "user.updated",
                payload_extractor=lambda user: {"id": user.id, "name": user.name}
            )
            async def update_user(self, user: User) -> User:
                return await self.repo.save(user)
    """

    def decorator(func: F) -> F:
        # 메타데이터 저장
        info = EventEmitterInfo(
            event_type=event_type,
            condition=condition,
            payload_extractor=payload_extractor,
            method=func,
        )

        if not hasattr(func, "__bloom_event_emitters__"):
            func.__bloom_event_emitters__ = []  # type: ignore
        func.__bloom_event_emitters__.append(info)  # type: ignore

        return func

    return decorator


# =============================================================================
# Helper Functions
# =============================================================================


def get_event_listeners(method: Callable[..., Any]) -> list[EventListenerInfo]:
    """메서드의 EventListener 정보 조회"""
    return getattr(method, "__bloom_event_listeners__", [])


def get_event_emitters(method: Callable[..., Any]) -> list[EventEmitterInfo]:
    """메서드의 EventEmitter 정보 조회"""
    return getattr(method, "__bloom_event_emitters__", [])


def has_event_listener(method: Callable[..., Any]) -> bool:
    """메서드가 EventListener인지 확인"""
    return bool(getattr(method, "__bloom_event_listeners__", None))


def has_event_emitter(method: Callable[..., Any]) -> bool:
    """메서드가 EventEmitter인지 확인"""
    return bool(getattr(method, "__bloom_event_emitters__", None))


def resolve_event_type(
    info: EventListenerInfo,
    method: Callable[..., Any],
) -> str:
    """EventListener의 event_type 해석

    event_type이 None이면 메서드의 첫 번째 파라미터 타입에서 추론합니다.
    """
    if info.event_type is not None:
        return get_event_type(info.event_type)

    # 타입 힌트에서 추론
    import inspect
    from typing import get_type_hints

    try:
        hints = get_type_hints(method)
        sig = inspect.signature(method)
        params = list(sig.parameters.values())

        # self를 제외한 첫 번째 파라미터
        for param in params:
            if param.name == "self":
                continue
            param_type = hints.get(param.name)
            if param_type and isinstance(param_type, type) and issubclass(param_type, Event):
                return get_event_type(param_type)
            break
    except Exception:
        pass

    raise ValueError(
        f"Cannot infer event_type for {method.__name__}. "
        "Please specify event_type explicitly."
    )
