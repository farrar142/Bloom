# Bloom BloomTestCase - pytest 기반 테스트 케이스

Bloom의 `BloomTestCase`는 pytest 기반의 클래스형 테스트를 지원합니다.
unittest.TestCase를 상속하지 않고 순수 pytest 스타일로 동작합니다.

## 기본 사용법

```python
from bloom import Component
from bloom.tests import BloomTestCase

@Component
class UserRepository:
    def get_users(self) -> list[str]:
        return ["alice", "bob"]

@Component
class UserService:
    repository: UserRepository  # 자동 주입

    def list_users(self) -> list[str]:
        return self.repository.get_users()

class TestUserService(BloomTestCase):
    # 테스트에 필요한 컴포넌트 등록
    components = [UserRepository, UserService]

    async def test_list_users(self):
        service = self.get_instance(UserService)
        users = service.list_users()
        assert users == ["alice", "bob"]
```

## 클래스 속성

| 속성         | 타입             | 기본값   | 설명                   |
| ------------ | ---------------- | -------- | ---------------------- |
| `app_name`   | `str`            | `"test"` | Application 이름       |
| `components` | `list[type]`     | `[]`     | 스캔할 컴포넌트 리스트 |
| `config`     | `dict[str, Any]` | `None`   | 설정 딕셔너리          |

```python
class TestWithConfig(BloomTestCase):
    app_name = "my_app"
    components = [MyService, MyRepository]
    config = {
        "database": {"host": "localhost", "port": 5432},
        "debug": True,
    }
```

## 인스턴스 속성

| 속성      | 타입               | 설명                       |
| --------- | ------------------ | -------------------------- |
| `app`     | `Application`      | Bloom Application 인스턴스 |
| `manager` | `ContainerManager` | DI 컨테이너 매니저         |
| `client`  | `BloomTestClient`  | HTTP 테스트 클라이언트     |

## DI Container 메서드

### `get_instance(type_) -> T`

등록된 컴포넌트의 인스턴스를 조회합니다.

```python
async def test_get_instance(self):
    service = self.get_instance(UserService)
    assert service is not None
```

### `get_instances(type_) -> list[T]`

해당 타입의 모든 인스턴스를 조회합니다 (서브클래스 포함).

```python
async def test_get_all_handlers(self):
    handlers = self.get_instances(EventHandler)
    assert len(handlers) == 3
```

### `has_instance(type_) -> bool`

인스턴스 존재 여부를 확인합니다.

```python
async def test_instance_exists(self):
    assert self.has_instance(UserService)
    assert not self.has_instance(UnregisteredService)
```

## HTTP 테스트 메서드

`BloomTestCase`는 비동기 HTTP 메서드를 제공합니다.

### `get(path, **kwargs) -> AssertableResponse`

```python
async def test_get_users(self):
    response = await self.get("/api/users")
    response.assert_ok()
    response.assert_json(["alice", "bob"])
```

### `post(path, **kwargs) -> AssertableResponse`

```python
async def test_create_user(self):
    response = await self.post("/api/users", json={"name": "charlie"})
    response.assert_status(201)
    response.assert_json_contains({"name": "charlie"})
```

### `put(path, **kwargs) -> AssertableResponse`

```python
async def test_update_user(self):
    response = await self.put("/api/users/1", json={"name": "updated"})
    response.assert_ok()
```

### `patch(path, **kwargs) -> AssertableResponse`

```python
async def test_patch_user(self):
    response = await self.patch("/api/users/1", json={"name": "patched"})
    response.assert_ok()
```

### `delete(path, **kwargs) -> AssertableResponse`

```python
async def test_delete_user(self):
    response = await self.delete("/api/users/1")
    response.assert_status(204)
```

### `client` 속성

더 세밀한 제어가 필요한 경우 `client` 속성을 직접 사용할 수 있습니다.

```python
async def test_custom_headers(self):
    response = await self.client.get(
        "/api/protected",
        headers={"Authorization": "Bearer token123"}
    )
    response.assert_ok()
```

## Mock / Override 메서드

### `override(type_, instance) -> ContextManager`

의존성을 임시로 오버라이드합니다.

```python
async def test_with_mock(self):
    class FakeRepository:
        def get_users(self):
            return ["fake_user"]
    
    with self.override(UserRepository, FakeRepository()):
        service = self.get_instance(UserService)
        users = service.list_users()
        assert users == ["fake_user"]
```

### `override_factory(type_, factory) -> ContextManager`

팩토리를 사용하여 의존성을 오버라이드합니다.

```python
async def test_with_factory(self):
    with self.override_factory(UserRepository, lambda: FakeRepository()):
        repo = self.get_instance(UserRepository)
        assert isinstance(repo, FakeRepository)
```

## Assertion 헬퍼

### `assert_instance(obj, type_) -> T`

타입 검증 후 객체를 반환합니다.

