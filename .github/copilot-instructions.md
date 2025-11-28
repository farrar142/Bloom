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

### 테스트 실행

```bash
pytest                           # 전체 192개 테스트
pytest tests/test_web.py -v      # 웹 레이어 테스트
pytest -k "lifecycle"            # 특정 패턴 테스트
```

### 테스트 작성 규칙

- `tests/conftest.py`의 `reset_container_manager` fixture가 테스트 격리 자동 처리
- 새 컴포넌트 정의 시 테스트 내부에서 `Application("test").ready()` 호출 필요
- 비동기 테스트는 `@pytest.mark.asyncio` 데코레이터 사용

### 서버 실행

```bash
uvicorn main:app.asgi --reload  # app = Application("name").scan(...).ready()
```

## 코드 패턴 및 컨벤션

### Container 시스템 확장 시

1. `bloom/core/container/element.py`의 `Element` 상속하여 메타데이터 정의
2. `bloom/core/container/base.py`의 `Container` 상속하여 새 컨테이너 타입 구현
3. 데코레이터에서 `XxxContainer.get_or_create(target)` 패턴 사용

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
│   ├── container/  # Container, Element, ComponentContainer, FactoryContainer, HandlerContainer
│   ├── manager.py  # ContainerManager (ContextVar 기반)
│   ├── lifecycle.py # PostConstruct/PreDestroy 처리
│   └── lazy.py     # Lazy[T] descriptor
├── web/            # ASGI 웹 레이어
│   ├── router.py   # URL 라우팅
│   ├── params/     # 파라미터 리졸버들
│   ├── middleware/ # 미들웨어 체인
│   ├── auth/       # 인증/인가
│   └── error/      # 에러 핸들링
```

## 주의사항

- `pydantic>=2.0` 필수 의존성 (BaseModel 파라미터 바인딩)
- Python 3.12+ 문법 사용 (Generic `[T]` 문법, `type[T]`)
- 비동기 핸들러 지원 (`async def` 메서드 자동 감지)
