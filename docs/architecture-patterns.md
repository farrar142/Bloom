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
