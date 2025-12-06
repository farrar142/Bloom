# BloomTestCase 테스팅 모듈

`bloom.testing` 모듈은 Bloom 프레임워크 애플리케이션을 테스트하기 위한 유틸리티를 제공합니다.

## 설치

```python
from bloom.testing import (
    BloomTestCase,
    MockBean,
    TestClient,
    MockSTOMP,
    fixture,
)
```

## 주요 컴포넌트

### BloomTestCase

테스트 케이스의 기본 클래스입니다. DI 컨테이너 초기화, MockBean 자동 설정, 픽스처 관리 등을 자동으로 처리합니다.

```python
from bloom.testing import BloomTestCase, MockBean
from bloom.core import Service

@Service
class UserService:
    def get_user(self, id: int) -> dict:
        return {"id": id, "name": f"User {id}"}

class MyTest(BloomTestCase):
    async def setUp(self):
        # 테스트 전 설정
        pass

    async def tearDown(self):
        # 테스트 후 정리
        pass

    async def test_user_service(self):
        service = await self.get_instance(UserService)
        user = service.get_user(1)
        assert user["id"] == 1

# 테스트 실행
test = MyTest()
await test._run_test("test_user_service")
```

### MockBean

서비스를 Mock으로 대체합니다. 테스트 클래스의 필드 타입 힌트로 선언하면 자동으로 Mock이 생성되고 DI 컨테이너에 등록됩니다.

```python
from bloom.testing import BloomTestCase, MockBean
from bloom.core import Service, Repository

@Repository
class UserRepository:
    def find_by_id(self, id: int) -> dict | None:
        # 실제 DB 조회
        return None

@Service
class UserService:
    repo: UserRepository

    def get_user(self, id: int) -> dict:
        user = self.repo.find_by_id(id)
        if not user:
            raise ValueError("User not found")
        return user

class UserServiceTest(BloomTestCase):
    repo: MockBean[UserRepository]  # Mock 자동 생성

    async def setUp(self):
        # Mock 설정
        self.repo.find_by_id.return_value = {"id": 1, "name": "Test User"}

    async def test_get_user(self):
        service = await self.get_instance(UserService)
        user = service.get_user(1)

        assert user["name"] == "Test User"
        self.repo.find_by_id.assert_called_once_with(1)
```

### TestClient

ASGI 애플리케이션을 직접 호출하여 HTTP 요청을 테스트합니다.

```python
from bloom.testing import BloomTestCase
from bloom.web import ASGIApplication, JSONResponse

app = ASGIApplication()

@app.get("/api/users/{user_id}")
async def get_user(request):
    user_id = request.path_params.get("user_id")
    return JSONResponse({"id": int(user_id), "name": f"User {user_id}"})

class APITest(BloomTestCase):
    async def test_get_user(self):
        async with self.test_client(app) as client:
            # GET 요청
            response = await client.get("/api/users/1")
            assert response.status_code == 200

            data = response.json()
            assert data["id"] == 1

    async def test_create_user(self):
        async with self.test_client(app) as client:
            # POST 요청 with JSON body
            response = await client.post(
                "/api/users",
                json={"name": "New User"},
            )
            assert response.status_code == 201

    async def test_with_headers(self):
        async with self.test_client(app) as client:
            # 헤더 포함 요청
            response = await client.get(
                "/api/protected",
                headers={"Authorization": "Bearer token123"},
            )

    async def test_with_query_params(self):
        async with self.test_client(app) as client:
            # 쿼리 파라미터
            response = await client.get(
                "/api/search",
                params={"q": "test", "page": "2"},
            )
```

#### TestClient HTTP 메서드

- `get(path, *, headers=None, params=None)` - GET 요청
- `post(path, *, headers=None, json=None, data=None)` - POST 요청
- `put(path, *, headers=None, json=None, data=None)` - PUT 요청
- `patch(path, *, headers=None, json=None, data=None)` - PATCH 요청
- `delete(path, *, headers=None)` - DELETE 요청

#### TestResponse

HTTP 응답을 감싸는 래퍼 클래스입니다.

```python
response = await client.get("/api/users")

# 상태 코드
assert response.status_code == 200

# 응답 본문
text = response.text  # 텍스트
data = response.json()  # JSON
content = response.content  # bytes

# 헤더
content_type = response.headers.get("content-type")

# 4xx/5xx 응답에서 예외 발생
response.raise_for_status()
```

### MockSTOMP

STOMP 프로토콜 Mock 클라이언트입니다. 실제 메시지 브로커 없이 STOMP 통신을 테스트할 수 있습니다.

