# Proxy System

Bloom 프레임워크의 프록시 시스템은 의존성 주입(DI)에서 지연 로딩, 순환 의존성 해결, 비동기 컴포넌트 지원을 위해 사용됩니다.

## 개요

Bloom은 세 가지 프록시 타입을 제공합니다:

| 프록시 | 용도 | 접근 방식 |
|--------|------|-----------|
| `LazyProxy[T]` | 동기 컴포넌트 | 투명 프록시 (직접 접근) |
| `AsyncProxy[T]` | 비동기 컴포넌트 | `await proxy.resolve()` |
| `MethodProxy[T]` | AOP/콜스택 추적 | 내부 사용 |

## LazyProxy

### 개념

`LazyProxy`는 **동기 컴포넌트**에 대한 지연 로딩 프록시입니다. 실제 인스턴스에 대한 접근을 투명하게 위임하여, 프록시를 실제 객체처럼 사용할 수 있습니다.

### 동작 방식

```
┌──────────────────────────────────────────────────────────┐
│                    LazyProxy 동작 흐름                    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  @Component                                              │
│  class UserService:                                      │
│      repo: UserRepository  ←── LazyProxy로 주입됨         │
│                                                          │
│      def get_user(self, id):                             │
│          return self.repo.find(id)                       │
│                 ↓                                        │
│          LazyProxy.__getattr__("find")                   │
│                 ↓                                        │
│          _lp_resolve() → 실제 인스턴스 획득               │
│                 ↓                                        │
│          getattr(instance, "find")(id)                   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 사용 예시

```python
from bloom import Component

@Component
class UserRepository:
    def find(self, id: int) -> User:
        # DB 조회 로직
        ...

@Component
class UserService:
    # LazyProxy[UserRepository]로 자동 주입됨
    repo: UserRepository
    
    def get_user(self, id: int) -> User:
        # repo 접근 시점에 실제 인스턴스 resolve
        return self.repo.find(id)
```

### 순환 의존성 해결

LazyProxy의 가장 중요한 역할은 **순환 의존성 해결**입니다:

```python
@Component
class ServiceA:
    b: "ServiceB"  # LazyProxy로 주입

@Component  
class ServiceB:
    a: ServiceA  # LazyProxy로 주입

# 생성 순서:
# 1. ServiceA 인스턴스 생성 (b는 LazyProxy)
# 2. ServiceB 인스턴스 생성 (a는 LazyProxy)
# 3. ServiceA.b 접근 시 → LazyProxy가 ServiceB resolve
# 4. ServiceB.a 접근 시 → LazyProxy가 ServiceA resolve
```

```
┌─────────────────────────────────────────────────────────────────┐
│                    순환 의존성 해결 과정                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  생성 단계:                                                      │
│  ┌─────────┐     LazyProxy      ┌─────────┐                     │
│  │ServiceA │ ←───────────────── │ServiceB │                     │
│  │  (b: ?) │ ──────────────────→│  (a: ?) │                     │
│  └─────────┘     LazyProxy      └─────────┘                     │
│                                                                 │
│  접근 단계:                                                      │
│  ┌─────────┐                    ┌─────────┐                     │
│  │ServiceA │ ←── resolve ────── │ServiceB │                     │
│  │  .b     │ ─── resolve ─────→ │  .a     │                     │
│  └─────────┘                    └─────────┘                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 스코프별 동작

| 스코프 | 동작 |
|--------|------|
| `SINGLETON` | 한 번 resolve 후 프록시 내부에 캐싱 |
| `REQUEST` | 매 접근마다 ScopeManager에서 현재 컨텍스트의 인스턴스 조회 |
| `CALL` | 매 접근마다 ScopeManager에서 현재 Handler 컨텍스트의 인스턴스 조회 |

### 지원하는 프로토콜

LazyProxy는 다양한 Python 프로토콜을 지원하여 투명하게 동작합니다:

```python
# Attribute access
proxy.attr           # __getattr__
proxy.attr = value   # __setattr__

# Container protocol  
len(proxy)           # __len__
for item in proxy:   # __iter__
item in proxy        # __contains__
proxy[key]           # __getitem__
proxy[key] = value   # __setitem__

# Callable protocol
proxy(args)          # __call__

# Comparison
proxy == other       # __eq__
hash(proxy)          # __hash__

# String representation
str(proxy)           # __str__
repr(proxy)          # __repr__
bool(proxy)          # __bool__
```

## AsyncProxy

### 개념

`AsyncProxy`는 **비동기 컴포넌트**를 위한 프록시입니다. 동기 컨텍스트에서 CALL 스코프의 비동기 컴포넌트(예: `AsyncSession`)를 안전하게 사용할 수 있게 합니다.

### LazyProxy와의 차이

| 특성 | LazyProxy | AsyncProxy |
|------|-----------|------------|
| 접근 방식 | 투명 (`proxy.method()`) | 명시적 (`await proxy.resolve()`) |
| 컨텍스트 | 동기/비동기 모두 | 비동기 전용 |
| 사용 시점 | 일반 컴포넌트 | 비동기 생성이 필요한 컴포넌트 |

### 사용 예시

