# Dependency Injection Scopes

Bloom 프레임워크는 Spring Framework에서 영감을 받은 의존성 주입(DI) 시스템을 제공합니다. 컴포넌트의 생명주기를 관리하기 위해 세 가지 스코프를 지원합니다.

## 스코프 종류

| 스코프 | 설명 | 생명주기 |
|--------|------|----------|
| `SINGLETON` | 애플리케이션 전체에서 단일 인스턴스 | 앱 시작 ~ 종료 |
| `REQUEST` | HTTP 요청마다 새 인스턴스 | 요청 시작 ~ 응답 완료 |
| `CALL` | `@Handler` 메서드 호출마다 새 인스턴스 | 메서드 진입 ~ 반환 |

---

## SINGLETON Scope

### 개요

`SINGLETON`은 기본 스코프로, 애플리케이션 전체에서 **단 하나의 인스턴스**만 생성됩니다. 대부분의 서비스, 리포지토리, 설정 클래스에 적합합니다.

### 사용법

```python
from bloom.core import Component, Scope

# 기본값이 SINGLETON이므로 별도 지정 불필요
@Component
class UserService:
    pass

# 명시적으로 지정할 수도 있음
@Component(scope=Scope.SINGLETON)
class ConfigService:
    pass
```

### 생명주기

```
┌─────────────────────────────────────────────────────────┐
│                    Application Lifecycle                │
├─────────────────────────────────────────────────────────┤
│  initialize()        인스턴스 사용              shutdown() │
│       │                   │                        │     │
│       ▼                   ▼                        ▼     │
│  @PostConstruct    get_instance()           @PreDestroy  │
│       │                   │                        │     │
│       └───────────────────┴────────────────────────┘     │
│                    단일 인스턴스 유지                      │
└─────────────────────────────────────────────────────────┘
```

### 라이프사이클 콜백

```python
from bloom.core import Component, PostConstruct, PreDestroy

@Component
class DatabaseConnection:
    @PostConstruct
    async def connect(self):
        """앱 시작 시 한 번 호출"""
        self.conn = await create_connection()
        print("Database connected")
    
    @PreDestroy
    async def disconnect(self):
        """앱 종료 시 한 번 호출"""
        await self.conn.close()
        print("Database disconnected")
```

### AutoClosable 인터페이스

`@PreDestroy` 대신 `AutoClosable` 인터페이스를 구현할 수도 있습니다:

```python
from bloom.core import Component, AutoClosable

@Component
class FileHandler(AutoClosable):
    async def close(self):
        """앱 종료 시 자동 호출"""
        await self.file.close()
```

### 특징

- ✅ 상태를 공유해야 하는 서비스에 적합
- ✅ 초기화 비용이 큰 리소스에 적합 (DB 연결, 캐시 등)
- ✅ 의존성 주입 시 항상 같은 인스턴스 반환
- ⚠️ 멀티스레드 환경에서 스레드 안전성 고려 필요

---

## CALL Scope

### 개요

`CALL` 스코프는 `@Handler` 데코레이터가 붙은 메서드 호출마다 **새로운 인스턴스**를 생성합니다. 메서드 실행이 완료되면 인스턴스가 자동으로 정리됩니다.

트랜잭션 컨텍스트, 작업 단위(Unit of Work), 임시 상태 관리에 적합합니다.

### 사용법

```python
from bloom.core import Component, Scope, Handler, PreDestroy
from bloom.core.decorators import scope_decorator

# 방법 1: @Component와 @scope_decorator 조합
# 주의: @Component가 먼저, @scope_decorator가 나중에 와야 함
@Component
@scope_decorator(Scope.CALL)
class TransactionContext:
    def __init__(self):
        self.operations = []
    
    def add_operation(self, op):
        self.operations.append(op)
    
    @PreDestroy
    async def commit_or_rollback(self):
        """Handler 종료 시 자동 호출"""
        try:
            await self.commit()
        except Exception:
            await self.rollback()
```

### @Handler와 함께 사용

```python
@Component
class UserService:
    tx: TransactionContext  # CALL 스코프 의존성
    
    @Handler
    async def create_user(self, name: str):
        """
        @Handler 진입 시:
        1. CALL 스코프 컨텍스트 시작
        2. TransactionContext 인스턴스 생성
        3. @PostConstruct 호출
        
        @Handler 종료 시:
        4. @PreDestroy 호출 (commit_or_rollback)
        5. 인스턴스 정리
        """
        self.tx.add_operation(CreateUser(name))
        return User(name=name)
```

### 생명주기

