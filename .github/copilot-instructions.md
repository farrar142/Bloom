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

| 데코레이터                 | 역할                                         |
| -------------------------- | -------------------------------------------- |
| `@Component`               | 클래스를 DI 컨테이너에 등록                  |
| `@Scope(Scope.XXX)`        | 인스턴스 스코프 지정 (SINGLETON/PROTOTYPE)   |
| `@Factory`                 | 메서드 기반 인스턴스 생성 (복잡한 초기화 시) |
| `@Handler(key)`            | 키 기반 핸들러 등록 (예외 처리, 라우팅 등)   |
| `@Controller`              | 웹 컨트롤러 (Component 확장)                 |
| `@Get/@Post/@Put/@Delete`  | HTTP 메서드 핸들러                           |
| `@ConfigurationProperties` | 타입 안전한 설정 바인딩                      |
| `@Order`                   | 실행 순서 지정 (낮을수록 먼저)               |

### 필드 주입 패턴

**모든 필드 주입은 기본적으로 Lazy (지연 초기화)**입니다. 투명 프록시로 동작하여 `.get()` 호출이 필요 없습니다:

```python
from bloom import Component, Scope
from bloom.core import Lazy

@Component
class Service:
    repository: Repository  # 기본 Lazy 주입 (LazyFieldProxy)
    heavy_dep: Lazy[HeavyService]  # 명시적 Lazy[T] 표기도 가능 (동일 동작)

    def use_deps(self):
        # 모든 필드는 첫 접근 시점에 실제 인스턴스 생성
        # .get() 불필요! 투명 프록시로 직접 접근 가능
        self.repository.find(1)
        self.heavy_dep.do_something()
```

### Scope (인스턴스 스코프)

`@Scope` 데코레이터로 컴포넌트의 인스턴스 생명주기를 지정합니다:

| Scope       | 설명                               | 사용 예                     |
| ----------- | ---------------------------------- | --------------------------- |
| `SINGLETON` | 앱 전체에서 단일 인스턴스 (기본값) | 대부분의 서비스, 리포지토리 |
| `PROTOTYPE` | 접근할 때마다 새 인스턴스 생성     | 상태를 가진 객체, 빌더      |
| `REQUEST`   | HTTP 요청마다 새 인스턴스 (TODO)   | 요청별 컨텍스트             |

```python
from bloom import Component, Scope
from bloom.core import Scope as ScopeEnum

@Component
class SingletonService:
    pass  # 기본값: SINGLETON

@Component
@Scope(ScopeEnum.PROTOTYPE)
class PrototypeBuilder:
    """매번 새 인스턴스가 필요한 경우"""
    state: list = []  # 인스턴스별 독립 상태

@Component
class Consumer:
    builder: PrototypeBuilder  # 접근할 때마다 새 인스턴스 반환

    def create_something(self):
        b1 = self.builder  # 새 인스턴스
        b2 = self.builder  # 또 다른 새 인스턴스
        assert b1 is not b2  # True
```

**동작 원리:**

1. **SINGLETON**: 최초 접근 시 인스턴스 생성 후 캐시, 이후 동일 인스턴스 반환
2. **PROTOTYPE**: 매 접근마다 `_create_instance()` 호출하여 새 인스턴스 생성
3. 모든 필드는 `LazyFieldProxy`로 주입되어 Scope 정보를 활용

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

### TestCase 클래스 (Django 스타일)

`bloom.testing.TestCase`는 Django처럼 모든 테스트 기능을 하나의 클래스에 통합합니다:

```python
from bloom import Component
from bloom.web import Controller, Get
from bloom.testing import TestCase

@Component
class UserRepository:
    def get_users(self) -> list[str]:
        return ["alice", "bob"]

@Component
class UserService:
    repository: UserRepository

@Controller
class UserController:
    service: UserService

    @Get("/users")
    def list_users(self) -> list[str]:
        return self.service.repository.get_users()

class TestUserController(TestCase):
    # 클래스 속성으로 설정
    app_name = "test"
    components = [UserRepository, UserService, UserController]
    config = {"debug": True}  # 선택적 설정

    def test_get_users(self):
        # DI 인스턴스 조회
        service = self.get_instance(UserService)
        self.assert_instance_of(service, UserService)

        # 필드 주입 검증
        repo = self.assert_injected(service, "repository", UserRepository)

    def test_http_request(self):
        # HTTP 요청 (동기)
        response = self.get("/users")
        self.assert_success(response)
        self.assert_json_equal(response, ["alice", "bob"])

    def test_with_mock(self):
        # Mock 오버라이드
        class FakeRepository:
            def get_users(self): return ["fake"]

        with self.override(UserRepository, FakeRepository()):
            repo = self.get_instance(UserRepository)
            self.assertEqual(repo.get_users(), ["fake"])
```

#### TestCase 주요 메서드

| 카테고리      | 메서드                                                                                                    |
| ------------- | --------------------------------------------------------------------------------------------------------- |
| **DI**        | `get_instance(type)`, `get_instances(type)`, `has_instance(type)`                                         |
| **HTTP**      | `get()`, `post()`, `put()`, `delete()`, `patch()`                                                         |
| **Mock**      | `override(type, instance)`, `override_factory(type, factory)`                                             |
| **Assertion** | `assert_instance_of()`, `assert_injected()`, `assert_status()`, `assert_success()`, `assert_json_equal()` |
| **디버깅**    | `print_container_tree()`, `get_container_info()`                                                          |

#### AsyncTestCase (비동기)

```python
from bloom.testing import AsyncTestCase
import pytest

class TestAsyncService(AsyncTestCase):
    components = [AsyncService]

    @pytest.mark.asyncio
    async def test_async_method(self):
        response = await self.async_get("/api/data")
        self.assert_success(response)
```

자세한 내용은 `docs/testing-testcase.md` 참조.

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

| 계층         | 역할                                  | 예시                                       |
| ------------ | ------------------------------------- | ------------------------------------------ |
| **Entry**    | 개별 항목 (불변 데이터)               | `RouteEntry`, `HttpMethodHandlerContainer` |
| **Registry** | Entry 컬렉션 관리, 조회/매칭          | `RouteRegistry`, `MethodRegistry`          |
| **Manager**  | Registry들을 통합 관리, 외부 API 제공 | `Router`                                   |

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

### Factory Chain 패턴

동일 타입을 반환하는 여러 `@Factory`가 체인으로 연결되어 순차 실행됩니다:

```python
from bloom import Component
from bloom.core.decorators import Factory, Order

@Component
class CounterConfig:
    @Factory
    def create(self) -> Counter:
        """Creator: 최초 인스턴스 생성 (자기 타입 미의존)"""
        return Counter(0)

    @Factory
    @Order(1)
    def add_one(self, counter: Counter) -> Counter:
        """Modifier: 기존 인스턴스 수정 (자기 타입 의존)"""
        counter.value += 1
        return counter

    @Factory
    @Order(2)
    def add_two(self, counter: Counter) -> Counter:
        """Modifier: 추가 수정"""
        counter.value += 2
        return counter
```

실행 순서: `create()` → `add_one()` → `add_two()` = Counter(3)

**순서 결정 규칙:**

1. `@Order` 데코레이터: 값이 낮을수록 먼저 실행
2. 의존성 기반: Creator(자기 타입 미의존) → Modifier(자기 타입 의존)

**Ambiguous Provider 에러:**

- Creator가 2개 이상이고 Modifier가 있으면 에러 발생
- 해결: Creator는 1개만, 나머지는 Modifier로 구성

자세한 내용은 `docs/factory-chain-dependency-graph.md` 참조.

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

### Method Advice 패턴 (AOP)

메서드 호출을 가로채어 전처리/후처리 로직을 실행하는 AOP 패턴입니다.