```python
from bloom import Component
from bloom.core import AsyncProxy
from bloom.db import AsyncSession

@Component
class UserRepository:
    # AsyncProxy로 명시적 선언
    async_session: AsyncProxy[AsyncSession]
    
    async def find_all(self) -> list[User]:
        # await resolve()로 인스턴스 획득
        session = await self.async_session.resolve()
        return await session.execute(select(User))
```

### 동작 방식

```
┌──────────────────────────────────────────────────────────┐
│                   AsyncProxy 동작 흐름                    │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  @Component                                              │
│  class UserRepository:                                   │
│      session: AsyncProxy[AsyncSession]                   │
│                         ↑                                │
│                   AsyncProxy 주입                         │
│                                                          │
│      async def find_all(self):                           │
│          session = await self.session.resolve()          │
│                              ↓                           │
│                    AsyncProxy.resolve()                  │
│                              ↓                           │
│                    ScopeManager 캐시 확인                 │
│                              ↓                           │
│              manager.get_instance_async()                │
│                              ↓                           │
│                    AsyncSession 반환                      │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 왜 AsyncProxy가 필요한가?

**문제 상황**: `@PostConstruct`나 DI 필드 주입은 동기 컨텍스트에서 실행됩니다. 하지만 CALL 스코프 컴포넌트(예: `AsyncSession`)는 Handler 컨텍스트 내에서만 생성되어야 합니다.

```python
# ❌ 문제: LazyProxy는 동기 컨텍스트에서 CALL 스코프 resolve 시 에러
@Component
class UserRepository:
    session: AsyncSession  # LazyProxy로 주입
    
    @PostConstruct  # 동기 컨텍스트
    def init(self):
        # self.session 접근 시 에러!
        # "Cannot access CALL scoped component outside of @Handler context"
        pass
```

```python
# ✅ 해결: AsyncProxy는 resolve()를 호출할 때까지 지연
@Component
class UserRepository:
    session: AsyncProxy[AsyncSession]  # AsyncProxy로 주입
    
    @PostConstruct  # 동기 컨텍스트
    def init(self):
        # session은 AsyncProxy이므로 접근하지 않음
        pass
    
    async def find_all(self):  # Handler 컨텍스트 내에서 호출됨
        session = await self.session.resolve()  # 여기서 resolve
        return await session.execute(...)
```

### 스코프별 동작

| 스코프 | 동작 |
|--------|------|
| `SINGLETON` | 한 번 resolve 후 캐싱 |
| `REQUEST` | 요청마다 새 인스턴스 (ScopeManager에서 조회) |
| `CALL` | Handler 호출마다 새 인스턴스 (ScopeManager에서 조회) |

### 컨텍스트 체크

AsyncProxy는 resolve 시 적절한 컨텍스트인지 확인합니다:

```python
# CALL 스코프: Handler 컨텍스트 필요
if container.scope == ScopeEnum.CALL:
    if not manager.scope_manager.is_in_call_context():
        raise RuntimeError(
            "Cannot access CALL scoped component outside of @Handler context"
        )

# REQUEST 스코프: Request 컨텍스트 필요
if container.scope == ScopeEnum.REQUEST:
    if not manager.scope_manager.is_in_request_context():
        raise RuntimeError(
            "Cannot access REQUEST scoped component outside of request context"
        )
```

## 명시적 타입 선언

DI 시스템은 **명시적 타입 선언**을 기반으로 프록시 타입을 결정합니다:

```python
@Component
class MyService:
    # 일반 타입 선언 → LazyProxy 주입
    repo: UserRepository
    
    # AsyncProxy 명시적 선언 → AsyncProxy 주입
    session: AsyncProxy[AsyncSession]
```

내부적으로 `typing.get_origin()`과 `get_args()`를 사용하여 `AsyncProxy[T]` 타입을 감지합니다.

## MethodProxy (내부 사용)

`MethodProxy`는 컴포넌트의 메서드를 감싸서 다음 기능을 제공합니다:

- **콜스택 추적**: CALL 스코프용 frame ID 관리
- **AOP 지원**: `@Before`, `@After`, `@Around` 어드바이스

일반적으로 직접 사용하지 않으며, 프레임워크 내부에서 자동으로 적용됩니다.

## 요약

```
┌─────────────────────────────────────────────────────────────────┐
│                       Proxy 선택 가이드                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Q: 비동기 컴포넌트인가? (AsyncSession, async 생성 등)            │
│     │                                                           │
│     ├─ Yes → AsyncProxy[T] 사용                                 │
│     │        - await proxy.resolve()로 접근                     │
│     │        - CALL/REQUEST 스코프에 적합                        │
│     │                                                           │
│     └─ No → LazyProxy[T] (자동 적용)                            │
│             - proxy.method()로 직접 접근                         │
│             - 순환 의존성 자동 해결                               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| 상황 | 권장 프록시 | 사용법 |
|------|------------|--------|
| 일반 컴포넌트 의존성 | LazyProxy (자동) | `repo: UserRepository` |
| 순환 의존성 | LazyProxy (자동) | `other: "OtherService"` |
| AsyncSession 등 비동기 리소스 | AsyncProxy | `session: AsyncProxy[AsyncSession]` |
| CALL 스코프 비동기 컴포넌트 | AsyncProxy | `await proxy.resolve()` |
