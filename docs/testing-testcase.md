# Bloom TestCase - Django 스타일 테스트 케이스

Bloom의 `TestCase`는 Django의 `TestCase`처럼 모든 테스트 기능을 하나의 클래스에 통합하여 제공합니다.

## 기본 사용법

```python
from bloom import Component
from bloom.tests import TestCase

@Component
class UserRepository:
    def get_users(self) -> list[str]:
        return ["alice", "bob"]

@Component
class UserService:
    repository: UserRepository  # 자동 주입

    def list_users(self) -> list[str]:
        return self.repository.get_users()

class TestUserService(TestCase):
    # 테스트에 필요한 컴포넌트 등록
    components = [UserRepository, UserService]

    def test_list_users(self):
        service = self.get_instance(UserService)
        users = service.list_users()
        self.assertEqual(users, ["alice", "bob"])
```

## 클래스 속성

| 속성         | 타입         | 기본값   | 설명                                   |
| ------------ | ------------ | -------- | -------------------------------------- |
| `app_name`   | `str`        | `"test"` | Application 이름                       |
| `components` | `list[type]` | `[]`     | 스캔할 컴포넌트 리스트                 |
| `config`     | `dict`       | `None`   | 설정 딕셔너리                          |
| `auto_ready` | `bool`       | `True`   | setUp에서 자동으로 `ready()` 호출 여부 |

```python
class TestWithConfig(TestCase):
    app_name = "my_app"
    components = [MyService, MyRepository]
    config = {
        "database": {"host": "localhost", "port": 5432},
        "debug": True,
    }
    auto_ready = True  # 기본값
```

## 인스턴스 속성

| 속성      | 타입               | 설명                       |
| --------- | ------------------ | -------------------------- |
| `app`     | `Application`      | Bloom Application 인스턴스 |
| `manager` | `ContainerManager` | DI 컨테이너 매니저         |
| `client`  | `TestClient`       | HTTP 테스트 클라이언트     |

## DI Container 메서드

### `get_instance(target_type) -> T`

등록된 컴포넌트의 인스턴스를 조회합니다.

```python
def test_get_instance(self):
    service = self.get_instance(UserService)
    self.assertIsNotNone(service)
```

### `get_instances(target_type) -> list[T]`

해당 타입의 모든 인스턴스를 조회합니다 (서브클래스 포함).

```python
def test_get_all_handlers(self):
    handlers = self.get_instances(EventHandler)
    self.assertEqual(len(handlers), 3)
```

### `has_instance(target_type) -> bool`

인스턴스 존재 여부를 확인합니다.

```python
def test_instance_exists(self):
    self.assertTrue(self.has_instance(UserService))
    self.assertFalse(self.has_instance(UnregisteredService))
```

## HTTP 테스트 메서드

`TestCase`는 동기 HTTP 메서드를 제공합니다. 내부적으로 비동기를 동기로 래핑합니다.

### `get(path, *, headers=None, query_params=None) -> TestResponse`

```python
def test_get_users(self):
    response = self.get("/api/users")
    self.assert_success(response)
    self.assertEqual(response.json(), ["alice", "bob"])
```

### `post(path, *, json=None, body=None, headers=None) -> TestResponse`

```python
def test_create_user(self):
    response = self.post("/api/users", json={"name": "charlie"})
    self.assert_status(response, 201)
```

### `put(path, *, json=None, body=None, headers=None) -> TestResponse`

```python
def test_update_user(self):
    response = self.put("/api/users/1", json={"name": "updated"})
    self.assert_success(response)
```

### `delete(path, *, headers=None) -> TestResponse`

```python
def test_delete_user(self):
    response = self.delete("/api/users/1")
    self.assert_status(response, 204)
```

### `patch(path, *, json=None, body=None, headers=None) -> TestResponse`

```python
def test_patch_user(self):
    response = self.patch("/api/users/1", json={"status": "active"})
    self.assert_success(response)
```

## Mock 메서드

### `override(target_type, instance) -> ContextManager`

의존성을 mock 인스턴스로 대체합니다.

```python
def test_with_mock(self):
    class FakeRepository:
        def get_users(self):
            return ["fake_user"]

    with self.override(UserRepository, FakeRepository()):
        service = self.get_instance(UserService)
        # 이제 service.repository는 FakeRepository
        users = service.list_users()
        self.assertEqual(users, ["fake_user"])

    # with 블록 종료 후 원래 인스턴스 복원
```

### `override_factory(target_type, factory) -> ContextManager`

팩토리 함수로 mock을 생성합니다. 호출 시마다 새 인스턴스가 생성됩니다.

```python
def test_with_factory_mock(self):
    call_count = 0

    def create_fake():
        nonlocal call_count
        call_count += 1
        return FakeRepository()

    with self.override_factory(UserRepository, create_fake):
        # 팩토리가 호출됨
        pass
```

## Assertion 메서드

### 타입 검증

```python
def test_type_assertion(self):
    service = self.get_instance(UserService)
    self.assert_instance_of(service, UserService)
```

### 필드 주입 검증

```python
def test_injection(self):
    service = self.get_instance(UserService)

    # 필드가 주입되었는지 확인하고, 주입된 값 반환
    repo = self.assert_injected(service, "repository", UserRepository)
    self.assertIsNotNone(repo)
```

### HTTP 응답 검증