```python
from bloom import Component
from bloom.core.decorators import Factory
from bloom.core.container import HandlerContainer
from bloom.core.container.element import Element
from bloom.core.advice import MethodAdvice, MethodAdviceRegistry, InvocationContext

# 1. 마커 Element 정의
class TransactionalElement(Element):
    pass

# 2. 데코레이터 정의
def Transactional(method):
    container = HandlerContainer.get_or_create(method)
    container.add_elements(TransactionalElement())
    return method

# 3. Advice 구현
@Component
class TransactionAdvice(MethodAdvice):
    db: Database  # DI로 주입

    def supports(self, container: HandlerContainer) -> bool:
        return container.has_element(TransactionalElement)

    async def before(self, context: InvocationContext) -> None:
        tx = await self.db.begin()
        context.set_attribute("tx", tx)

    async def after(self, context: InvocationContext, result: Any) -> Any:
        tx = context.get_attribute("tx")
        await tx.commit()
        return result

    async def on_error(self, context: InvocationContext, error: Exception) -> Any:
        tx = context.get_attribute("tx")
        await tx.rollback()
        raise error

# 4. Registry 생성 (@Factory 필수!)
@Component
class AdviceConfig:
    @Factory
    def advice_registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
        registry = MethodAdviceRegistry()
        for advice in advices:
            registry.register(advice)
        return registry

# 5. 서비스에서 사용 (HandlerContainer가 이미 생성됨 - @Handler 불필요)
@Component
class OrderService:
    @Transactional
    async def create_order(self, order_data: dict) -> Order:
        order = Order(**order_data)
        await self.order_repo.save(order)
        return order
```

**실행 흐름:**

- 정상: `before()` → 핸들러 → `after()`
- 예외: `before()` → 핸들러 [예외!] → `on_error()`

**ProxyableDescriptor 추상 클래스:**

디스크립터(`@Task` 등)가 프록시 적용을 지원하기 위한 ABC입니다.
`Application`은 구체적인 디스크립터 타입을 몰라도 이 ABC만 알면 됩니다.

```python
from abc import ABC, abstractmethod
from bloom.core.abstract import ProxyableDescriptor

class ProxyableDescriptor(ABC):
    @abstractmethod
    def get_original_handler(self) -> Callable | None:
        """원본 핸들러 반환 (HandlerContainer 조회용)"""
        ...

    @abstractmethod
    def apply_proxy(self, instance: Any, proxy: Any) -> Any:
        """프록시를 적용하고 바인딩된 객체 반환"""
        ...

# 사용 예: TaskDescriptor가 ProxyableDescriptor를 상속
class TaskDescriptor(ProxyableDescriptor, Generic[T]):
    def get_original_handler(self) -> Callable[..., T]:
        return self._handler

    def apply_proxy(self, instance: Any, proxy: Any) -> BoundTask[T]:
        bound_task = self.__get__(instance, type(instance))
        bound_task._proxy = proxy
        bound_task._use_proxy = True
        return bound_task
```

자세한 내용은 `docs/method-advice-pattern.md` 참조.

### Task 패턴 (@Task) - Celery 스타일

`@Task` 데코레이터로 메서드를 비동기 태스크로 정의합니다. Celery와 유사한 인터페이스를 제공합니다.

#### 로컬 태스크 (AsyncioTaskBackend)

단일 프로세스 내에서 비동기로 태스크를 실행합니다:

```python
from bloom import Component
from bloom.core.decorators import Factory
from bloom.task import Task, AsyncioTaskBackend, TaskResult, ScheduledTask

@Component
class EmailService:
    @Task
    def send_email(self, to: str, subject: str) -> str:
        return f"Sent to {to}"

    @Task(name="important-email", max_retries=3)
    async def send_important_email(self, to: str) -> str:
        await self.send_with_retry(to)
        return f"Important sent to {to}"

@Component
class TaskConfig:
    @Factory
    def task_backend(self) -> AsyncioTaskBackend:
        return AsyncioTaskBackend(max_workers=4)

# 사용법:
service = app.manager.get_instance(EmailService)

# 1. 직접 호출 (동기)
result = service.send_email("user@example.com", "Hello")

# 2. 백그라운드 실행 (비동기)
task_result: TaskResult = service.send_email.delay("user@example.com", "Hello")
value = task_result.get()           # 결과 대기
task_result.ready()                 # 완료 여부
task_result.successful()            # 성공 여부

# 3. 스케줄 등록
scheduled: ScheduledTask = service.send_email.schedule(
    fixed_rate=60,                  # 60초마다
    args=("admin@example.com", "Report"),
)
scheduled.pause()   # 일시정지
scheduled.resume()  # 재개
scheduled.cancel()  # 취소
```