```python
from bloom.testing import MockSTOMP

stomp = MockSTOMP()
await stomp.connect()

# 구독
received = []
await stomp.subscribe("/topic/test", lambda msg: received.append(msg))

# 메시지 시뮬레이션
stomp.simulate_message("/topic/test", {"data": "hello"})
assert len(received) == 1

# 메시지 전송
await stomp.send("/app/test", {"action": "ping"})

# 전송 확인
stomp.assert_sent("/app/test", {"action": "ping"})
```

BloomTestCase와 함께 사용:

```python
class STOMPTest(BloomTestCase):
    async def test_stomp_messaging(self):
        async with self.stomp_client("ws://localhost:8080/stomp") as stomp:
            received = []
            await stomp.subscribe("/topic/test", lambda msg: received.append(msg))

            stomp.simulate_message("/topic/test", {"data": "hello"})
            assert len(received) == 1
```

### fixture 데코레이터

pytest 스타일의 픽스처를 정의합니다.

```python
from bloom.testing import BloomTestCase, fixture

class FixtureTest(BloomTestCase):
    @fixture
    async def sample_user(self):
        return {"id": 1, "name": "Test User"}

    @fixture(autouse=True)
    async def setup_db(self):
        # 테스트 전 실행
        await self.db.connect()
        yield  # 테스트 실행
        # 테스트 후 실행
        await self.db.disconnect()

    async def test_with_fixture(self, sample_user):
        # sample_user 픽스처 자동 주입
        assert sample_user["name"] == "Test User"
```

## 통합 테스트 예제

MockBean과 TestClient를 함께 사용하는 통합 테스트:

```python
from bloom.testing import BloomTestCase, MockBean
from bloom.web import ASGIApplication, JSONResponse
from bloom.core import Service, Repository

@Repository
class UserRepository:
    def find_all(self) -> list[dict]:
        # 실제 DB 조회
        return []

@Service
class UserService:
    repo: UserRepository

    def get_users(self) -> list[dict]:
        return self.repo.find_all()

app = ASGIApplication()

@app.get("/api/users")
async def list_users(request):
    from bloom.core import get_container_manager
    manager = get_container_manager()
    service = await manager.get_instance_async(UserService)
    return JSONResponse(service.get_users())

class IntegrationTest(BloomTestCase):
    repo: MockBean[UserRepository]

    async def test_full_flow(self):
        # Mock 설정
        self.repo.find_all.return_value = [
            {"id": 1, "name": "User 1"},
            {"id": 2, "name": "User 2"},
        ]

        # HTTP 요청
        async with self.test_client(app) as client:
            response = await client.get("/api/users")
            assert response.status_code == 200

            users = response.json()
            assert len(users) == 2

        # Mock 호출 확인
        self.repo.find_all.assert_called_once()
```

## pytest 통합

pytest와 함께 사용할 때는 `@pytest.mark.asyncio` 데코레이터를 사용합니다:

```python
import pytest
from bloom.testing import BloomTestCase, MockBean

class TestUserAPI:
    @pytest.mark.asyncio
    async def test_get_users(self):
        class MyTest(BloomTestCase):
            repo: MockBean[UserRepository]

            async def test_users(self):
                self.repo.find_all.return_value = [{"id": 1}]
                # ...

        test = MyTest()
        await test._run_test("test_users")
```

## API 참조

### BloomTestCase

| 메서드              | 설명                             |
| ------------------- | -------------------------------- |
| `setUp()`           | 테스트 전 실행 (오버라이드 가능) |
| `tearDown()`        | 테스트 후 실행 (오버라이드 가능) |
| `get_instance(cls)` | DI 컨테이너에서 인스턴스 획득    |
| `test_client(app)`  | HTTP TestClient 컨텍스트 매니저  |
| `stomp_client(url)` | STOMP 클라이언트 컨텍스트 매니저 |

### MockBean[T]

테스트 클래스의 필드 타입 힌트로 선언하면 `unittest.mock.MagicMock` 인스턴스가 자동 생성됩니다.

### TestClient

| 메서드                                | 설명        |
| ------------------------------------- | ----------- |
| `get(path, *, headers, params)`       | GET 요청    |
| `post(path, *, headers, json, data)`  | POST 요청   |
| `put(path, *, headers, json, data)`   | PUT 요청    |
| `patch(path, *, headers, json, data)` | PATCH 요청  |
| `delete(path, *, headers)`            | DELETE 요청 |

### MockSTOMP

| 메서드                                | 설명                   |
| ------------------------------------- | ---------------------- |
| `connect(headers)`                    | STOMP 연결             |
| `disconnect()`                        | 연결 해제              |
| `subscribe(destination, callback)`    | 대상 구독              |
| `send(destination, body)`             | 메시지 전송            |
| `simulate_message(destination, body)` | 메시지 수신 시뮬레이션 |
| `assert_sent(destination, body)`      | 전송 확인              |
