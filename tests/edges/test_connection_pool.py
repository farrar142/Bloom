"""DB 커넥션 풀 + REQUEST 스코프 테스트

MockDbConnectionPool을 사용하여 실제 DB 없이 
REQUEST 스코프 커넥션 관리 패턴을 테스트합니다.

패턴: REQUEST 스코프 인스턴스 + SINGLETON 풀
- DbConnectionPool (SINGLETON): 앱 전체에서 공유
- DbConnection (REQUEST): 요청마다 풀에서 획득/반환
"""

import pytest
from dataclasses import dataclass, field
from typing import Any

from bloom import Application, Component, Scope, PostConstruct, PreDestroy
from bloom.core import ScopeEnum, request_scope


# =============================================================================
# Mock DB 커넥션 및 풀
# =============================================================================
@dataclass
class MockConnection:
    """Mock DB 커넥션"""

    id: int
    pool: "MockDbConnectionPool"
    is_released: bool = False
    queries: list[str] = field(default_factory=list)

    def fetchrow(self, query: str, *args) -> dict[str, Any]:
        """동기 fetchrow"""
        self.queries.append(query)
        return {"id": 1, "name": "test", "query": query}

    def fetch(self, query: str, *args) -> list[dict[str, Any]]:
        """동기 fetch"""
        self.queries.append(query)
        return [{"id": i, "name": f"item{i}"} for i in range(3)]

    def execute(self, query: str, *args) -> str:
        """동기 execute"""
        self.queries.append(query)
        return "OK"


class MockDbConnectionPool:
    """Mock DB 커넥션 풀

    테스트에서 커넥션 획득/반환을 추적할 수 있습니다.
    """

    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self._next_id = 0
        self._active_connections: list[MockConnection] = []
        self._released_connections: list[MockConnection] = []
        self.acquire_count = 0
        self.release_count = 0

    def acquire(self) -> MockConnection:
        """풀에서 커넥션 획득"""
        self._next_id += 1
        conn = MockConnection(id=self._next_id, pool=self)
        self._active_connections.append(conn)
        self.acquire_count += 1
        return conn

    def release(self, conn: MockConnection) -> None:
        """풀에 커넥션 반환"""
        if conn in self._active_connections:
            self._active_connections.remove(conn)
        conn.is_released = True
        self._released_connections.append(conn)
        self.release_count += 1

    def close(self) -> None:
        """풀 종료"""
        self._active_connections.clear()
        self._released_connections.clear()

    @property
    def active_count(self) -> int:
        return len(self._active_connections)

    @property
    def released_count(self) -> int:
        return len(self._released_connections)


# =============================================================================
# 테스트
# =============================================================================
class TestConnectionPoolBasic:
    """기본 커넥션 풀 동작 테스트"""

    def test_mock_pool_acquire_release(self):
        """MockPool 기본 동작 확인"""
        pool = MockDbConnectionPool()

        conn1 = pool.acquire()
        assert conn1.id == 1
        assert pool.active_count == 1

        conn2 = pool.acquire()
        assert conn2.id == 2
        assert pool.active_count == 2

        pool.release(conn1)
        assert pool.active_count == 1
        assert conn1.is_released

        pool.release(conn2)
        assert pool.active_count == 0


