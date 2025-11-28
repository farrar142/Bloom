# Bloom Framework - 의존성 주입 (Dependency Injection)

Bloom은 Spring Framework에서 영감을 받은 Python 의존성 주입(DI) 컨테이너입니다. 타입 어노테이션을 기반으로 자동 의존성 주입을 제공하며, 복잡한 의존성 관계를 시각화하고 분석하는 도구를 포함합니다.

## 목차

1. [기본 개념](#1-기본-개념)
2. [컨테이너 타입](#2-컨테이너-타입)
3. [의존성 주입 패턴](#3-의존성-주입-패턴)
4. [Factory Chain](#4-factory-chain)
5. [Lazy 의존성](#5-lazy-의존성)
6. [순환 의존성 감지](#6-순환-의존성-감지)
7. [라이프사이클 관리](#7-라이프사이클-관리)
8. [의존성 그래프 분석](#8-의존성-그래프-분석)
9. [초기화 순서](#9-초기화-순서)

---

## 1. 기본 개념

### 1.1 컴포넌트 등록

`@Component` 데코레이터로 클래스를 DI 컨테이너에 등록합니다:

```python
from bloom import Component

@Component
class Logger:
    def log(self, message: str) -> None:
        print(f"[LOG] {message}")

@Component
class UserService:
    logger: Logger  # 타입 어노테이션만으로 자동 주입
    
    def create_user(self, name: str) -> None:
        self.logger.log(f"Creating user: {name}")
```

### 1.2 애플리케이션 초기화

```python
from bloom import Application

app = Application("my-app").scan(my_module).ready()

# 인스턴스 가져오기
user_service = app.manager.get_instance(UserService)
user_service.create_user("Alice")
```

---

## 2. 컨테이너 타입

Bloom은 세 가지 컨테이너 타입을 지원합니다:

### 2.1 Component

일반적인 싱글톤 컴포넌트:

```python
@Component
class DatabaseConnection:
    pass
```

**의존성 그래프 표시:**
```
DatabaseConnection (Component)
```

### 2.2 Factory

메서드 기반 인스턴스 생성 (복잡한 초기화 시 사용):

```python
@Component
class AuthConfig:
    @Factory
    def authenticator(self) -> Authenticator:
        return Authenticator(secret_key="...")
```

**의존성 그래프 표시:**
```
Authenticator (Factory)
```

### 2.3 Handler

키 기반 핸들러 등록 (예외 처리, 라우팅 등):

```python
@Component
class EventHandlers:
    @Handler("user.created")
    def on_user_created(self, event) -> None:
        pass
```

**의존성 그래프 표시:**
```
HandlerContainer (Handler)
HttpMethodHandler (Handler)
ErrorHandlerContainer (Handler)
```

---

## 3. 의존성 주입 패턴

### 3.1 단일 레벨 의존성

```python
@Component
class Repository:
    db: DatabaseConnection
```

**의존성 트리:**
```
Repository
    └── DatabaseConnection
```

### 3.2 다중 레벨 의존성

3단계 이상의 의존성 체인:

```python
@Component
class OrderController:
    service: OrderService

@Component  
class OrderService:
    repository: OrderRepository

@Component
class OrderRepository:
    db: DatabaseConnection
```

**의존성 그래프 표시:**
```
## Multi-Level Dependencies
----------------------------------------

Chains with 3+ levels of dependency depth:

  [4 levels] OrderController → OrderService → OrderRepository → DatabaseConnection

  OrderController
      └── OrderService
          └── OrderRepository
              └── DatabaseConnection
```

### 3.3 다이아몬드 의존성

여러 경로가 하나의 공통 의존성으로 수렴하는 패턴:

```python
@Component
class OrderService:
    order_repo: OrderRepository
    product_repo: ProductRepository

@Component
class OrderRepository:
    db: DatabaseConnection
    cache: CacheService

@Component
class ProductRepository:
    db: DatabaseConnection  # 공통 의존성
    cache: CacheService     # 공통 의존성
```

**의존성 그래프 표시:**
```
## Diamond Dependencies
----------------------------------------

Patterns where multiple paths lead to a common dependency:

  Diamond: OrderService → (OrderRepository, ProductRepository) → DatabaseConnection

                 ┌──────────────┐
                 │ OrderService │
                 └──────┬───────┘
              ┌─────────┴─────────┐
              ▼                   ▼
     ┌────────────────┐  ┌────────────────┐
     │  OrderRepo     │  │  ProductRepo   │
     └───────┬────────┘  └───────┬────────┘
             └───────────┬───────┘
                         ▼
                ┌────────────────┐
                │ DatabaseConn   │
                └────────────────┘
```

> **참고:** Bloom은 싱글톤 패턴을 사용하므로 다이아몬드 의존성에서도 같은 인스턴스가 공유됩니다.

---

## 4. Factory Chain

동일 타입을 반환하는 여러 `@Factory`가 체인으로 연결되어 순차 실행됩니다.

### 4.1 기본 구조

```python
@Component
class ConfigFactory:
    logger: Logger
    
    @Factory
    def create_config(self) -> AppConfig:
        """Creator: 최초 인스턴스 생성 (자기 타입 미의존)"""
        return AppConfig()
    
    @Factory
    @Order(1)
    def enable_debug(self, config: AppConfig) -> AppConfig:
        """Modifier: 기존 인스턴스 수정 (자기 타입 의존)"""
        config.debug = True
        return config
    
    @Factory
    @Order(2)
    def add_features(self, config: AppConfig) -> AppConfig:
        """Modifier: 추가 수정"""
        config.features = ["auth", "cache"]
        return config
```

### 4.2 순서 결정 규칙

| 규칙 | 설명 |
|------|------|
| Creator 먼저 | 자기 타입을 의존하지 않는 Factory가 먼저 실행 |
| `@Order` | 값이 낮을수록 먼저 실행 |
| 의존성 기반 | `@Order` 없으면 외부 의존성으로 순서 결정 |

### 4.3 @Order 사용 예제

```python
  AppConfig (Factory Chain - 4 factories)
    └─ create_config()           # Creator (Order 없음)
    └─ enable_debug() @Order(1)  # 첫 번째 Modifier
    └─ add_features() @Order(2)  # 두 번째 Modifier
    └─ add_metadata() @Order(3)  # 세 번째 Modifier
```

### 4.4 의존성 기반 순서 (@Order 없음)

```python
@Component
class SettingsFactory:
    @Factory
    def create_settings(self) -> Settings:
        return Settings()
    
    @Factory
    def add_database_url(self, settings: Settings, data_source: DataSource) -> Settings:
        # DataSource에 의존
        settings.set("db.url", data_source.url)
        return settings
    
    @Factory
    def add_cache_config(self, settings: Settings, cache_config: CacheConfig) -> Settings:
        # CacheConfig에 의존
        settings.set("cache.enabled", str(cache_config.enabled))
        return settings
    
    @Factory
    def finalize_settings(self, settings: Settings, data_source: DataSource, cache_config: CacheConfig) -> Settings:
        # 둘 다 의존 → 마지막에 실행
        settings.finalized = True
        return settings
```

**의존성 그래프 표시:**
```
  Settings (Factory Chain - 4 factories)
    └─ create_settings()      # Creator
    └─ add_cache_config()     # CacheConfig 의존
    └─ add_database_url()     # DataSource 의존
    └─ finalize_settings()    # 둘 다 의존 → 마지막
```

### 4.5 Factory Chain 상세 시각화

```
## Factory Chains (Detailed)
----------------------------------------

### AppConfig Chain

  ┌─────────────────┐
  │ create_config() │ [Creator]
  └────────┬────────┘
           │
           │ ◀── ConfigFactory
           ▼
  ┌─────────────────┐
  │ enable_debug()  │ @Order(1)
  └────────┬────────┘
           │
           │ ◀── ConfigFactory
           ▼
  ┌─────────────────┐
  │ add_features()  │ @Order(2)
  └────────┬────────┘
           │
           │ ◀── ConfigFactory
           ▼
  ┌─────────────────┐
  │ add_metadata()  │ @Order(3)
  └────────┬────────┘
           │
           ▼
      [AppConfig]
```

### 4.6 Ambiguous Provider 에러

Creator가 2개 이상이고 Modifier가 있으면 에러 발생:

```python
# ❌ 에러 발생
@Component
class BadConfig:
    @Factory
    def create_a(self) -> MyType:  # Creator 1
        return MyType()
    
    @Factory
    def create_b(self) -> MyType:  # Creator 2 (ambiguous!)
        return MyType()
    
    @Factory
    def modify(self, my: MyType) -> MyType:  # Modifier
        return my
```

**해결:** Creator는 1개만, 나머지는 Modifier로 구성

---

## 5. Lazy 의존성

순환 의존성 해결을 위한 지연 로딩:

### 5.1 사용법

```python
from bloom import Component, Lazy

@Component
class EmailService:
    logger: Logger
    
    def send_email(self, to: str, message: str) -> None:
        self.logger.log(f"Sending email to {to}")

@Component
class NotificationService:
    logger: Logger
    email_service: Lazy[EmailService]  # 지연 로딩
    
    def notify(self, message: str) -> None:
        self.logger.log(f"Notification: {message}")
        # 접근 시점에 실제 인스턴스 반환
        self.email_service.send_email("admin@example.com", message)
```

### 5.2 의존성 그래프 표시

```
## Dependency Graph
----------------------------------------

Legend: ─── = direct dependency, ┄┄┄ = lazy dependency (deferred)

NotificationService
    ├── Logger
    └┄┄ EmailService (lazy)
        └── Logger
```

### 5.3 Lazy 의존성 섹션

```
## Lazy Dependencies (Deferred Loading)
----------------------------------------

Components using @Lazy for deferred initialization:
(Breaks circular dependencies by deferring resolution)

  NotificationService
    └┄┄ EmailService (lazy)

  UserCreatedHandler
    └┄┄ EmailService (lazy)
```

---

## 6. 순환 의존성 감지

### 6.1 순환 의존성이란?

```python
@Component
class ServiceA:
    service_b: ServiceB  # A → B

@Component
class ServiceB:
    service_c: ServiceC  # B → C

@Component
class ServiceC:
    service_a: ServiceA  # C → A (순환!)
```

### 6.2 자동 감지 및 그래프 저장

순환 의존성 발견 시:
1. `CircularDependencyError` 예외 발생
2. 의존성 그래프가 `circular-dependency-{timestamp}.txt`로 저장

```
============================================================
⚠️  CIRCULAR DEPENDENCY DETECTED
============================================================

Dependency graph saved to: circular-dependency-20251129_064955.txt

Circular dependency detected among:
  - ServiceA → ['ServiceB']
  - ServiceB → ['ServiceC']
  - ServiceC → ['ServiceA']
============================================================
```

### 6.3 그래프 내 순환 표시

```
## Summary
----------------------------------------
Total Containers: 5
Unique Types: 5
Factory Chains: 0
⚠️  Circular Dependencies: 5 types involved

============================================================
⚠️  CIRCULAR DEPENDENCY DETECTED
============================================================

The following components form a circular dependency chain:

  🔄 ServiceA
      └── Cycle deps: ServiceB

  🔄 ServiceB
      └── Cycle deps: ServiceC

  🔄 ServiceC
      └── Cycle deps: ServiceA

  Cycle path:
    ServiceA → ServiceB → ServiceC → (cycle back)

------------------------------------------------------------
💡 How to resolve:

  1. Use @Lazy to break the cycle:
     ```python
     @Component
     class ServiceA:
         service_b: Lazy[ServiceB]  # Deferred loading
     ```

  2. Extract common functionality to a third component

  3. Reconsider the design - circular dependencies
     often indicate a design issue

============================================================
```

### 6.4 해결 방법

**방법 1: Lazy 사용**
```python
@Component
class ServiceC:
    service_a: Lazy[ServiceA]  # 지연 로딩으로 순환 해결
```

**방법 2: 인터페이스/공통 컴포넌트 추출**
```python
@Component
class SharedService:
    # A, B, C가 공통으로 사용하는 기능
    pass

@Component
class ServiceA:
    shared: SharedService
```

---

## 7. 라이프사이클 관리

### 7.1 @PostConstruct

DI 완료 후 호출:

```python
from bloom import Component, PostConstruct

@Component
class ConnectionPool:
    logger: Logger
    
    def __init__(self):
        self.connections = []
    
    @PostConstruct
    def initialize(self):
        """의존성 주입 완료 후 호출"""
        self.logger.log("Initializing connection pool")
        for i in range(10):
            self.connections.append(f"conn_{i}")
```

### 7.2 @PreDestroy

애플리케이션 종료 시 역순 호출:

```python
from bloom import Component, PreDestroy

@Component
class ConnectionPool:
    @PreDestroy
    def cleanup(self):
        """종료 시 호출 (초기화 역순)"""
        self.connections.clear()
```

### 7.3 종료 순서

```python
async with app:
    # 앱 실행
    pass
# 종료 시: 초기화 역순으로 @PreDestroy 호출
# Step 6 → Step 5 → ... → Step 1
```

---

## 8. 의존성 그래프 분석

### 8.1 그래프 생성

```python
from bloom.logging.graph import generate_dependency_graph

graph = generate_dependency_graph(app.manager, "dependency-graph.txt")
print(graph)
```

### 8.2 그래프 섹션

| 섹션 | 설명 |
|------|------|
| **Summary** | 전체 통계 (컨테이너 수, Factory Chain 수 등) |
| **Containers by Type** | 타입별 컨테이너 목록 |
| **Dependency Graph** | 의존성 트리 시각화 |
| **Factory Chains** | Factory Chain 상세 흐름 |
| **Lazy Dependencies** | Lazy 의존성 목록 |
| **Multi-Level Dependencies** | 3단계 이상 의존성 체인 |
| **Diamond Dependencies** | 다이아몬드 패턴 시각화 |
| **Initialization Order** | 초기화 순서 (단계별) |
| **Dependency Matrix** | 전체 의존성 매트릭스 |

### 8.3 의존성 매트릭스

모든 컴포넌트 간의 의존 관계를 행렬로 표시:

```
## Dependency Matrix
----------------------------------------

           L O P U
          --------
Logger   │ · · · ·
OrderSvc │ ● · ● ·
ProdRepo │ · · · ·
UserSvc  │ ● · · ●

Legend: ● = depends on, · = no dependency
```

---

## 9. 초기화 순서

### 9.1 토폴로지 정렬

Bloom은 의존성 그래프를 토폴로지 정렬하여 초기화 순서를 결정합니다:

1. **Level 0**: 의존성이 없는 컴포넌트 (병렬 초기화 가능)
2. **Level 1**: Level 0에만 의존하는 컴포넌트
3. **Level N**: Level N-1 이하에 의존하는 컴포넌트

### 9.2 초기화 순서 시각화

```
## Initialization Order (Dependency Resolution)
----------------------------------------

Step-by-step initialization sequence:
(Components in same group can be initialized in parallel)

  ┌──────────────────────────────────────────────────────────┐
  │ Step 1: Initialize base components (no deps)             │
  └──────────────────────────────────────────────────────────┘
      ┌────────────────────────────────────────────────┐
      │ Parallel Group (12 components)                 │
      ├────────────────────────────────────────────────┤
      │ • Logger                                       │
      │ • CacheService                                 │
      │ • DatabaseConnection                           │
      │ • AuthConfiguration                            │
      │ • ...                                          │
      └────────────────────────────────────────────────┘
          │
          ▼

  ┌──────────────────────────────────────────────────────────┐
  │ Step 2: Initialize after Step 1 completes                │
  └──────────────────────────────────────────────────────────┘
      ┌────────────────────────────────────────────────┐
      │ Parallel Group (15 components)                 │
      ├────────────────────────────────────────────────┤
      │ • AuthService        ← [Logger]                │
      │ • OrderRepository    ← [CacheService, DbConn]  │
      │ • UserRepository     ← [DbConn, Logger]        │
      │ • ...                                          │
      └────────────────────────────────────────────────┘
          │
          ▼

  ┌──────────────────────────────────────────────────────────┐
  │ Step 3: Initialize after Step 2 completes                │
  └──────────────────────────────────────────────────────────┘
      ┌────────────────────────────────────────────────┐
      │ Parallel Group (6 components)                  │
      ├────────────────────────────────────────────────┤
      │ • OrderService       ← [Logger, OrderRepo +1]  │
      │ • UserService        ← [Logger, UserRepo]      │
      │ • ...                                          │
      └────────────────────────────────────────────────┘

  ...

  ✓ Initialization complete: 42 components in 6 steps
```

### 9.3 병렬 초기화

같은 단계의 컴포넌트들은 병렬로 초기화할 수 있습니다:

```python
# 순차 초기화 (기본)
app = Application("my-app").scan(module).ready()

# 병렬 초기화 (시작 시간 단축)
app = Application("my-app").scan(module).ready(parallel=True)
```

> **주의:** Factory Chain이 있는 경우 순차 초기화를 권장합니다.

### 9.4 의존성 대기 표시

각 컴포넌트가 어떤 의존성을 기다리는지 표시:

```
│ • OrderService       ← [Logger, OrderRepo +1]   │
                                           ↑
                                   "+1"은 추가 의존성 1개 있음을 의미
                                   (ProductRepository)
```

---

## 요약

| 기능 | 설명 |
|------|------|
| **@Component** | 클래스를 DI 컨테이너에 등록 |
| **@Factory** | 메서드 기반 인스턴스 생성 |
| **@Handler(key)** | 키 기반 핸들러 등록 |
| **Factory Chain** | 동일 타입 반환 Factory 체인 실행 |
| **@Order(n)** | Factory Chain 실행 순서 지정 |
| **Lazy[T]** | 순환 의존성 해결용 지연 로딩 |
| **@PostConstruct** | DI 완료 후 초기화 |
| **@PreDestroy** | 종료 시 정리 (역순) |
| **Dependency Graph** | 의존성 시각화 및 분석 |
| **Circular Detection** | 순환 의존성 자동 감지 및 그래프 저장 |

---

## 관련 문서

- [Factory Chain 의존성 그래프](factory-chain-dependency-graph.md)
- [Architecture Patterns](architecture-patterns.md)
- [Configuration Properties](config-properties.md)