```
┌─────────────────────────────────────────────────────────┐
│                   @Handler Method Call                  │
├─────────────────────────────────────────────────────────┤
│  start_call()       메서드 실행           end_call()     │
│       │                 │                     │         │
│       ▼                 ▼                     ▼         │
│  인스턴스 생성     CALL 스코프 접근      @PreDestroy      │
│  @PostConstruct        │              인스턴스 정리      │
│       │                 │                     │         │
│       └─────────────────┴─────────────────────┘         │
│              이 범위 내에서만 인스턴스 유효               │
└─────────────────────────────────────────────────────────┘
```

### 중첩 Handler

중첩된 `@Handler` 호출은 각각 **독립된 CALL 스코프**를 가집니다:

```python
@Component
@scope_decorator(Scope.CALL)
class RequestContext:
    def __init__(self):
        self.id = uuid.uuid4()

@Component
class OuterService:
    ctx: RequestContext
    
    @Handler
    async def outer_method(self):
        outer_ctx_id = self.ctx.id  # 인스턴스 A
        
        inner = get_container_manager().get_instance(InnerService)
        await inner.inner_method()
        
        # outer의 ctx는 여전히 인스턴스 A
        assert self.ctx.id == outer_ctx_id

@Component
class InnerService:
    ctx: RequestContext
    
    @Handler
    async def inner_method(self):
        # 별도의 인스턴스 B (outer와 다름)
        inner_ctx_id = self.ctx.id
```

```
┌─────────────────────────────────────────────────────────┐
│ outer_method() - Frame 1                                │
│   RequestContext A 생성                                  │
│   ┌─────────────────────────────────────────────────┐   │
│   │ inner_method() - Frame 2                        │   │
│   │   RequestContext B 생성 (A와 독립)               │   │
│   │   ...                                           │   │
│   │   RequestContext B 정리 (@PreDestroy)           │   │
│   └─────────────────────────────────────────────────┘   │
│   RequestContext A 정리 (@PreDestroy)                   │
└─────────────────────────────────────────────────────────┘
```

### inherit_parent 옵션

중첩 Handler에서 **부모의 인스턴스를 공유**하고 싶다면 `inherit_parent` 옵션을 사용합니다:

```python
scope_manager = manager.scope_manager

async with scope_manager.call_scope() as parent_frame:
    # 부모 컨텍스트에서 인스턴스 생성
    parent_ctx = await manager.get_instance_async(RequestContext)
    
    # 자식 컨텍스트가 부모 인스턴스를 상속
    async with scope_manager.call_scope(inherit_parent=True, destroy_instances=False):
        child_ctx = await manager.get_instance_async(RequestContext)
        assert parent_ctx is child_ctx  # 같은 인스턴스!
    
    # destroy_instances=False이므로 아직 정리되지 않음

# 부모 컨텍스트 종료 시 정리
```

### 정리 순서

CALL 스코프 인스턴스는 **의존성 역순**으로 정리됩니다:

```python
@Component
@scope_decorator(Scope.CALL)
class FirstService:
    @PreDestroy
    async def cleanup(self):
        print("first cleanup")

@Component
@scope_decorator(Scope.CALL)
class SecondService:
    first: FirstService  # FirstService에 의존
    
    @PreDestroy
    async def cleanup(self):
        print("second cleanup")

@Component
@scope_decorator(Scope.CALL)
class ThirdService:
    second: SecondService  # SecondService에 의존
    
    @PreDestroy
    async def cleanup(self):
        print("third cleanup")

# 생성 순서: First → Second → Third
# 정리 순서: Third → Second → First (역순)
```

### asynccontextmanager 지원

테스트나 수동 스코프 관리를 위한 컨텍스트 매니저를 제공합니다:

```python
scope_manager = manager.scope_manager

# 기본 사용
async with scope_manager.call_scope() as frame_id:
    instance = await manager.get_instance_async(CallScopedService)
    # frame_id로 현재 프레임 식별 가능
# 종료 시 자동으로 @PreDestroy 호출

# 옵션 사용
async with scope_manager.call_scope(
    inherit_parent=True,      # 부모 인스턴스 상속
    destroy_instances=False   # @PreDestroy 호출 생략
):
    pass
```

### 유틸리티 메서드

```python
scope_manager = manager.scope_manager

# 현재 CALL 컨텍스트 내부인지 확인
if scope_manager.is_in_call_context():
    ...

# 현재 활성 frame_id
frame_id = scope_manager.get_current_frame_id()

# 중첩 깊이 확인
depth = scope_manager.get_frame_stack_depth()
```

### 특징

- ✅ 메서드 단위의 격리된 상태 관리
- ✅ 트랜잭션, Unit of Work 패턴에 적합
- ✅ 자동 리소스 정리 (`@PreDestroy`)
- ✅ 중첩 호출 지원 (독립된 스코프)
- ✅ 선택적 부모 인스턴스 상속