class TestRequestScopeConnection:
    """REQUEST 스코프 커넥션 테스트"""

    def test_connection_acquired_on_first_access(self, reset_container_manager):
        """첫 접근 시 커넥션 획득, 요청 종료 시 반환"""
        acquire_log: list[int] = []
        release_log: list[int] = []

        # Mock 풀 (싱글톤)
        @Component
        class DbConnectionPool:
            _pool: MockDbConnectionPool | None = None

            @PostConstruct
            def init_pool(self):
                self._pool = MockDbConnectionPool()

            @property
            def pool(self) -> MockDbConnectionPool:
                return self._pool

        # 요청별 커넥션 (REQUEST 스코프)
        @Component
        @Scope(ScopeEnum.REQUEST)
        class DbConnection:
            pool: DbConnectionPool
            _conn: MockConnection | None = None

            @PostConstruct
            def acquire(self):
                self._conn = self.pool.pool.acquire()
                acquire_log.append(self._conn.id)

            @PreDestroy
            def release(self):
                if self._conn:
                    release_log.append(self._conn.id)
                    self.pool.pool.release(self._conn)
                    self._conn = None

            @property
            def conn(self) -> MockConnection:
                return self._conn

        @Component
        class UserRepository:
            db: DbConnection

            def find_by_id(self, user_id: int) -> dict:
                return self.db.conn.fetchrow(
                    "SELECT * FROM users WHERE id = $1"
                )

        app = Application("test").ready()
        pool_instance = app.manager.get_instance(DbConnectionPool)
        repo = app.manager.get_instance(UserRepository)

        # 요청 전: 커넥션 없음
        assert pool_instance.pool.active_count == 0
        assert len(acquire_log) == 0

        # 첫 번째 요청
        with request_scope():
            result = repo.find_by_id(1)
            assert result["id"] == 1
            # 커넥션 획득됨
            assert len(acquire_log) == 1
            assert pool_instance.pool.active_count == 1

        # 요청 종료 후: 커넥션 반환됨
        assert len(release_log) == 1
        assert pool_instance.pool.active_count == 0

        # 두 번째 요청
        with request_scope():
            result = repo.find_by_id(2)
            assert len(acquire_log) == 2  # 새 커넥션 획득

        assert len(release_log) == 2  # 반환됨
        assert pool_instance.pool.active_count == 0

    def test_same_connection_within_request(self, reset_container_manager):
        """같은 요청 내에서는 같은 커넥션 사용"""
        connection_ids: list[int] = []

        @Component
        class DbConnectionPool:
            _pool: MockDbConnectionPool | None = None

            @PostConstruct
            def init_pool(self):
                self._pool = MockDbConnectionPool()

            @property
            def pool(self) -> MockDbConnectionPool:
                return self._pool

        @Component
        @Scope(ScopeEnum.REQUEST)
        class DbConnection:
            pool: DbConnectionPool
            _conn: MockConnection | None = None

            @PostConstruct
            def acquire(self):
                self._conn = self.pool.pool.acquire()

            @PreDestroy
            def release(self):
                if self._conn:
                    self.pool.pool.release(self._conn)

            def get_conn_id(self) -> int:
                return self._conn.id if self._conn else -1

        @Component
        class UserRepository:
            db: DbConnection

            def get_connection_id(self) -> int:
                return self.db.get_conn_id()

        @Component
        class OrderRepository:
            db: DbConnection  # 같은 REQUEST → 같은 커넥션

            def get_connection_id(self) -> int:
                return self.db.get_conn_id()

        @Component
        class UserService:
            user_repo: UserRepository
            order_repo: OrderRepository

            def get_all_connection_ids(self) -> list[int]:
                return [
                    self.user_repo.get_connection_id(),
                    self.order_repo.get_connection_id(),
                ]

        app = Application("test").ready()
        service = app.manager.get_instance(UserService)
        pool = app.manager.get_instance(DbConnectionPool)

        # 첫 번째 요청
        with request_scope():
            ids = service.get_all_connection_ids()
            connection_ids.extend(ids)
            # 같은 요청 → 같은 커넥션!
            assert ids[0] == ids[1]

        # 두 번째 요청
        with request_scope():
            ids2 = service.get_all_connection_ids()
            connection_ids.extend(ids2)
            # 같은 요청 → 같은 커넥션
            assert ids2[0] == ids2[1]

        # 다른 요청 → 다른 커넥션
        assert connection_ids[0] != connection_ids[2]

    def test_connection_released_on_exception(self, reset_container_manager):
        """예외 발생해도 커넥션 반환"""
        release_count = [0]

        @Component
        class DbConnectionPool:
            _pool: MockDbConnectionPool | None = None

            @PostConstruct
            def init_pool(self):
                self._pool = MockDbConnectionPool()

            @property
            def pool(self) -> MockDbConnectionPool:
                return self._pool

        @Component
        @Scope(ScopeEnum.REQUEST)
        class DbConnection:
            pool: DbConnectionPool
            _conn: MockConnection | None = None

            @PostConstruct
            def acquire(self):
                self._conn = self.pool.pool.acquire()

            @PreDestroy
            def release(self):
                if self._conn:
                    release_count[0] += 1
                    self.pool.pool.release(self._conn)

            def raise_error(self):
                raise ValueError("Test error!")

        @Component
        class Service:
            db: DbConnection

            def do_something(self):
                self.db.raise_error()

        app = Application("test").ready()
        service = app.manager.get_instance(Service)
        pool = app.manager.get_instance(DbConnectionPool)

        # 예외 발생
        with pytest.raises(ValueError, match="Test error!"):
            with request_scope():
                service.do_something()

        # 예외가 발생해도 PreDestroy로 커넥션 반환됨
        assert release_count[0] == 1
        assert pool.pool.active_count == 0


