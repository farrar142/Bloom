# Vessel - Python DI Container Framework

## Architecture Overview

Vessel은 Spring-style 의존성 주입 컨테이너로, 데코레이터 기반으로 컴포넌트를 등록하고 자동 의존성 해결을 제공합니다.

### Core Components

- **Application** (`vessel/application.py`): 최상위 진입점. `scan().ready()` 체이닝으로 초기화
- **Container** (`vessel/core/container/`): 클래스 메타데이터와 의존성 정보 관리
- **ContainerManager** (`vessel/core/manager.py`): 전역 레지스트리 (컨테이너/인스턴스)
- **Web Layer** (`vessel/web/`): ASGI, Router, Controller, HttpMethodHandler

### Container Types

| 타입                  | 용도                   | 데코레이터         |
| --------------------- | ---------------------- | ------------------ |
| `ComponentContainer`  | 클래스 등록            | `@Component`       |
| `FactoryContainer`    | 메서드로 인스턴스 생성 | `@Factory`         |
| `HandlerContainer`    | 라우터/예외 핸들러     | `@Handler(key)`    |
| `ControllerContainer` | 웹 컨트롤러            | `@Controller`      |
| `HttpMethodHandler`   | HTTP 메서드 핸들러     | `@Get`, `@Post` 등 |

## Key Patterns

### 1. Application 초기화

```python
from vessel import Application, Component, Controller, Get

# 스캔(scan)으로 컴포넌트를 수집하고 ready()로 애플리케이션을 초기화합니다.
# ready()는 1) 컨테이너 토폴로지컬 초기화, 2) 라우터에 핸들러 등록을 자동으로 수행합니다.
app = Application("my_app").scan(MyModule).ready()

# ASGI 서버로 실행 (uvicorn main:app.asgi)
```

추가로 `app.router`와 `app.asgi` 속성을 통해 라우터 및 ASGI 애플리케이션에 접근할 수 있습니다:

```python
# 초기화 후 라우트 확인
routes = app.router.get_routes()

# uvicorn으로 실행시 사용되는 ASGI 객체
# uvicorn main:app.asgi
```

### 2. 컴포넌트 정의

```python
@Component
class Repository:
    pass

@Component
class Service:
    repository: Repository  # 필드 주입 - 클래스 어노테이션 사용
```

### 3. Factory 패턴 (외부 클래스 주입)

```python
@Component
class Config:
    @Factory
    def create_external(self, repo: Repository) -> ExternalService:
        return ExternalService(repo)  # 리턴 타입으로 등록됨
```

### 4. 웹 컨트롤러 (async 지원)

```python
@Controller
@RequestMapping("/api")
class UserController:
    service: UserService  # 의존성 주입

    @Get("/users")
    async def list_users(self) -> list[dict]:
        return await self.service.get_all()

    @Post("/users")
    async def create_user(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse.created({"id": 1})

    @Get("/users/{id}")
    async def get_user(self, id: str) -> dict:
        return {"id": id}
```

### 5. Handler 패턴

```python
@Component
class Controller:
    @Handler(("GET", "/users"))  # 라우트 키
    def get_users(self) -> list: ...

    @Handler(ValueError)  # 예외 타입 키
    def handle_error(self, e: ValueError) -> str: ...
```

## Web Layer (`vessel/web/`)

### 비동기 흐름

```
ASGI Server (uvicorn)
    ↓ await
ASGIApplication.__call__()
    ↓ await
Router.dispatch()
    ↓ await
HttpMethodHandler.__call__()
    ↓ await (async) / call (sync)
실제 핸들러 메서드
```

### HTTP 데코레이터

- `@Get`, `@Post`, `@Put`, `@Patch`, `@Delete`
- 사용법: `@Get`, `@Get("/path")`, `@Get(path="/path")`

### HttpRequest / HttpResponse

```python
# Request
request.method, request.path, request.headers
request.query_params, request.body, request.json

# Response
HttpResponse.ok(body)
HttpResponse.created(body)
HttpResponse.not_found(message)
HttpResponse.bad_request(message)
```

## Testing

```bash
pytest                    # 전체 테스트
pytest tests/test_web.py -v  # 웹 테스트
```

### Test Structure

- `tests/conftest.py`: 공통 fixture 및 `@Module` 데코레이터
- `reset_container_manager` fixture가 자동으로 레지스트리 초기화
- 비동기 테스트: `@pytest.mark.asyncio`

### 테스트 작성 예시

```python
@pytest.mark.asyncio
async def test_router_dispatch(self):
    class M:
        pass

    @Module(M)
    @Component
    class TestController:
        @Get("/ping")
        async def ping(self) -> str:
            return "pong"

    app = Application("test").scan(M).ready()

    request = HttpRequest(method="GET", path="/ping")
    response = await app.router.dispatch(request)
    assert response.body == "pong"
```

## Development Conventions

1. **타입 힌트 필수**: 의존성 주입은 `__annotations__` 기반
2. **Container 접근**: `cls.__container__` 또는 `method.__container__`
3. **Qualifier**: `@Qualifier("name")`으로 동일 타입 다중 인스턴스 구분
4. **한글 docstring**: 프로젝트 전체에서 한글 문서화
5. **비동기 우선**: 웹 핸들러는 async 권장 (sync도 지원)

## File Responsibilities

| 파일                        | 역할                                         |
| --------------------------- | -------------------------------------------- |
| `vessel/application.py`     | 최상위 Application 클래스                    |
| `vessel/__init__.py`        | 주요 API export                              |
| `vessel/core/decorators.py` | `@Component`, `@Factory`, `@Handler`         |
| `vessel/core/manager.py`    | 전역 상태 관리, 인스턴스 조회                |
| `vessel/core/utils.py`      | 토폴로지컬 정렬 (순환 의존성 감지)           |
| `vessel/core/container/`    | Container 구현체들                           |
| `vessel/web/asgi.py`        | ASGI 애플리케이션                            |
| `vessel/web/router.py`      | HTTP 라우팅                                  |
| `vessel/web/controller.py`  | `@Controller`, `@RequestMapping`             |
| `vessel/web/handler.py`     | `@Get`, `@Post`, `@Put`, `@Patch`, `@Delete` |
| `vessel/web/http.py`        | `HttpRequest`, `HttpResponse`                |
