# 이벤트 시스템 (Event System)

## 개요

Bloom은 두 가지 이벤트 버스를 제공합니다:

| 이벤트 버스           | 용도            | 이벤트 타입   | 커스터마이징    |
| --------------------- | --------------- | ------------- | --------------- |
| `SystemEventBus`      | 프레임워크 내부 | `SystemEvent` | 불가 (내부용)   |
| `ApplicationEventBus` | 비즈니스 로직   | `DomainEvent` | `@Factory` 가능 |

## ApplicationEventBus (도메인 이벤트)

### 빠른 시작

```python
from dataclasses import dataclass
from bloom import Application, Component
from bloom.core.events import DomainEvent, ApplicationEventBus, EventListener

# 1. 도메인 이벤트 정의
@dataclass
class UserCreatedEvent(DomainEvent):
    user_id: str
    username: str

@dataclass
class OrderPlacedEvent(DomainEvent):
    order_id: str
    user_id: str
    amount: float

# 2. 이벤트 리스너 정의
@Component
class NotificationService:
    @EventListener(UserCreatedEvent)
    def on_user_created(self, event: UserCreatedEvent):
        print(f"새 사용자 환영 이메일 발송: {event.username}")

    @EventListener(OrderPlacedEvent)
    def on_order_placed(self, event: OrderPlacedEvent):
        print(f"주문 확인 알림: {event.order_id}")

# 3. 이벤트 발행
@Component
class UserService:
    event_bus: ApplicationEventBus

    def create_user(self, username: str) -> str:
        user_id = f"user-{id(username)}"
        # 비즈니스 로직...

        # 이벤트 발행
        self.event_bus.publish(UserCreatedEvent(
            user_id=user_id,
            username=username
        ))
        return user_id

# 4. 앱 설정
app = Application("myapp")
app.scan(NotificationService)
app.scan(UserService)
app.ready()

service = app.manager.get_instance(UserService)
service.create_user("Alice")
# 출력: 새 사용자 환영 이메일 발송: Alice
```

### @EventListener 데코레이터

```python
from bloom.core.events import EventListener

@Component
class MyEventHandler:
    # 단일 이벤트 타입
    @EventListener(UserCreatedEvent)
    def on_user_created(self, event: UserCreatedEvent):
        pass

    # 여러 이벤트 타입
    @EventListener(OrderPlacedEvent, PaymentReceivedEvent)
    def on_order_events(self, event: DomainEvent):
        if isinstance(event, OrderPlacedEvent):
            # 주문 처리
            pass
        elif isinstance(event, PaymentReceivedEvent):
            # 결제 처리
            pass

    # 비동기 리스너
    @EventListener(UserCreatedEvent)
    async def async_handler(self, event: UserCreatedEvent):
        await send_welcome_email(event.username)
```

### ApplicationEventBus 커스터마이징

기본 `InMemoryEventBus`를 다른 구현으로 교체할 수 있습니다:

```python
from bloom import Component
from bloom.core.decorators import Factory
from bloom.core.events import ApplicationEventBus

# Redis 기반 이벤트 버스 (예시)
class RedisEventBus(ApplicationEventBus):
    def __init__(self, redis_url: str):
        super().__init__()
        self.redis = Redis.from_url(redis_url)

    def publish(self, event):
        # Redis에 이벤트 발행
        self.redis.publish(type(event).__name__, event.to_json())
        # 로컬 리스너도 실행
        super().publish(event)

@Component
class EventConfig:
    @Factory
    def event_bus(self) -> ApplicationEventBus:
        return RedisEventBus("redis://localhost:6379/0")
```

## SystemEventBus (시스템 이벤트)

프레임워크 내부에서 발생하는 이벤트입니다. 디버깅, 모니터링, 프로파일링에 활용합니다.

### 시스템 이벤트 종류

```python
from bloom.core.events import (
    InstanceCreatedEvent,   # PROTOTYPE/REQUEST 인스턴스 생성
    MethodEnteredEvent,     # 메서드 진입
    MethodExitedEvent,      # 메서드 정상 종료
    MethodErrorEvent,       # 메서드 예외 발생
)
```

### InstanceCreatedEvent

PROTOTYPE 또는 REQUEST 스코프 인스턴스가 생성될 때 발행됩니다.

```python
@dataclass
class InstanceCreatedEvent(SystemEvent):
    instance: Any           # 생성된 인스턴스
    instance_type: type     # 인스턴스 타입
    scope: Scope            # PROTOTYPE 또는 REQUEST
```

### MethodEnteredEvent / MethodExitedEvent / MethodErrorEvent

`CallStackTraceAdvice`가 활성화되면 발행됩니다.

```python
@dataclass
class MethodEnteredEvent(SystemEvent):
    frame: CallFrame        # 콜 프레임

@dataclass
class MethodExitedEvent(SystemEvent):
    frame: CallFrame
    duration_ms: float      # 실행 시간

@dataclass
class MethodErrorEvent(SystemEvent):
    frame: CallFrame
    error: Exception        # 발생한 예외
```

### 시스템 이벤트 구독 (고급)

```python
from bloom.core.events import SystemEvent, InstanceCreatedEvent

@Component
class MetricsCollector:
    system_events: SystemEventBus  # 직접 주입

    @PostConstruct
    def setup(self):
        self.system_events.subscribe(
            InstanceCreatedEvent,
            self._on_instance_created
        )

    def _on_instance_created(self, event: InstanceCreatedEvent):
        # 메트릭 수집
        metrics.counter("prototype_created").inc(
            labels={"type": event.instance_type.__name__}
        )
```