class TestMultipleRequestsConcurrent:
    """동시 요청 격리 테스트"""

    @pytest.mark.asyncio
    async def test_concurrent_requests_isolated(self, reset_container_manager):
        """동시 요청들이 각각 독립적인 커넥션 사용"""
        import asyncio
        from bloom.core.request_context import RequestContext

        @Component
        class DbConnectionPool:
            _pool: MockDbConnectionPool | None = None

            @PostConstruct
            def init_pool(self):
                self._pool = MockDbConnectionPool()

            @property
            def pool(self) -> MockDbConnectionPool:
                return self._pool

        @Component
        @Scope(ScopeEnum.REQUEST)
        class DbConnection:
            pool: DbConnectionPool
            _conn: MockConnection | None = None

            @PostConstruct
            def acquire(self):
                self._conn = self.pool.pool.acquire()

            @PreDestroy
            def release(self):
                if self._conn:
                    self.pool.pool.release(self._conn)

            def get_conn_id(self) -> int:
                return self._conn.id if self._conn else -1

        @Component
        class Service:
            db: DbConnection

            def get_connection_id(self) -> int:
                return self.db.get_conn_id()

        app = Application("test").ready()
        service = app.manager.get_instance(Service)
        pool = app.manager.get_instance(DbConnectionPool)

        results: list[int] = []

        async def handle_request(request_id: int):
            """각 요청 시뮬레이션"""
            RequestContext.start()
            try:
                conn_id = service.get_connection_id()
                await asyncio.sleep(0.01)  # 약간의 지연
                # 같은 요청 내에서 다시 조회해도 같은 커넥션
                conn_id_again = service.get_connection_id()
                assert conn_id == conn_id_again
                results.append(conn_id)
            finally:
                RequestContext.end()

        # 5개 동시 요청
        await asyncio.gather(*[handle_request(i) for i in range(5)])

        # 각 요청이 다른 커넥션 사용
        assert len(set(results)) == 5
        # 모든 커넥션 반환됨
        assert pool.pool.active_count == 0