#### 분산 태스크 (DistributedTaskBackend)

Redis 등 브로커를 통해 여러 워커 프로세스에서 태스크를 분산 처리합니다:

```python
from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.task import Task, DistributedTaskBackend, RedisBroker, InMemoryBroker

@Component
class EmailService:
    @Task(name="send_email")
    def send_email(self, to: str, subject: str) -> str:
        return f"Sent to {to}: {subject}"

@Component
class TaskConfig:
    @Factory
    def task_backend(self) -> DistributedTaskBackend:
        # 프로덕션: Redis 브로커
        broker = RedisBroker("redis://localhost:6379/0")
        # 개발: 인메모리 브로커
        # broker = InMemoryBroker()
        return DistributedTaskBackend(broker)

app = Application("myapp").scan(__name__).ready()
```

**워커 실행:**

```bash
# uvicorn으로 웹 서버 실행
uvicorn main:app.asgi --reload

# 별도 터미널에서 워커 실행
bloom worker main:app.queue
bloom worker main:app.queue --concurrency 4
bloom worker main:app.queue -c 8

# Python -m 으로 실행
python -m bloom worker main:app.queue
```

**아키텍처:**

```
┌─────────────────┐          ┌─────────────────┐
│  Web Server     │          │  Worker         │
│  (uvicorn)      │          │  (bloom worker) │
│                 │          │                 │
│  app.asgi       │          │  app.queue      │
│  HTTP 요청 처리 │          │  태스크 처리    │
└────────┬────────┘          └────────┬────────┘
         │                            │
         │  delay() 호출              │  태스크 실행
         ▼                            ▼
    ┌────────────────────────────────────┐
    │          Redis Broker              │
    │   (InMemoryBroker for dev)         │
    └────────────────────────────────────┘
```

**브로커 종류:**

| 브로커           | 용도               | 특징                          |
| ---------------- | ------------------ | ----------------------------- |
| `InMemoryBroker` | 개발/테스트        | 단일 프로세스, 재시작 시 소실 |
| `RedisBroker`    | 프로덕션 분산 환경 | 멀티 프로세스, 영속성 지원    |

**스케줄 트리거:**

- `fixed_rate`: 시작 시점 기준 고정 간격 (초)
- `fixed_delay`: 완료 시점 기준 고정 지연 (초)
- `cron`: cron 표현식 (분 시 일 월 요일)

자세한 내용은 `docs/task-system.md` 참조.

### ConfigurationProperties 패턴

타입 안전한 설정 바인딩:

```python
from dataclasses import dataclass
from bloom import Component
from bloom.config import ConfigurationProperties

@ConfigurationProperties("app.database")
@dataclass
class DatabaseConfig:
    host: str = "localhost"
    port: int = 5432
    username: str = ""
    password: str = ""

@Component
class DatabaseService:
    config: DatabaseConfig  # 자동으로 app.database.* 설정 바인딩

# Application 설정
app = Application("myapp")
app.load_config("config/application.yaml")
app.scan(__name__).ready()
```

자세한 내용은 `docs/config-properties.md` 참조.

### Container 오버라이드 규칙

중첩 데코레이터에서 더 구체적인(하위) Container가 우선합니다. MRO 인덱스로 구체성을 판단합니다:

```python
# 상위 → 하위: 하위가 오버라이드, Element 자동 이전
@Order(1)        # HandlerContainer + OrderElement
@Get("/users")   # HttpMethodHandlerContainer로 교체, OrderElement 이전됨
def handler(): pass

# 하위 → 상위: 하위 유지, Element만 추가
@Get("/users")   # HttpMethodHandlerContainer 생성
@Order(1)        # 기존 컨테이너에 OrderElement만 추가
def handler(): pass
```

