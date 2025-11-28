# Bloom Framework - AI Coding Instructions

## 프로젝트 개요

Bloom은 Spring Framework에서 영감을 받은 Python DI(의존성 주입) 컨테이너 프레임워크입니다. ASGI 기반 웹 레이어와 데코레이터 기반 컴포넌트 시스템을 제공합니다.

## 핵심 아키텍처

### DI Container 흐름

1. `@Component` → `ComponentContainer` 생성 및 자동 등록
2. `ContainerManager`가 모든 컨테이너 관리 (ContextVar 기반 스레드 안전)
3. `Application.scan(module).ready()` 체이닝으로 초기화
4. 토폴로지컬 정렬로 의존성 순서 보장 및 순환 감지

### 주요 컴포넌트

| 데코레이터                | 역할                                         |
| ------------------------- | -------------------------------------------- |
| `@Component`              | 클래스를 DI 컨테이너에 등록                  |
| `@Factory`                | 메서드 기반 인스턴스 생성 (복잡한 초기화 시) |
| `@Handler(key)`           | 키 기반 핸들러 등록 (예외 처리, 라우팅 등)   |
| `@Controller`             | 웹 컨트롤러 (Component 확장)                 |
| `@Get/@Post/@Put/@Delete` | HTTP 메서드 핸들러                           |

### 필드 주입 패턴

```python
@Component
class Service:
    repository: Repository  # 타입 어노테이션만으로 자동 주입
    lazy_dep: Lazy[HeavyService]  # 순환 의존성 해결용 지연 주입
```

## 웹 레이어 구조

- `bloom/web/router.py`: 경로 매칭 및 핸들러 디스패치
- `bloom/web/params/`: 파라미터 리졸버 (`@RequestBody`, `@HttpHeader`, `@HttpCookie`, `@UploadedFile`)
- `bloom/web/middleware/`: 미들웨어 체인 (요청→A→B→핸들러→B→A→응답)
- `bloom/web/auth/`: 인증/인가 (`Authenticator`, `@Authorize`)

## 개발 워크플로우

### Python 환경 (uv 사용)

```bash
uv run python script.py          # Python 스크립트 실행
uv run pytest                    # 테스트 실행
uv add package_name              # 패키지 추가
uv sync                          # 의존성 동기화
```

### 테스트 실행

```bash
uv run pytest                    # 전체 테스트 (performance 제외)
uv run pytest -m performance     # 성능 벤치마크 테스트만
uv run pytest -m ""              # 모든 테스트 (performance 포함)
uv run pytest tests/test_web.py -v   # 웹 레이어 테스트
uv run pytest -k "lifecycle"     # 특정 패턴 테스트
```

### 테스트 작성 규칙

- `tests/conftest.py`의 `reset_container_manager` fixture가 테스트 격리 자동 처리
- 새 컴포넌트 정의 시 테스트 내부에서 `Application("test").ready()` 호출 필요
- 비동기 테스트는 `@pytest.mark.asyncio` 데코레이터 사용

### 서버 실행

```bash
uv run uvicorn main:app.asgi --reload  # app = Application("name").scan(...).ready()
```

## 코드 패턴 및 컨벤션

### Manager-Registry-Entry 패턴

웹 레이어에서 핸들러/라우트 등을 체계적으로 관리하기 위한 3계층 패턴입니다.

```
Manager (싱글톤)
  └── Registry (컬렉션 관리)
        └── Entry (개별 항목)
```

#### 계층별 역할

| 계층 | 역할 | 예시 |
|------|------|------|
| **Entry** | 개별 항목 (불변 데이터) | `RouteEntry`, `HttpMethodHandler` |
| **Registry** | Entry 컬렉션 관리, 조회/매칭 | `RouteRegistry`, `MethodRegistry` |
| **Manager** | Registry들을 통합 관리, 외부 API 제공 | `Router` |

#### 추상 클래스 (`bloom/core/abstract/`)

```python
from bloom.core.abstract import Entry, AbstractRegistry, AbstractManager

# 1. Entry 정의 (개별 항목)
class RouteEntry(Entry):
    path: str
    method: str
    handler: Callable

# 2. Registry 정의 (Entry 컬렉션)
class RouteRegistry(AbstractRegistry[RouteEntry]):
    def match(self, path: str, method: str) -> RouteEntry | None:
        for entry in self._entries:
            if entry.matches(path, method):
                return entry
        return None

# 3. Manager 정의 (Registry 통합)
class Router(AbstractManager[RouteRegistry]):
    def dispatch(self, request: HttpRequest) -> HttpResponse:
        for registry in self._registries:
            entry = registry.match(request.path, request.method)
            if entry:
                return entry.handler(request)
        return HttpResponse.not_found()
```

#### GroupRegistry 패턴 (미들웨어용)

미들웨어처럼 그룹 단위로 활성화/비활성화가 필요한 경우:

```python
from bloom.core.abstract import EntryGroup, GroupRegistry

# EntryGroup: 항목들을 그룹으로 묶음
class MiddlewareGroup(EntryGroup[Middleware]):
    pass

# GroupRegistry: EntryGroup들을 관리
class MiddlewareChain(GroupRegistry[Middleware]):
    group_type = MiddlewareGroup
    
    def add_group_after(self, *middlewares: Middleware) -> MiddlewareGroup:
        group = MiddlewareGroup()
        for m in middlewares:
            group.add(m)
        self._groups.append(group)
        return group
```

### Container-Element 패턴 (중요!)

**핵심 원칙: 메타데이터는 무조건 Container의 Element를 통해서만 저장/조회**

클래스나 메서드에 직접 속성을 저장하지 말고, 반드시 Container의 Element를 통해 메타데이터를 관리해야 합니다.

#### ❌ 잘못된 방법 (클래스에 직접 저장)

```python
def MyDecorator(cls):
    # ❌ 클래스에 직접 메타데이터 저장 - 절대 금지!
    setattr(cls, "_my_meta", {"key": "value"})
    return cls

def get_meta(cls):
    # ❌ 클래스 속성 직접 조회 - 절대 금지!
    return getattr(cls, "_my_meta", {})
```

#### ✅ 올바른 방법 (Container Element 사용)

```python
from bloom.core.container import ComponentContainer
from bloom.core.container.element import Element

# 1. Element 클래스 정의
class MyDecoratorElement(Element):
    """메타데이터를 담는 Element"""

    def __init__(self, value: str):
        super().__init__()
        # metadata 딕셔너리에 저장
        self.metadata["my_key"] = value

    @property
    def value(self) -> str:
        return self.metadata.get("my_key", "")

# 2. 데코레이터에서 Element를 Container에 추가
def MyDecorator(value: str):
    def wrapper(cls):
        container = ComponentContainer.get_or_create(cls)
        container.add_elements(MyDecoratorElement(value))
        return cls
    return wrapper

# 3. 메타데이터 확인 - Element 존재 여부
def has_my_decorator(cls: type) -> bool:
    container = ComponentContainer.get_container(cls)
    if container is None:
        return False
    # Element 타입으로 확인
    return container.has_element(MyDecoratorElement)

# 4. 메타데이터 조회 - get_metadatas API 사용
def get_my_value(cls: type) -> str:
    container = ComponentContainer.get_container(cls)
    if container is None:
        return ""
    # 메타데이터 키로 조회
    values = container.get_metadatas("my_key", default="")
    return values[0] if values else ""
```

#### Container API

```python
# Container 생성/조회
container = ComponentContainer.get_or_create(cls)  # 없으면 생성
container = ComponentContainer.get_container(cls)   # 없으면 None

# Element 추가
container.add_elements(MyElement(value))

# Element 존재 확인
has_it = container.has_element(MyElement)  # Element 타입(클래스)으로 확인

# 메타데이터 조회
values = container.get_metadatas("key", default="")  # 키로 조회, 리스트 반환
value = values[0] if values else ""
```

#### 실제 사례: MessageController

```python
class MessageControllerElement(Element):
    key = "message_controller"

    def __init__(self, prefix: str = ""):
        super().__init__()
        self.metadata["prefix"] = prefix  # ✅ metadata에 저장

    @property
    def value(self) -> str:
        return self.metadata.get("prefix", "")

def MessageController(cls_or_prefix):
    def _apply(cls, prefix):
        container = ComponentContainer.get_or_create(cls)
        container.add_elements(MessageControllerElement(prefix))  # ✅ Element로 저장
        return cls
    # ... 오버로딩 로직

def is_message_controller(cls: type) -> bool:
    container = ComponentContainer.get_container(cls)
    if container is None:
        return False
    return container.has_element(MessageControllerElement)  # ✅ Element로 확인

def get_prefix(cls: type) -> str:
    container = ComponentContainer.get_container(cls)
    if container is None:
        return ""
    prefixes = container.get_metadatas("prefix", default="")  # ✅ 메타데이터로 조회
    return prefixes[0] if prefixes else ""
```

### Container 시스템 확장 시

1. `bloom/core/container/element.py`의 `Element` 상속하여 메타데이터 정의
2. `bloom/core/container/base.py`의 `Container` 상속하여 새 컨테이너 타입 구현
3. 데코레이터에서 `XxxContainer.get_or_create(target)` 패턴 사용
4. **메타데이터는 반드시 Element의 metadata 딕셔너리에 저장**
5. **조회는 `has_element(ElementClass)` 및 `get_metadatas(key)` 사용**

### 파라미터 리졸버 추가 시

1. `bloom/web/params/base.py`의 `ParameterResolver` 상속
2. `bloom/web/params/__init__.py`에서 레지스트리 등록 순서 중요 (먼저 등록된 것이 우선)

### 라이프사이클 훅

```python
@Component
class DbConnection:
    @PostConstruct
    def connect(self): ...    # DI 완료 후 호출

    @PreDestroy
    def disconnect(self): ... # 종료 시 역순 호출
```