class TestConnectionWithTransaction:
    """트랜잭션 패턴 테스트"""

    def test_same_connection_for_transaction(self, reset_container_manager):
        """같은 요청 내 모든 작업이 같은 커넥션 사용 (트랜잭션 가능)"""
        queries_executed: list[str] = []

        @Component
        class DbConnectionPool:
            _pool: MockDbConnectionPool | None = None

            @PostConstruct
            def init_pool(self):
                self._pool = MockDbConnectionPool()

            @property
            def pool(self) -> MockDbConnectionPool:
                return self._pool

        @Component
        @Scope(ScopeEnum.REQUEST)
        class DbConnection:
            pool: DbConnectionPool
            _conn: MockConnection | None = None

            @PostConstruct
            def acquire(self):
                self._conn = self.pool.pool.acquire()

            @PreDestroy
            def release(self):
                if self._conn:
                    # 쿼리 로그 저장
                    queries_executed.extend(self._conn.queries)
                    self.pool.pool.release(self._conn)

            def execute(self, query: str):
                return self._conn.execute(query)

        @Component
        class UserRepository:
            db: DbConnection

            def create(self, name: str):
                self.db.execute(f"INSERT INTO users (name) VALUES ('{name}')")

        @Component
        class OrderRepository:
            db: DbConnection

            def create(self, user_id: int):
                self.db.execute(f"INSERT INTO orders (user_id) VALUES ({user_id})")

        @Component
        class TransactionService:
            db: DbConnection
            user_repo: UserRepository
            order_repo: OrderRepository

            def create_user_with_order(self, name: str):
                # 모두 같은 커넥션 사용 → 트랜잭션 가능
                self.db.execute("BEGIN")
                self.user_repo.create(name)
                self.order_repo.create(1)
                self.db.execute("COMMIT")

        app = Application("test").ready()
        service = app.manager.get_instance(TransactionService)

        with request_scope():
            service.create_user_with_order("Alice")

        # 트랜잭션 내 모든 쿼리가 같은 커넥션에서 실행됨
        assert queries_executed == [
            "BEGIN",
            "INSERT INTO users (name) VALUES ('Alice')",
            "INSERT INTO orders (user_id) VALUES (1)",
            "COMMIT",
        ]


class TestAsyncPostConstruct:
    """async @PostConstruct 테스트 (async with request_scope())"""

    @pytest.mark.asyncio
    async def test_async_postconstruct_with_async_context(
        self, reset_container_manager
    ):
        """async with request_scope()로 async @PostConstruct 지원"""
        init_log: list[str] = []
        cleanup_log: list[str] = []

        @Component
        class DbConnectionPool:
            _pool: MockDbConnectionPool | None = None

            @PostConstruct
            def init_pool(self):
                self._pool = MockDbConnectionPool()

            @property
            def pool(self) -> MockDbConnectionPool:
                return self._pool

        @Component
        @Scope(ScopeEnum.REQUEST)
        class AsyncDbConnection:
            pool: DbConnectionPool
            _conn: MockConnection | None = None

            @PostConstruct
            async def acquire(self):
                # async 초기화 시뮬레이션
                import asyncio

                await asyncio.sleep(0.001)
                self._conn = self.pool.pool.acquire()
                init_log.append(f"acquired:{self._conn.id}")

            @PreDestroy
            async def release(self):
                if self._conn:
                    import asyncio

                    await asyncio.sleep(0.001)
                    cleanup_log.append(f"released:{self._conn.id}")
                    self.pool.pool.release(self._conn)

            def get_conn_id(self) -> int:
                return self._conn.id if self._conn else -1

        @Component
        class Service:
            db: AsyncDbConnection

            def get_connection_id(self) -> int:
                return self.db.get_conn_id()

        app = Application("test").ready()
        service = app.manager.get_instance(Service)
        pool = app.manager.get_instance(DbConnectionPool)

        # async with로 async @PostConstruct/@PreDestroy 지원
        async with request_scope():
            # 필드 접근 시 pending에 등록됨
            conn_id = service.get_connection_id()
            # pending init이 아직 실행 안됨 → -1
            assert conn_id == -1

        # async context 종료 시:
        # 1. run_pending_init() 실행 → async @PostConstruct
        # 2. end_async() 실행 → async @PreDestroy
        assert len(init_log) == 1
        assert len(cleanup_log) == 1
        assert pool.pool.active_count == 0

    @pytest.mark.asyncio
    async def test_async_postconstruct_run_before_handler(
        self, reset_container_manager
    ):
        """핸들러 호출 전에 pending init 실행 (Router 통합 시)

        Note: Router.dispatch()에서 핸들러 호출 전 run_pending_init()을 호출합니다.
              이 테스트는 그 동작을 시뮬레이션합니다.
        """
        from bloom.core.request_context import RequestContext

        init_log: list[str] = []

        @Component
        class DbConnectionPool:
            _pool: MockDbConnectionPool | None = None

            @PostConstruct
            def init_pool(self):
                self._pool = MockDbConnectionPool()

            @property
            def pool(self) -> MockDbConnectionPool:
                return self._pool

        @Component
        @Scope(ScopeEnum.REQUEST)
        class AsyncDbConnection:
            pool: DbConnectionPool
            _conn: MockConnection | None = None

            @PostConstruct
            async def acquire(self):
                import asyncio

                await asyncio.sleep(0.001)
                self._conn = self.pool.pool.acquire()
                init_log.append(f"acquired:{self._conn.id}")

            @PreDestroy
            async def release(self):
                if self._conn:
                    self.pool.pool.release(self._conn)

            def get_conn_id(self) -> int:
                return self._conn.id if self._conn else -1

        @Component
        class Service:
            db: AsyncDbConnection

            def get_connection_id(self) -> int:
                return self.db.get_conn_id()

        app = Application("test").ready()
        service = app.manager.get_instance(Service)

        # Router.dispatch() 시뮬레이션
        RequestContext.start()
        try:
            # 1. 필드 접근 (pending에 등록)
            _ = service.get_connection_id()

            # 2. run_pending_init() 호출 (Router에서 수행)
            await RequestContext.run_pending_init()

            # 3. 이제 커넥션이 초기화됨
            conn_id = service.get_connection_id()
            assert conn_id == 1
            assert len(init_log) == 1
        finally:
            await RequestContext.end_async()


