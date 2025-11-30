# PROTOTYPE 스코프와 자동 라이프사이클 관리

## 개요

Bloom의 PROTOTYPE 스코프는 필드에 접근할 때마다 새 인스턴스를 생성합니다.
**콜스택 기반 자동 정리** 기능으로 메서드 종료 시 해당 메서드에서 생성된
PROTOTYPE 인스턴스들의 `@PreDestroy`가 자동으로 호출됩니다.

## 스코프 종류

| Scope       | 설명                               | 인스턴스 저장 위치            | 라이프사이클              |
| ----------- | ---------------------------------- | ----------------------------- | ------------------------- |
| `SINGLETON` | 앱 전체에서 단일 인스턴스 (기본값) | `ContainerManager`            | 앱 시작 ~ 앱 종료         |
| `PROTOTYPE` | 접근할 때마다 새 인스턴스 생성     | 저장하지 않음 (콜스택 추적)   | 메서드 시작 ~ 메서드 종료 |
| `REQUEST`   | HTTP 요청마다 새 인스턴스          | `RequestContext` (ContextVar) | 요청 시작 ~ 요청 종료     |

## PROTOTYPE 모드

`PrototypeMode`로 PROTOTYPE의 인스턴스 캐싱 방식을 지정합니다:

| Mode          | 설명                                    | 사용 사례                                   |
| ------------- | --------------------------------------- | ------------------------------------------- |
| `DEFAULT`     | 매번 새 인스턴스 생성 (기본값)          | 상태 없는 객체, 매번 새로운 컨텍스트 필요   |
| `CALL_SCOPED` | 같은 핸들러 호출 내에서는 같은 인스턴스 | 같은 트랜잭션 내 DB 연결 공유, Unit of Work |

```python
from bloom import Component
from bloom.core import Scope, ScopeEnum, PrototypeMode

@Component
@Scope(ScopeEnum.PROTOTYPE)  # DEFAULT: 매번 새 인스턴스
class DefaultPrototype:
    pass

@Component
@Scope(ScopeEnum.PROTOTYPE, mode=PrototypeMode.CALL_SCOPED)  # 핸들러 내 공유
class CallScopedPrototype:
    pass
```

## 빠른 시작

```python
from bloom import Application, Component
from bloom.core import Scope, ScopeEnum
from bloom.core.decorators import PostConstruct, PreDestroy, Handler, Factory
from bloom.core.advice import MethodAdvice, MethodAdviceRegistry, CallStackTraceAdvice

@Component
@Scope(ScopeEnum.PROTOTYPE)
class DatabaseConnection:
    connection_id: int = 0

    @PostConstruct
    def connect(self):
        self.connection_id = id(self)
        print(f"연결 생성: {self.connection_id}")

    @PreDestroy
    def disconnect(self):
        print(f"연결 해제: {self.connection_id}")

# TracingAdvice 필수! (콜스택 관리)
@Component
class TracingAdvice(CallStackTraceAdvice):
    pass

@Component
class AdviceConfig:
    @Factory
    def registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
        reg = MethodAdviceRegistry()
        for advice in advices:
            reg.register(advice)
        return reg

@Component
class UserService:
    db: DatabaseConnection


    def create_user(self, name: str) -> str:
        # PROTOTYPE 접근 시 새 인스턴스 생성 + @PostConstruct
        conn_id = self.db.connection_id
        print(f"사용자 생성: {name} (연결: {conn_id})")
        return f"user-{conn_id}"
        # 메서드 종료 시 자동으로 @PreDestroy 호출!

app = Application("myapp")
app.scan(DatabaseConnection)
app.scan(TracingAdvice)
app.scan(AdviceConfig)
app.scan(UserService)
app.ready()

service = app.manager.get_instance(UserService)
service.create_user("Alice")
# 출력:
# 연결 생성: 4381234567
# 사용자 생성: Alice (연결: 4381234567)
# 연결 해제: 4381234567
```

## CALL_SCOPED: 핸들러 내 인스턴스 공유

`CALL_SCOPED` 모드는 같은 핸들러 호출 내에서 동일한 인스턴스를 반환합니다.
여러 서비스에서 같은 DB 연결이나 트랜잭션을 공유할 때 유용합니다.