### MiddlewareChain 설정

`@Factory`로 `MiddlewareChain`을 생성하고, `*middlewares: Middleware`로 모든 미들웨어 인스턴스를 자동 주입받습니다:

```python
from bloom import Component
from bloom.core.decorators import Factory
from bloom.web.middleware import Middleware, MiddlewareChain, CorsMiddleware

@Component
class MyCors(CorsMiddleware):
    allow_origins = ["https://example.com"]
    allow_credentials = True

@Component
class MiddlewareConfig:
    @Factory
    def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
        chain = MiddlewareChain()
        chain.add_group_after(*middlewares)  # 모든 Middleware 서브클래스 자동 주입
        return chain
```

**미들웨어를 `@Factory`로 생성하는 방법** (외부 설정이나 복잡한 초기화 필요 시):

```python
from bloom import Component
from bloom.core.decorators import Factory
from bloom.web.middleware import Middleware, MiddlewareChain, CorsMiddleware

@Component
class MiddlewareConfig:
    config: AppConfig  # 설정 주입

    @Factory
    def cors_middleware(self) -> CorsMiddleware:
        # 동적으로 설정값 적용
        cors = CorsMiddleware()
        cors.allow_origins = self.config.allowed_origins
        cors.allow_credentials = self.config.allow_credentials
        return cors

    @Factory
    def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
        chain = MiddlewareChain()
        chain.add_group_after(*middlewares)  # cors_middleware 포함 자동 주입
        return chain
```

실행 순서: 요청 → A → B → C → 핸들러 → C → B → A → 응답 (역순)

### Qualifier 사용법

동일 타입의 여러 인스턴스를 구분할 때 사용:

```python
from bloom import Component, Qualifier

@Component
@Qualifier("mysql")
class MySqlRepository(Repository):
    pass

@Component
@Qualifier("postgres")
class PostgresRepository(Repository):
    pass

@Component
class Service:
    # qualifier로 특정 인스턴스 주입
    repo: Annotated[Repository, "mysql"]
```

`ContainerManager.get_instance(Repository, qualifier="mysql")`로 특정 인스턴스 조회 가능.

### ErrorHandler 패턴

예외 타입별 핸들러 등록. Controller 내부 정의는 해당 경로에서만, Component 정의는 글로벌로 동작:

```python
from bloom.web.error import ErrorHandler

@Controller
@RequestMapping("/api/users")
class UserController:
    # 이 Controller 경로 하위에서만 동작
    @ErrorHandler(ValueError)
    def handle_value_error(self, error: ValueError) -> HttpResponse:
        return HttpResponse.bad_request(str(error))

@Component
class GlobalErrorHandlers:
    # 모든 엔드포인트에서 동작 (글로벌)
    @ErrorHandler(Exception)
    def fallback(self, error: Exception) -> HttpResponse:
        return HttpResponse.internal_error("Internal Server Error")
```

우선순위: Controller 스코프 정확한 타입 → Controller 부모 타입 → 글로벌 정확한 타입 → 글로벌 부모 타입

## 파일 구조 가이드

```
bloom/
├── core/           # DI 컨테이너 핵심
│   ├── abstract/   # 추상 패턴 (Entry, AbstractRegistry, AbstractManager, EntryGroup, GroupRegistry)
│   ├── container/  # Container, Element, ComponentContainer, FactoryContainer, HandlerContainer
│   ├── manager.py  # ContainerManager (ContextVar 기반)
│   ├── lifecycle.py # PostConstruct/PreDestroy 처리
│   └── lazy.py     # Lazy[T] descriptor
├── web/            # ASGI 웹 레이어
│   ├── router.py   # URL 라우팅 (Manager-Registry-Entry 패턴)
│   ├── routing/    # RouteRegistry, RouteEntry, MethodRegistry
│   ├── params/     # 파라미터 리졸버들
│   ├── middleware/ # 미들웨어 (GroupRegistry 패턴)
│   ├── builtin/    # 내장 미들웨어 (CorsMiddleware, ErrorHandlerMiddleware)
│   ├── auth/       # 인증/인가
│   └── error/      # 에러 핸들링
```

## 주의사항

- `pydantic>=2.0` 필수 의존성 (BaseModel 파라미터 바인딩)
- Python 3.12+ 문법 사용 (Generic `[T]` 문법, `type[T]`)
- 비동기 핸들러 지원 (`async def` 메서드 자동 감지)
- **⚠️ 메타데이터 저장 금지 사항**: 클래스나 메서드에 `setattr`로 직접 메타데이터를 저장하지 말 것! 반드시 Container의 Element를 통해서만 저장/조회
- **⚠️ HTTP path vs WebSocket STOMP path**: `@Controller`의 `@RequestMapping` path는 HTTP 전용이며, `@MessageMapping` 등의 STOMP path와는 완전히 별개입니다. `@MessageController`만 STOMP prefix를 제공합니다.