class TestMiddlewareWithRequestScope:
    """미들웨어에서 REQUEST 스코프 사용 테스트"""

    @pytest.mark.asyncio
    async def test_middleware_can_use_request_scope(self, reset_container_manager):
        """미들웨어에서 REQUEST 스코프 인스턴스 사용 가능"""
        from bloom.web import Controller, Get
        from bloom.web.middleware import Middleware, MiddlewareChain
        from bloom.web import HttpRequest, HttpResponse
        from bloom.core.decorators import Factory

        middleware_log: list[str] = []
        handler_log: list[str] = []

        @Component
        class DbConnectionPool:
            _pool: MockDbConnectionPool | None = None

            @PostConstruct
            def init_pool(self):
                self._pool = MockDbConnectionPool()

            @property
            def pool(self) -> MockDbConnectionPool:
                return self._pool

        @Component
        @Scope(ScopeEnum.REQUEST)
        class DbConnection:
            pool: DbConnectionPool
            _conn: MockConnection | None = None

            @PostConstruct
            def acquire(self):
                self._conn = self.pool.pool.acquire()

            @PreDestroy
            def release(self):
                if self._conn:
                    self.pool.pool.release(self._conn)

            def get_conn_id(self) -> int:
                return self._conn.id if self._conn else -1

        # 미들웨어에서 REQUEST 스코프 인스턴스 사용
        @Component
        class DbLoggingMiddleware(Middleware):
            db: DbConnection

            async def process_request(self, request: HttpRequest) -> None:
                conn_id = self.db.get_conn_id()
                middleware_log.append(f"middleware:conn={conn_id}")
                return None

        @Controller
        class TestController:
            db: DbConnection

            @Get("/test")
            def get_test(self) -> dict:
                conn_id = self.db.get_conn_id()
                handler_log.append(f"handler:conn={conn_id}")
                return {"connection_id": conn_id}

        @Component
        class MiddlewareConfig:
            @Factory
            def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.add_group_after(*middlewares)
                return chain

        app = Application("test").ready()
        pool = app.manager.get_instance(DbConnectionPool)

        # ASGI 테스트
        from bloom.testing import TestClient

        client = TestClient(app)
        response = await client.get("/test")

        assert response.status_code == 200
        data = response.json()

        # 미들웨어와 핸들러가 같은 커넥션 사용
        assert len(middleware_log) == 1
        assert len(handler_log) == 1

        # 같은 REQUEST 스코프 → 같은 커넥션
        assert "conn=1" in middleware_log[0]
        assert "conn=1" in handler_log[0]

        # 커넥션이 반환됨
        assert pool.pool.active_count == 0
        assert pool.pool.acquire_count == 1  # 단 하나의 커넥션만 사용됨