```python
async def test_type_check(self):
    service = self.get_instance(UserService)
    typed_service = self.assert_instance(service, UserService)
    # typed_service는 타입 힌트가 적용됨
```

### `assert_injected(obj, field, type_=None) -> T`

필드가 주입되었는지 검증합니다.

```python
async def test_injection(self):
    service = self.get_instance(UserService)
    repo = self.assert_injected(service, "repository", UserRepository)
    assert repo is not None
```

### `assert_container_exists(type_) -> None`

컨테이너가 등록되었는지 검증합니다.

```python
async def test_container(self):
    self.assert_container_exists(UserService)
```

## AssertableResponse 체이닝

HTTP 응답에 대한 assertion을 체이닝할 수 있습니다.

```python
async def test_chained_assertions(self):
    (await self.get("/api/users"))
        .assert_ok()
        .assert_content_type("application/json")
        .assert_json(["alice", "bob"])
```

### 주요 AssertableResponse 메서드

| 메서드                           | 설명                                                   |
| -------------------------------- | ------------------------------------------------------ |
| `assert_ok()`                    | 상태 코드가 200인지 검증                               |
| `assert_status(code)`            | 상태 코드 검증                                         |
| `assert_json(expected)`          | JSON 응답 검증                                         |
| `assert_json_contains(subset)`   | JSON 응답이 subset을 포함하는지 검증                   |
| `assert_json_path(path, value)`  | JSON 경로의 값 검증 (예: `"data.users[0].name"`)       |
| `assert_content_type(type_)`     | Content-Type 검증                                      |
| `assert_header(key, value)`      | 헤더 값 검증                                           |
| `assert_header_exists(key)`      | 헤더 존재 여부 검증                                    |
| `assert_text_contains(text)`     | 응답 텍스트가 특정 문자열을 포함하는지 검증            |

## 테스트 격리

각 테스트 메서드는 독립적인 `Application` 인스턴스에서 실행됩니다.

```python
class TestIsolation(BloomTestCase):
    components = [Counter]
    
    async def test_a(self):
        counter = self.get_instance(Counter)
        counter.increment()
        assert counter.value == 1
    
    async def test_b(self):
        # test_a와 완전히 독립
        counter = self.get_instance(Counter)
        assert counter.value == 0  # 0부터 시작
```

## 전체 예제

```python
from bloom import Component
from bloom.tests import BloomTestCase
from bloom.web import Controller, RequestMapping, Get, Post

@Component
class UserRepository:
    def __init__(self):
        self._users = ["alice", "bob"]
    
    def get_all(self) -> list[str]:
        return self._users
    
    def add(self, name: str) -> None:
        self._users.append(name)

@Component
class UserService:
    repository: UserRepository
    
    def list_users(self) -> list[str]:
        return self.repository.get_all()
    
    def create_user(self, name: str) -> str:
        self.repository.add(name)
        return name

@Controller
@RequestMapping("/api/users")
class UserController:
    service: UserService
    
    @Get("/")
    def list_users(self) -> list[str]:
        return self.service.list_users()
    
    @Post("/")
    def create_user(self, name: str) -> dict:
        created = self.service.create_user(name)
        return {"name": created}


class TestUserAPI(BloomTestCase):
    components = [UserRepository, UserService, UserController]
    
    async def test_list_users(self):
        """사용자 목록 조회"""
        response = await self.get("/api/users/")
        response.assert_ok()
        response.assert_json(["alice", "bob"])
    
    async def test_create_user(self):
        """사용자 생성"""
        response = await self.post("/api/users/", json={"name": "charlie"})
        response.assert_ok()
        response.assert_json_contains({"name": "charlie"})
    
    async def test_with_mock_repository(self):
        """Mock Repository로 테스트"""
        class FakeRepository:
            def get_all(self) -> list[str]:
                return ["fake_user"]
            def add(self, name: str) -> None:
                pass
        
        with self.override(UserRepository, FakeRepository()):
            response = await self.get("/api/users/")
            response.assert_json(["fake_user"])
```

## pytest 함수형 스타일과의 비교

### 클래스형 (BloomTestCase)

```python
class TestUserService(BloomTestCase):
    components = [UserService]
    
    async def test_get_users(self):
        service = self.get_instance(UserService)
        assert service.get_users() == ["alice", "bob"]
```

### 함수형 (fixtures)

```python
import pytest
from bloom.tests import BloomTestClient

@pytest.fixture
async def app():
    from bloom import Application
    app = Application("test")
    app.scan(UserService)
    await app.ready_async()
    yield app
    await app.shutdown_async()

async def test_get_users(app):
    async with BloomTestClient(app) as client:
        response = await client.get("/api/users")
        response.assert_ok()
```

클래스형은 fixture 설정이 간편하고, 관련 테스트를 그룹화하기 좋습니다.