```python
from bloom import Application, Component
from bloom.core import Scope, ScopeEnum, PrototypeMode
from bloom.core.decorators import Handler, Factory
from bloom.core.advice import MethodAdvice, MethodAdviceRegistry, CallStackTraceAdvice

@Component
@Scope(ScopeEnum.PROTOTYPE, mode=PrototypeMode.CALL_SCOPED)
class TransactionContext:
    """핸들러 호출 내에서 공유되는 트랜잭션 컨텍스트"""
    tx_id: str = ""

    def __init__(self):
        import uuid
        self.tx_id = str(uuid.uuid4())[:8]
        print(f"트랜잭션 시작: {self.tx_id}")

    def get_id(self) -> str:
        return self.tx_id

@Component
class TracingAdvice(CallStackTraceAdvice):
    pass

@Component
class AdviceConfig:
    @Factory
    def registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
        reg = MethodAdviceRegistry()
        for a in advices:
            reg.register(a)
        return reg

@Component
class OrderRepository:
    tx: TransactionContext

    def save_order(self, order_id: str):
        print(f"주문 저장 (tx: {self.tx.tx_id})")

@Component
class PaymentService:
    tx: TransactionContext

    def process_payment(self, amount: int):
        print(f"결제 처리 (tx: {self.tx.tx_id})")

@Component
class OrderService:
    tx: TransactionContext
    order_repo: OrderRepository
    payment: PaymentService

    @Handler  # 핸들러로 지정해야 콜스택 추적됨
    def create_order(self, order_id: str, amount: int):
        # 모든 서비스에서 같은 TransactionContext 공유
        print(f"주문 생성 (tx: {self.tx.tx_id})")
        self.order_repo.save_order(order_id)
        self.payment.process_payment(amount)
        return self.tx.tx_id

app = Application("order_app")
app.scan(TransactionContext, TracingAdvice, AdviceConfig)
app.scan(OrderRepository, PaymentService, OrderService)
app.ready()

service = app.manager.get_instance(OrderService)

# 첫 번째 주문 - 하나의 트랜잭션
tx1 = service.create_order("order-1", 100)
# 출력:
# 트랜잭션 시작: abc12345
# 주문 생성 (tx: abc12345)
# 주문 저장 (tx: abc12345)
# 결제 처리 (tx: abc12345)

# 두 번째 주문 - 새로운 트랜잭션
tx2 = service.create_order("order-2", 200)
# 출력:
# 트랜잭션 시작: def67890
# 주문 생성 (tx: def67890)
# 주문 저장 (tx: def67890)
# 결제 처리 (tx: def67890)

assert tx1 != tx2  # 각 호출마다 새 트랜잭션
```

### CALL_SCOPED vs DEFAULT 비교

```python
@Component
class Consumer:
    scoped: CallScopedResource    # CALL_SCOPED
    default: DefaultResource      # DEFAULT

    @Handler
    def process(self):
        # CALL_SCOPED: 같은 핸들러 내 모두 같은 인스턴스
        id1 = self.scoped.id  # 새 인스턴스 생성
        id2 = self.scoped.id  # 캐시된 인스턴스 반환
        id3 = self.scoped.id  # 캐시된 인스턴스 반환
        assert id1 == id2 == id3  # ✓ 같은 ID

        # DEFAULT: 매번 새 인스턴스
        d1 = self.default.id  # 새 인스턴스
        d2 = self.default.id  # 새 인스턴스
        d3 = self.default.id  # 새 인스턴스
        assert d1 != d2 != d3  # ✓ 모두 다른 ID
```

## PROTOTYPE 접근 방식

⚠️ **중요**: PROTOTYPE 필드는 **속성 접근**을 통해서만 resolve됩니다.

```python
@Component
class Consumer:
    resource: PrototypeResource

    def process(self):
        # ❌ 잘못된 방법 - LazyFieldProxy 객체만 가져옴
        r = self.resource  # resolve 안 됨!

        # ✅ 올바른 방법 - 속성 접근으로 resolve 트리거
        value = self.resource.some_property  # 새 인스턴스 생성
        self.resource.some_method()           # 또 다른 새 인스턴스 생성

        # ✅ 한 번에 여러 작업 시
        result = self.resource.do_work()      # 하나의 인스턴스에서 처리
```

매번 접근할 때마다 새 인스턴스가 생성되므로, 같은 인스턴스를 재사용하려면:

```python
def process(self):
    # 한 번 resolve 후 로컬 변수로 재사용
    conn = self.resource
    conn.open()        # 같은 인스턴스
    conn.execute(...)  # 같은 인스턴스
    conn.close()       # 같은 인스턴스
```

## 콜스택 기반 자동 정리

### 동작 원리

1. **메서드 진입**: `CallStackTraceAdvice`가 `push_frame()` 호출
2. **PROTOTYPE 생성**: `LazyFieldProxy`가 `register_prototype(instance, container)` 호출
3. **메서드 종료**: `pop_frame()`에서 `cleanup_prototypes_at_depth(depth)` 자동 호출
4. **@PreDestroy 실행**: 해당 depth에서 생성된 모든 PROTOTYPE의 `@PreDestroy` 호출

```
┌─────────────────────────────────────────────────────────────┐
│ outer_method() [depth=0]                                     │
│  ├─ push_frame(depth=0)                                      │
│  ├─ self.resource.xxx → PROTOTYPE 생성 → register(depth=0)  │
│  │                                                           │
│  │  ┌──────────────────────────────────────────────────────┐ │
│  │  │ inner_method() [depth=1]                              │ │
│  │  │  ├─ push_frame(depth=1)                               │ │
│  │  │  ├─ self.resource.xxx → register(depth=1)            │ │
│  │  │  └─ pop_frame(depth=1) → cleanup depth=1 PROTOTYPES  │ │
│  │  └──────────────────────────────────────────────────────┘ │
│  │                                                           │
│  └─ pop_frame(depth=0) → cleanup depth=0 PROTOTYPES         │
└─────────────────────────────────────────────────────────────┘
```