자세한 내용은 `docs/architecture-patterns.md` 참조.

## 파일 구조 가이드

```
bloom/
├── core/           # DI 컨테이너 핵심
│   ├── abstract/   # 추상 패턴 (Entry, AbstractRegistry, AbstractManager, EntryGroup, GroupRegistry, ProxyableDescriptor)
│   ├── container/  # Container, Element, ComponentContainer, FactoryContainer, HandlerContainer, CallableContainer
│   ├── advice/     # AOP (MethodAdvice, MethodAdviceRegistry, MethodInvocationManager)
│   ├── manager.py  # ContainerManager (ContextVar 기반)
│   ├── orchestrator.py # ContainerOrchestrator (초기화 오케스트레이션)
│   ├── lifecycle.py # PostConstruct/PreDestroy 처리
│   └── lazy.py     # Lazy[T] descriptor
├── config/         # 설정 관리
│   ├── manager.py  # ConfigManager
│   ├── properties.py # ConfigurationProperties
│   └── loader.py   # 설정 로더 (YAML, JSON, ENV)
├── task/           # 태스크 시스템 (Celery 스타일)
│   ├── __init__.py # 패키지 exports
│   ├── trigger.py  # Trigger, CronTrigger, FixedRateTrigger, FixedDelayTrigger
│   ├── result.py   # TaskResult, AsyncTaskResult, ScheduledTask
│   ├── backend.py  # TaskBackend, AsyncioTaskBackend
│   ├── decorator.py # @Task, TaskElement, TaskDescriptor, BoundTask
│   ├── advice.py   # TaskMethodAdvice
│   ├── distributed.py # DistributedTaskBackend (분산 처리)
│   ├── registry.py # TaskRegistry (태스크 이름-핸들러 매핑)
│   ├── message.py  # TaskMessage, TaskState (직렬화용)
│   ├── queue_app.py # QueueApplication (워커 앱)
│   └── broker/     # 메시지 브로커
│       ├── base.py   # Broker ABC
│       ├── memory.py # InMemoryBroker (개발용)
│       └── redis.py  # RedisBroker (프로덕션용)
├── web/            # ASGI 웹 레이어
│   ├── router.py   # URL 라우팅 (Manager-Registry-Entry 패턴)
│   ├── routing/    # RouteRegistry, RouteEntry, MethodRegistry
│   ├── params/     # 파라미터 리졸버들
│   ├── middleware/ # 미들웨어 (GroupRegistry 패턴)
│   ├── builtin/    # 내장 미들웨어 (CorsMiddleware, ErrorHandlerMiddleware)
│   ├── auth/       # 인증/인가
│   └── error/      # 에러 핸들링
├── __main__.py     # CLI 엔트리포인트 (bloom worker 등)
└── application.py  # Application 클래스 (asgi, queue 프로퍼티)
```

## 주의사항

- `pydantic>=2.0` 필수 의존성 (BaseModel 파라미터 바인딩)
- **Python 3.13 타입 문법 사용**:
  - `class MyClass[T]:` 사용 (`class MyClass(Generic[T]):` ❌)
  - `def func[T](x: T) -> T:` 사용
  - `type Alias = int | str` 사용
  - `Callable[Concatenate[Self, P], R]` 패턴으로 인스턴스 메서드 타이핑
- 비동기 핸들러 지원 (`async def` 메서드 자동 감지)
- **⚠️ 메타데이터 저장 금지 사항**: 클래스나 메서드에 `setattr`로 직접 메타데이터를 저장하지 말 것! 반드시 Container의 Element를 통해서만 저장/조회
- **⚠️ HTTP path vs WebSocket STOMP path**: `@Controller`의 `@RequestMapping` path는 HTTP 전용이며, `@MessageMapping` 등의 STOMP path와는 완전히 별개입니다. `@MessageController`만 STOMP prefix를 제공합니다.
