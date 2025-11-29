# Bloom Framework Architecture Patterns

## 핵심 패턴: Manager → Registry → Entry

Bloom 프레임워크는 일관된 3-tier 아키텍처 패턴을 따릅니다.

```
┌─────────────────┐
│     Manager     │  ← 전체 조율, 초기화, 수집
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Registry     │  ← 등록/조회, 실행 순서 관리
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│      Entry      │  ← 실제 작업 수행 단위
└─────────────────┘
```

## 영역별 패턴 분석

| 영역 | Manager | Registry | Entry |
|------|---------|----------|-------|
| **DI Core** | `ContainerManager` | - | `Container` (Component/Factory/Handler) |
| **에러 처리** | - | `ErrorHandlerMiddleware` | `ErrorHandler` |
| **미들웨어** | - | `MiddlewareChain` | `Middleware` |
| **정적 파일** | `StaticFilesManager` | - | `StaticFiles` |
| **메시징** | `WebSocketManager` | `StompEndpointRegistry` | `MessageHandler` |
| **파라미터** | - | `ParameterResolverRegistry` | `ParameterResolver` |
| **라이프사이클** | `LifecycleManager` | - | `PostConstruct/PreDestroy` |
| **설정** | `ConfigManager` | - | `ConfigurationProperties` |

## 각 계층의 역할

### Manager
- **역할**: 전체 시스템 조율, 초기화 순서 관리, Entry 수집
- **특징**: Application 레벨에서 동작, ContextVar 기반 스레드 안전
- **예시**: `ContainerManager`, `StaticFilesManager`, `WebSocketManager`

### Registry
- **역할**: Entry 등록/조회, 실행 순서 관리
- **특징**: 키 기반 조회, 우선순위 처리, 체인 패턴
- **예시**: `MiddlewareChain`, `StompEndpointRegistry`, `ParameterResolverRegistry`

### Entry
- **역할**: 실제 작업을 수행하는 단위
- **특징**: Registry에 등록되어 Manager에 의해 관리됨
- **예시**: `StaticFiles`, `Middleware`, `ErrorHandler`, `ParameterResolver`

## DI Container vs Entry

**주의**: DI 시스템의 `Container` (ComponentContainer, FactoryContainer 등)는 
이 패턴의 Entry와는 별개입니다.

- **DI Container**: 클래스/메서드에 부착되어 메타데이터와 Element를 관리
- **Entry**: Registry에 등록되어 실제 작업을 수행하는 단위

```python
# DI Container - 클래스에 메타데이터 부착
@Component
class MyService:  # ComponentContainer가 부착됨
    pass

# Entry - Registry에 등록되는 작업 단위
static_entry = StaticFiles("/static", "public")
manager.registry.register("/static", static_entry)
```

## Container-Element 패턴 (DI용)

DI에서 메타데이터는 반드시 Container의 Element를 통해서만 저장/조회합니다.

```python
# ❌ 잘못된 방법 (클래스에 직접 저장)
setattr(cls, "_my_meta", {"key": "value"})

# ✅ 올바른 방법 (Container Element 사용)
class MyElement(Element):
    def __init__(self, value: str):
        super().__init__()
        self.metadata["my_key"] = value

container = ComponentContainer.get_or_create(cls)
container.add_element(MyElement(value))
```

## 중첩 데코레이터와 Container 오버라이드

### 데코레이터 실행 순서

Python에서 중첩 데코레이터는 **아래에서 위로** 실행됩니다:

```python
@Order(1)        # 3번째 실행
@Get("/users")   # 2번째 실행
def handler():   # 1번째: 함수 정의
    pass
```

실제 실행 순서:
1. `handler` 함수 정의
2. `@Get("/users")` → `HttpMethodHandlerContainer` 생성
3. `@Order(1)` → 기존 컨테이너에 `OrderElement` 추가

### Container 계층 구조

Container는 상속 계층을 가집니다:

```
Container (base)
    └── HandlerContainer
            └── HttpMethodHandlerContainer
            └── ErrorHandlerContainer
```

### 오버라이드 규칙

**핵심 원칙**: 더 구체적인(하위) Container가 우선합니다.

```python
# 시나리오 1: 상위 → 하위 (하위가 오버라이드)
@Order(1)        # HandlerContainer 생성
@Get("/users")   # HttpMethodHandlerContainer로 교체, OrderElement 이전
def handler(): pass

# 결과: HttpMethodHandlerContainer (OrderElement 포함)


# 시나리오 2: 하위 → 상위 (하위 유지)
@Get("/users")   # HttpMethodHandlerContainer 생성
@Order(1)        # 기존 컨테이너에 OrderElement만 추가
def handler(): pass

# 결과: HttpMethodHandlerContainer (OrderElement 포함)
```

### MRO 기반 구체성 판단

Python의 Method Resolution Order(MRO)를 사용하여 어떤 Container가 더 구체적인지 판단합니다:

```python
# HttpMethodHandlerContainer.__mro__
# [HttpMethodHandlerContainer, HandlerContainer, Container, object]
#          index: 0                   1              2        3

# MRO 인덱스가 낮을수록 더 구체적 (하위 클래스)
```

### _apply_override_rules 동작

`Container.get_or_create()` 호출 시 `_apply_override_rules`가 자동 적용됩니다:

```python
@classmethod
def _apply_override_rules(cls, target, create_new: Callable[[], Self]) -> Self:
    existing = cls.get_container(target)
    
    if existing is None:
        # 기존 컨테이너 없음 → 새로 생성
        new_container = create_new()
        return new_container
    
    # MRO 인덱스 비교 (낮을수록 구체적)
    existing_idx = cls._get_mro_index(type(existing))
    new_idx = cls._get_mro_index(cls)
    
    if new_idx < existing_idx:
        # 새 컨테이너가 더 구체적 → 교체
        new_container = create_new()
        existing._transfer_elements_to(new_container)  # Element 이전
        return new_container
    else:
        # 기존 컨테이너가 더 구체적 → 유지
        return existing
```

### Element 이전

상위 컨테이너가 하위 컨테이너로 교체될 때, 기존 Element들이 자동으로 이전됩니다:

```python
@Order(1)        # HandlerContainer + OrderElement(1)
@Get("/users")   # HttpMethodHandlerContainer 생성
                 # OrderElement(1)이 자동 이전됨
def handler(): pass

container = handler.__container__
assert isinstance(container, HttpMethodHandlerContainer)
assert container.get_metadata("order") == 1      # ✅ 이전된 Element
assert container.get_metadata("http_method") == "GET"
```

### 실제 사용 예시

```python
@Controller
class UserController:
    @Order(1)              # 순서 지정
    @Get("/users")         # HTTP GET 핸들러
    def list_users(self):
        return []
    
    @ErrorHandler(ValueError, KeyError)  # 여러 예외 처리
    def handle_errors(self, error: Exception):
        return {"error": str(error)}
```

각 데코레이터의 역할:
- `@Order(1)`: `OrderElement` 추가
- `@Get("/users")`: `HttpMethodHandlerContainer` + `MethodElement` + `PathElement`
- `@ErrorHandler(...)`: `ErrorHandlerContainer` + 여러 `ExceptionTypeElement`

## 추상 클래스 (core/abstract)

Manager는 ContainerManager에서 Registry를 검색하고, 없으면 Entry들을 수집하여 자동으로 Registry를 생성합니다.

```python
from bloom.core.abstract import Entry, AbstractRegistry, AbstractManager

# Entry - Registry에 등록되는 항목 (값만 가짐)
class StaticFileEntry(Entry[Path]):
    def __init__(self, path_prefix: str, directory: Path):
        super().__init__(directory)
        self.path_prefix = path_prefix

# Registry - Entry 리스트 관리
class StaticFilesRegistry(AbstractRegistry[StaticFileEntry]):
    pass

# Manager - 전체 조율 및 Registry 자동 생성
class StaticFilesManager(AbstractManager[StaticFilesRegistry]):
    registry_type = StaticFilesRegistry  # 생성할 Registry 타입
    entry_type = StaticFileEntry         # 수집할 Entry 타입

# 사용 시
manager = StaticFilesManager()
manager.initialize(container_manager)  # Registry 검색/생성 및 Entry 수집

# Entry만 등록하면 Manager가 알아서 처리
@Component
class StaticConfig:
    @Factory
    def public_files(self) -> StaticFileEntry:
        return StaticFileEntry("/static", Path("public"))

    @Factory
    def asset_files(self) -> StaticFileEntry:
        return StaticFileEntry("/assets", Path("assets"))

# Registry 순회
for entry in manager.registry:
    print(f"{entry.path_prefix} -> {entry.value}")
```

## 파일 위치

```
bloom/
├── core/
│   ├── manager.py           # ContainerManager
│   ├── lifecycle.py         # LifecycleManager
│   ├── abstract/            # 추상 패턴 클래스
│   │   ├── entry.py         # Entry[T]
│   │   ├── registry.py      # AbstractRegistry[E]
│   │   └── manager.py       # AbstractManager[R]
│   └── container/           # DI Container (별개 개념)
│       ├── base.py          # Container
│       ├── component.py     # ComponentContainer
│       ├── factory.py       # FactoryContainer
│       └── handler.py       # HandlerContainer
├── config/
│   └── manager.py           # ConfigManager
└── web/
    ├── static.py            # StaticFilesManager, StaticFiles
    ├── middleware/
    │   └── chain.py         # MiddlewareChain
    ├── error/
    │   └── handler.py       # ErrorHandler
    ├── params/
    │   └── registry.py      # ParameterResolverRegistry
    └── messaging/
        ├── manager.py       # WebSocketManager
        └── configurer.py    # StompEndpointRegistry
```