---

## REQUEST Scope

### 개요

`REQUEST` 스코프는 HTTP 요청마다 새 인스턴스를 생성합니다. 요청 컨텍스트, 사용자 세션 데이터 등에 적합합니다.

### 사용법

```python
@Component(scope=Scope.REQUEST)
class RequestContext:
    def __init__(self):
        self.user_id = None
        self.request_id = uuid.uuid4()
```

### asynccontextmanager

```python
async with scope_manager.request_scope():
    instance = await manager.get_instance_async(RequestScopedService)
# 종료 시 자동으로 @PreDestroy 호출
```

---

## 스코프 비교

| 특성 | SINGLETON | REQUEST | CALL |
|------|-----------|---------|------|
| 인스턴스 생성 시점 | 앱 초기화 시 | 요청 시작 시 | @Handler 진입 시 |
| 인스턴스 정리 시점 | 앱 종료 시 | 요청 종료 시 | @Handler 반환 시 |
| 중첩 지원 | N/A | N/A | ✅ (스택 기반) |
| 부모 상속 옵션 | N/A | N/A | ✅ inherit_parent |
| 주요 사용처 | 서비스, 설정 | 요청 컨텍스트 | 트랜잭션, UoW |

---

## 실전 예제: 트랜잭션 관리

```python
from bloom.core import Component, Scope, Handler, PreDestroy, PostConstruct
from bloom.core.decorators import scope_decorator

@Component
@scope_decorator(Scope.CALL)
class UnitOfWork:
    """Handler 단위의 작업 단위"""
    
    def __init__(self):
        self.new_objects: list = []
        self.dirty_objects: list = []
        self.deleted_objects: list = []
    
    @PostConstruct
    async def begin(self):
        print("UnitOfWork started")
    
    def register_new(self, obj):
        self.new_objects.append(obj)
    
    def register_dirty(self, obj):
        self.dirty_objects.append(obj)
    
    def register_deleted(self, obj):
        self.deleted_objects.append(obj)
    
    @PreDestroy
    async def commit(self):
        """Handler 종료 시 자동 커밋"""
        # INSERT
        for obj in self.new_objects:
            await self.db.insert(obj)
        
        # UPDATE
        for obj in self.dirty_objects:
            await self.db.update(obj)
        
        # DELETE
        for obj in self.deleted_objects:
            await self.db.delete(obj)
        
        print("UnitOfWork committed")


@Component
class OrderService:
    uow: UnitOfWork
    
    @Handler
    async def create_order(self, items: list):
        order = Order(items=items)
        self.uow.register_new(order)
        
        for item in items:
            inventory = await self.get_inventory(item.product_id)
            inventory.quantity -= item.quantity
            self.uow.register_dirty(inventory)
        
        return order
        # Handler 종료 시 자동으로 uow.commit() 호출
```

---

## 주의사항

### 데코레이터 순서

`@Component`와 `@scope_decorator`를 함께 사용할 때 **순서가 중요**합니다:

```python
# ✅ 올바른 순서: @Component가 먼저 (위에)
@Component
@scope_decorator(Scope.CALL)
class CorrectService:
    pass

# ❌ 잘못된 순서: @scope_decorator가 먼저 (위에)
@scope_decorator(Scope.CALL)
@Component
class WrongService:
    pass
```

Python 데코레이터는 **아래에서 위로** 실행되므로, `@scope_decorator`가 먼저 실행되어 `__bloom_scope__`를 설정하고, `@Component`가 이를 읽어서 올바른 스코프로 등록합니다.

### CALL 스코프 외부 접근

`@Handler` 외부에서 CALL 스코프 컴포넌트에 접근하면 에러가 발생합니다:

```python
@Component
@scope_decorator(Scope.CALL)
class CallScopedService:
    pass

# ❌ @Handler 외부에서 접근 시 에러
service = manager.get_instance(CallScopedService)
# CallScopeError: CallScopedService requires @Handler context
```

### LazyProxy와 CALL 스코프

CALL 스코프 컴포넌트는 `LazyProxy`를 통해 주입되며, 접근 시점에 현재 CALL 컨텍스트에서 인스턴스를 조회합니다:

```python
@Component
class MyService:
    call_scoped: CallScopedService  # LazyProxy로 주입됨
    
    @Handler
    async def method1(self):
        # 접근 시점에 현재 CALL 컨텍스트의 인스턴스 반환
        self.call_scoped.do_something()
    
    @Handler
    async def method2(self):
        # method1과 다른 CALL 컨텍스트이므로 다른 인스턴스
        self.call_scoped.do_something()
```
