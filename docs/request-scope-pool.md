# REQUEST 스코프와 커넥션 풀 패턴

REQUEST 스코프를 사용하여 HTTP 요청당 하나의 커넥션을 풀에서 획득하고, 요청 종료 시 자동으로 반환하는 패턴입니다.

## 개요

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              DbConnectionPool (SINGLETON)                │   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐              │   │
│  │  │conn1│ │conn2│ │conn3│ │conn4│ │conn5│ ...          │   │
│  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          ▲                                      │
│           ┌──────────────┴──────────────┐                      │
│           │                             │                      │
│  ┌────────┴─────────┐        ┌─────────┴────────┐             │
│  │   Request A      │        │    Request B      │             │
│  │ ┌──────────────┐ │        │ ┌──────────────┐  │             │
│  │ │ DbConnection │ │        │ │ DbConnection │  │             │
│  │ │  (REQUEST)   │ │        │ │  (REQUEST)   │  │             │
│  │ │   conn1 ─────┼─┼────────┼─┼─→ 다른 conn   │  │             │
│  │ └──────────────┘ │        │ └──────────────┘  │             │
│  └──────────────────┘        └───────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

## 기본 패턴

### 1. 커넥션 풀 (SINGLETON)

```python
from bloom import Component, PostConstruct, PreDestroy

@Component
class DbConnectionPool:
    """싱글톤 커넥션 풀 - 앱 전체에서 공유"""
    _pool: asyncpg.Pool | None = None

    @PostConstruct
    async def init_pool(self):
        self._pool = await asyncpg.create_pool(
            "postgresql://user:pass@localhost/db",
            min_size=5,
            max_size=20,
        )

    @PreDestroy
    async def close_pool(self):
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool
```

### 2. 요청별 커넥션 (REQUEST 스코프)

```python
from bloom import Component, Scope, PostConstruct, PreDestroy
from bloom.core import ScopeEnum

@Component
@Scope(ScopeEnum.REQUEST)
class DbConnection:
    """요청별 커넥션 - 요청 시작 시 획득, 종료 시 반환"""
    pool: DbConnectionPool
    _conn: asyncpg.Connection | None = None

    @PostConstruct
    def acquire(self):
        # 동기 버전: 풀에서 커넥션 획득
        self._conn = self.pool.pool.acquire()

    @PreDestroy
    def release(self):
        # 커넥션을 풀에 반환
        if self._conn:
            self.pool.pool.release(self._conn)
            self._conn = None

    @property
    def conn(self) -> asyncpg.Connection:
        return self._conn

    async def execute(self, query: str, *args):
        return await self._conn.execute(query, *args)

    async def fetchrow(self, query: str, *args):
        return await self._conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args):
        return await self._conn.fetch(query, *args)
```

### 3. 리포지토리에서 사용

```python
@Component
class UserRepository:
    db: DbConnection  # REQUEST 스코프 → 요청 내 같은 커넥션

    async def find_by_id(self, user_id: int) -> dict | None:
        return await self.db.fetchrow(
            "SELECT * FROM users WHERE id = $1", user_id
        )

    async def create(self, name: str, email: str) -> int:
        row = await self.db.fetchrow(
            "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id",
            name, email
        )
        return row["id"]


@Component
class OrderRepository:
    db: DbConnection  # 같은 요청 → UserRepository와 같은 커넥션!

    async def create(self, user_id: int, total: int) -> int:
        row = await self.db.fetchrow(
            "INSERT INTO orders (user_id, total) VALUES ($1, $2) RETURNING id",
            user_id, total
        )
        return row["id"]
```

## 트랜잭션 패턴

같은 요청 내 모든 리포지토리가 같은 커넥션을 공유하므로 트랜잭션이 자연스럽게 작동합니다:

```python
@Component
class OrderService:
    db: DbConnection
    user_repo: UserRepository
    order_repo: OrderRepository

    async def create_order_with_user(self, name: str, email: str, total: int) -> dict:
        # 모두 같은 커넥션 사용 → 트랜잭션 가능!
        await self.db.execute("BEGIN")
        try:
            user_id = await self.user_repo.create(name, email)
            order_id = await self.order_repo.create(user_id, total)
            await self.db.execute("COMMIT")
            return {"user_id": user_id, "order_id": order_id}
        except Exception as e:
            await self.db.execute("ROLLBACK")
            raise
```

## async @PostConstruct 지원

asyncpg 같은 라이브러리는 `await pool.acquire()`가 필요합니다. Bloom은 async `@PostConstruct`를 지원합니다:

```python
@Component
@Scope(ScopeEnum.REQUEST)
class AsyncDbConnection:
    pool: DbConnectionPool
    _conn: asyncpg.Connection | None = None

    @PostConstruct
    async def acquire(self):
        # async 획득 지원!
        self._conn = await self.pool.pool.acquire()

    @PreDestroy
    async def release(self):
        if self._conn:
            await self.pool.pool.release(self._conn)
            self._conn = None
```

### 동작 원리

1. 필드 접근 시 (`self.db.xxx`) → 인스턴스 생성 → async `@PostConstruct`가 pending 리스트에 등록
2. 미들웨어 체인 진입 전 → `run_pending_init()` 실행 → 모든 pending 초기화 완료
3. 미들웨어/핸들러에서 정상적으로 사용 가능
4. 요청 종료 시 → `end_request_async()` → async `@PreDestroy` 호출

## 미들웨어에서 사용

미들웨어에서도 REQUEST 스코프 인스턴스를 사용할 수 있습니다:

```python
from bloom.web.middleware import Middleware

@Component
class DbLoggingMiddleware(Middleware):
    db: DbConnection  # REQUEST 스코프

    async def process_request(self, request: HttpRequest) -> None:
        # 미들웨어에서도 커넥션 사용 가능!
        conn_id = id(self.db.conn)
        print(f"Request using connection: {conn_id}")
        return None
```

미들웨어와 핸들러가 같은 REQUEST 스코프이므로 **같은 커넥션**을 공유합니다.

## 테스트 방법

### 동기 테스트 (`with request_scope()`)

```python
from bloom.core import request_scope

async def test_connection_per_request(reset_container_manager):
    @Component
    class DbConnectionPool:
        # ... 풀 설정

    @Component
    @Scope(ScopeEnum.REQUEST)
    class DbConnection:
        # ... 동기 @PostConstruct 사용

    app = Application("test").ready()
    repo = app.manager.get_instance(UserRepository)

    # 첫 번째 요청
    with request_scope():
        user = repo.find_by_id(1)
        # @PostConstruct로 커넥션 획득
        # with 블록 종료 시 @PreDestroy로 반환

    # 두 번째 요청 - 새로운 커넥션
    with request_scope():
        user = repo.find_by_id(2)
```

### 비동기 테스트 (`async with request_scope()`)

```python
@pytest.mark.asyncio
async def test_async_connection(reset_container_manager):
    @Component
    @Scope(ScopeEnum.REQUEST)
    class AsyncDbConnection:
        @PostConstruct
        async def acquire(self):
            self._conn = await pool.acquire()

        @PreDestroy
        async def release(self):
            await pool.release(self._conn)

    app = Application("test").ready()
    service = app.manager.get_instance(Service)

    # async with로 async @PostConstruct/@PreDestroy 지원
    async with request_scope():
        result = await service.do_something()
```

### ASGI 통합 테스트

```python
from bloom.tests import TestClient

@pytest.mark.asyncio
async def test_http_request(reset_container_manager):
    # ... 컴포넌트 정의

    app = Application("test").ready()
    client = TestClient(app)

    # ASGI 앱이 자동으로 REQUEST 스코프 관리
    response = await client.get("/users/1")
    assert response.status_code == 200
    # 요청 종료 후 자동으로 커넥션 반환됨
```

## 실제 asyncpg 예제

```python
import asyncpg
from bloom import Application, Component, Scope, PostConstruct, PreDestroy
from bloom.core import ScopeEnum
from bloom.web import Controller, Get

@Component
class DatabasePool:
    _pool: asyncpg.Pool | None = None

    @PostConstruct
    async def init(self):
        self._pool = await asyncpg.create_pool(
            "postgresql://postgres:password@localhost/mydb",
            min_size=5,
            max_size=20,
        )

    @PreDestroy
    async def close(self):
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        return self._pool


@Component
@Scope(ScopeEnum.REQUEST)
class DbConnection:
    database: DatabasePool
    _conn: asyncpg.Connection | None = None

    @PostConstruct
    async def acquire(self):
        self._conn = await self.database.pool.acquire()

    @PreDestroy
    async def release(self):
        if self._conn:
            await self.database.pool.release(self._conn)

    async def fetch(self, query: str, *args):
        return await self._conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        return await self._conn.fetchrow(query, *args)

    async def execute(self, query: str, *args):
        return await self._conn.execute(query, *args)


@Component
class UserRepository:
    db: DbConnection

    async def get_all(self) -> list[dict]:
        rows = await self.db.fetch("SELECT * FROM users")
        return [dict(row) for row in rows]

    async def get_by_id(self, user_id: int) -> dict | None:
        row = await self.db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
        return dict(row) if row else None


@Controller
class UserController:
    user_repo: UserRepository

    @Get("/users")
    async def list_users(self) -> list[dict]:
        return await self.user_repo.get_all()

    @Get("/users/{user_id}")
    async def get_user(self, user_id: int) -> dict:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        return user


# 앱 시작
app = Application("myapp").scan(__name__).ready()

# uvicorn main:app.asgi --reload
```

## 주의사항

1. **풀은 SINGLETON**: `DbConnectionPool`은 반드시 SINGLETON(기본값)이어야 합니다. CALL이나 REQUEST로 하면 매번 새 풀이 생성됩니다.

2. **커넥션은 REQUEST**: `DbConnection`은 REQUEST 스코프로 요청당 하나만 생성됩니다.

3. **같은 요청 = 같은 커넥션**: 같은 요청 내 여러 리포지토리가 `DbConnection`을 주입받으면 모두 같은 인스턴스를 공유합니다.

4. **async @PostConstruct 타이밍**:

   - 필드 접근 시 인스턴스 생성 + pending 등록
   - 미들웨어 진입 전에 pending 실행
   - 따라서 미들웨어에서도 완전히 초기화된 커넥션 사용 가능

5. **예외 발생 시에도 정리**: `@PreDestroy`는 예외가 발생해도 호출됩니다 (finally 블록처럼).

## 멀티 워커 환경

uvicorn을 여러 워커로 실행하면 각 워커가 독립적인 풀을 가집니다:

```bash
uvicorn main:app.asgi --workers 4
```

```
Worker 1: DbConnectionPool (20 connections)
Worker 2: DbConnectionPool (20 connections)
Worker 3: DbConnectionPool (20 connections)
Worker 4: DbConnectionPool (20 connections)
= 총 80 connections
```

풀 크기를 설정할 때 워커 수를 고려하세요.