## 이벤트 클래스 계층

```
Event (ABC)
├── SystemEvent (프레임워크 내부)
│   ├── InstanceCreatedEvent
│   ├── MethodEnteredEvent
│   ├── MethodExitedEvent
│   └── MethodErrorEvent
└── DomainEvent (비즈니스 로직)
    ├── UserCreatedEvent
    ├── OrderPlacedEvent
    └── ... (사용자 정의)
```

## 이벤트 버스 구조

### InMemoryEventBus (기본 구현)

```python
class InMemoryEventBus(EventBus):
    """
    메모리 기반 동기 이벤트 버스

    - 이벤트 발행 시 등록된 리스너를 순차 실행
    - async 리스너는 asyncio.create_task()로 실행
    """

    def subscribe(self, event_type: type[E], handler: EventHandler[E]) -> None:
        """이벤트 타입에 핸들러 등록"""

    def unsubscribe(self, event_type: type[E], handler: EventHandler[E]) -> None:
        """핸들러 등록 해제"""

    def publish(self, event: Event) -> None:
        """이벤트 발행 - 등록된 핸들러들 실행"""
```

### 커스텀 이벤트 버스 구현

```python
from bloom.core.events import EventBus, Event, EventHandler

class AsyncQueueEventBus(EventBus):
    """비동기 큐 기반 이벤트 버스 예시"""

    def __init__(self):
        self._queue = asyncio.Queue()
        self._handlers: dict[type, list[EventHandler]] = {}

    def subscribe(self, event_type, handler):
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def publish(self, event):
        # 큐에 이벤트 추가 (비동기 처리)
        asyncio.create_task(self._queue.put(event))

    async def process_events(self):
        """백그라운드에서 이벤트 처리"""
        while True:
            event = await self._queue.get()
            for handler in self._handlers.get(type(event), []):
                try:
                    result = handler(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"Event handler error: {e}")
```

## 이벤트 발행 흐름

### DomainEvent 발행 흐름

```
UserService.create_user()
    │
    ▼
ApplicationEventBus.publish(UserCreatedEvent)
    │
    ├─► NotificationService.on_user_created()
    │
    ├─► AuditService.log_user_creation()
    │
    └─► AnalyticsService.track_signup()
```

### SystemEvent 발행 흐름

```
LazyFieldProxy._lfp_resolve()
    │
    ▼ (PROTOTYPE 생성 시)
SystemEventBus.publish(InstanceCreatedEvent)
    │
    └─► MetricsCollector._on_instance_created()


CallStackTraceAdvice.before()
    │
    ▼
SystemEventBus.publish(MethodEnteredEvent)
    │
    └─► TracingService._on_method_entered()
```

## 모범 사례

### 1. 이벤트는 불변으로 정의

```python
from dataclasses import dataclass

@dataclass(frozen=True)  # 불변
class UserCreatedEvent(DomainEvent):
    user_id: str
    username: str
    created_at: datetime = field(default_factory=datetime.now)
```

### 2. 이벤트 핸들러는 빠르게 반환

```python
@Component
class EmailService:
    task_backend: AsyncioTaskBackend

    @EventListener(UserCreatedEvent)
    def on_user_created(self, event: UserCreatedEvent):
        # ❌ 오래 걸리는 작업을 동기로 실행
        # send_email(event.username)

        # ✅ 백그라운드 태스크로 위임
        self.send_welcome_email.delay(event.username)

    @Task
    def send_welcome_email(self, username: str):
        # 실제 이메일 발송
        pass
```

### 3. 이벤트 타입별 구분 명확히

```python
# ✅ 명확한 이벤트 타입
@dataclass
class UserRegisteredEvent(DomainEvent):
    user_id: str

@dataclass
class UserVerifiedEvent(DomainEvent):
    user_id: str

@dataclass
class UserDeletedEvent(DomainEvent):
    user_id: str

# ❌ 모호한 이벤트 타입
@dataclass
class UserEvent(DomainEvent):
    user_id: str
    action: str  # "registered", "verified", "deleted"
```

### 4. 순환 이벤트 주의

```python
@Component
class ServiceA:
    event_bus: ApplicationEventBus

    @EventListener(EventB)
    def on_event_b(self, event):
        # ⚠️ EventA 발행 → ServiceB가 EventB 발행 → 무한 루프!
        self.event_bus.publish(EventA(...))

@Component
class ServiceB:
    event_bus: ApplicationEventBus

    @EventListener(EventA)
    def on_event_a(self, event):
        self.event_bus.publish(EventB(...))  # 순환!
```

## Container-Element 패턴

`@EventListener`는 Container-Element 패턴을 따릅니다:

```python
# bloom/core/events/application.py
class EventListenerElement(Element):
    """@EventListener 메타데이터를 담는 Element"""

    key = "event_listener"

    def __init__(self, event_types: tuple[type[DomainEvent], ...]):
        super().__init__()
        self.metadata["event_types"] = event_types

def EventListener(*event_types: type[DomainEvent]):
    def decorator(method):
        container = HandlerContainer.get_or_create(method)
        container.add_elements(EventListenerElement(event_types))
        return method
    return decorator
```

## 관련 문서

- [PROTOTYPE 스코프와 자동 라이프사이클 관리](./prototype-scope.md)
- [콜스택 추적 시스템](./tracing-system.md)
- [Method Advice 패턴](./method-advice-pattern.md)