### 중첩 호출 시 역순 정리

```python
@Component
class OuterService:
    inner: InnerService
    resource: PrototypeResource  # depth=0에서 생성

    def outer_process(self):
        self.resource.init()           # ① PROTOTYPE A 생성 (depth=0)
        self.inner.inner_process()     # ② inner 호출
        return "done"
        # ⑤ pop_frame(0) → PROTOTYPE A의 @PreDestroy

@Component
class InnerService:
    resource: PrototypeResource  # depth=1에서 생성

    def inner_process(self):
        self.resource.init()           # ③ PROTOTYPE B 생성 (depth=1)
        return "inner done"
        # ④ pop_frame(1) → PROTOTYPE B의 @PreDestroy

# 실행 순서:
# ① A 생성
# ② inner 진입
# ③ B 생성
# ④ B @PreDestroy (inner 종료)
# ⑤ A @PreDestroy (outer 종료)
```

## Async 환경에서의 격리

`ContextVar` 기반으로 각 코루틴별 독립적인 콜스택과 PROTOTYPE 저장소를 가집니다.

```python
@Component
class AsyncService:
    resource: PrototypeResource


    async def process(self, request_id: str):
        # 각 코루틴별 독립적인 PROTOTYPE 생성
        self.resource.request_id = request_id
        await asyncio.sleep(0.1)  # 다른 코루틴에 양보
        return self.resource.request_id
        # 이 코루틴의 PROTOTYPE만 정리됨

# 동시 실행
results = await asyncio.gather(
    service.process("A"),
    service.process("B"),
    service.process("C"),
)
# 각 요청의 PROTOTYPE이 독립적으로 생성/정리됨
```

### 격리 보장 구조

```python
# bloom/core/advice/tracing/context.py
_prototype_instances: ContextVar[dict[int, list[tuple[Any, Container]]]] = ContextVar(
    "bloom_prototype_instances", default={}
)

# 각 코루틴별 독립적인 dict 사용
# Key: depth, Value: [(instance, container), ...]
```

## 예외 발생 시 정리

예외가 발생해도 `on_error`에서 `pop_frame`이 호출되어 PROTOTYPE이 정리됩니다.

```python
@Component
class FailingService:
    resource: PrototypeResource


    async def might_fail(self):
        self.resource.init()  # PROTOTYPE 생성

        raise ValueError("오류 발생!")
        # 예외 발생해도 @PreDestroy 호출됨

try:
    await service.might_fail()
except ValueError:
    pass  # PROTOTYPE은 이미 정리됨
```

## Spring과의 비교

| 특성                    | Spring          | Bloom                       |
| ----------------------- | --------------- | --------------------------- |
| PROTOTYPE 인스턴스 추적 | 추적 안 함      | 콜스택 기반 추적            |
| @PostConstruct          | ✅ 호출됨       | ✅ 호출됨                   |
| @PreDestroy             | ❌ 호출 안 됨   | ✅ 메서드 종료 시 자동 호출 |
| 리소스 정리             | 클라이언트 책임 | 프레임워크가 자동 처리      |

## 필수 요구사항

PROTOTYPE 자동 정리가 작동하려면:

1. **TracingAdvice 등록 필수**

   ```python
   @Component
   class TracingAdvice(CallStackTraceAdvice):
       pass
   ```

2. **MethodAdviceRegistry 팩토리 등록 필수**

   ```python
   @Component
   class AdviceConfig:
       @Factory
       def registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
           reg = MethodAdviceRegistry()
           for advice in advices:
               reg.register(advice)
           return reg
   ```

3. **PROTOTYPE 사용 메서드에 데코레이터**

   ```python

   def my_method(self):
       self.prototype_field.do_something()
   ```

## API 레퍼런스

### register_prototype

```python
def register_prototype(instance: Any, container: Container) -> None:
    """
    현재 콜스택 깊이에 PROTOTYPE 인스턴스 등록

    LazyFieldProxy._lfp_resolve()에서 자동 호출됩니다.
    콜스택 외부(depth=0)에서 생성된 PROTOTYPE은 등록되지 않습니다.
    """
```

### cleanup_prototypes_at_depth

```python
def cleanup_prototypes_at_depth(depth: int) -> None:
    """
    특정 콜스택 깊이에서 생성된 PROTOTYPE 인스턴스들의 @PreDestroy 호출

    pop_frame()에서 자동 호출됩니다.
    """
```

### get_prototype_count_at_depth

```python
def get_prototype_count_at_depth(depth: int) -> int:
    """특정 깊이에 등록된 PROTOTYPE 인스턴스 수 (테스트/디버깅용)"""
```

## 관련 문서

- [콜스택 추적 시스템](./tracing-system.md)
- [Method Advice 패턴](./method-advice-pattern.md)
- [이벤트 시스템](./event-system.md)