```python
def test_response_assertions(self):
    response = self.get("/api/users")

    # 상태 코드 검증
    self.assert_status(response, 200)
    self.assert_success(response)      # 2xx
    self.assert_not_found(response)    # 404
    self.assert_bad_request(response)  # 400
    self.assert_unauthorized(response) # 401
    self.assert_forbidden(response)    # 403

    # JSON 검증
    self.assert_json_equal(response, {"users": ["alice", "bob"]})
```

## 유틸리티 메서드

### `run_async(coro) -> Any`

코루틴을 동기적으로 실행합니다.

```python
def test_async_code(self):
    async def fetch_data():
        return {"data": "value"}

    result = self.run_async(fetch_data())
    self.assertEqual(result, {"data": "value"})
```

### `print_container_tree() -> str`

디버깅용 컨테이너 트리를 문자열로 반환합니다.

```python
def test_debug(self):
    tree = self.print_container_tree()
    print(tree)
    # ContainerManager: test
    # ========================================
    # Containers:
    #   UserRepository: 1 container(s)
    #   UserService: 1 container(s)
    # Instances:
    #   UserRepository: 1 instance(s)
    #   UserService: 1 instance(s)
```

### `get_container_info(target) -> dict`

특정 타입의 컨테이너 정보를 조회합니다.

```python
def test_container_info(self):
    info = self.get_container_info(UserService)
    self.assertTrue(info["exists"])
    self.assertEqual(info["target"], "UserService")
```

## AsyncTestCase

비동기 테스트가 필요한 경우 `AsyncTestCase`를 사용합니다.

```python
import pytest
from bloom.tests import AsyncTestCase

class TestAsyncService(AsyncTestCase):
    components = [AsyncUserService]

    @pytest.mark.asyncio
    async def test_async_method(self):
        service = self.get_instance(AsyncUserService)
        result = await service.fetch_users()
        self.assertEqual(result, ["alice", "bob"])

    @pytest.mark.asyncio
    async def test_async_http(self):
        # 비동기 HTTP 메서드 사용
        response = await self.async_get("/api/users")
        self.assert_success(response)
```

### 비동기 HTTP 메서드

| 메서드           | 설명               |
| ---------------- | ------------------ |
| `async_get()`    | 비동기 GET 요청    |
| `async_post()`   | 비동기 POST 요청   |
| `async_put()`    | 비동기 PUT 요청    |
| `async_delete()` | 비동기 DELETE 요청 |
| `async_patch()`  | 비동기 PATCH 요청  |

## 전체 예제

```python
from dataclasses import dataclass
from bloom import Component
from bloom.web import Controller, Get, Post
from bloom.web.params.types import RequestBody
from bloom.tests import TestCase

# === 컴포넌트 정의 ===

@dataclass
class CreateUserRequest:
    name: str
    email: str

@Component
class UserRepository:
    _users: list[dict] = None

    def __post_init__(self):
        self._users = []

    def create(self, name: str, email: str) -> dict:
        user = {"id": len(self._users) + 1, "name": name, "email": email}
        self._users.append(user)
        return user

    def find_all(self) -> list[dict]:
        return self._users

@Component
class UserService:
    repository: UserRepository

    def create_user(self, name: str, email: str) -> dict:
        return self.repository.create(name, email)

    def get_users(self) -> list[dict]:
        return self.repository.find_all()

@Controller
class UserController:
    service: UserService

    @Get("/users")
    def list_users(self) -> list[dict]:
        return self.service.get_users()

    @Post("/users")
    def create_user(self, body: RequestBody[CreateUserRequest]) -> dict:
        return self.service.create_user(body.name, body.email)

# === 테스트 ===

class TestUserController(TestCase):
    components = [UserRepository, UserService, UserController]

    def test_list_users_empty(self):
        """빈 사용자 목록 조회"""
        response = self.get("/users")
        self.assert_success(response)
        self.assert_json_equal(response, [])

    def test_create_and_list_user(self):
        """사용자 생성 및 조회"""
        # 사용자 생성
        response = self.post("/users", json={
            "name": "Alice",
            "email": "alice@example.com"
        })
        self.assert_success(response)
        user = response.json()
        self.assertEqual(user["name"], "Alice")

        # 목록 조회
        response = self.get("/users")
        users = response.json()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["email"], "alice@example.com")

    def test_with_mock_repository(self):
        """Repository를 Mock으로 대체"""
        class MockRepository:
            def find_all(self):
                return [{"id": 999, "name": "Mock User"}]

        with self.override(UserRepository, MockRepository()):
            response = self.get("/users")
            users = response.json()
            self.assertEqual(users[0]["id"], 999)

    def test_service_injection(self):
        """서비스 주입 확인"""
        controller = self.get_instance(UserController)
        service = self.assert_injected(controller, "service", UserService)
        repo = self.assert_injected(service, "repository", UserRepository)
        self.assertIsNotNone(repo)
```

## TestCase vs 일반 pytest

### TestCase 사용 (권장)

```python
class TestUserService(TestCase):
    components = [UserRepository, UserService]

    def test_create_user(self):
        service = self.get_instance(UserService)
        # 모든 기능이 self에서 접근 가능
        self.assert_instance_of(service, UserService)
```

### 일반 pytest 사용

```python
def test_create_user(reset_container_manager):
    app = create_test_app("test", UserRepository, UserService)
    service = app.manager.get_instance(UserService)
    assert isinstance(service, UserService)
```

`TestCase`는 보일러플레이트를 줄이고, Django 스타일의 일관된 테스트 패턴을 제공합니다.
