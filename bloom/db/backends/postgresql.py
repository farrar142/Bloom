"""PostgreSQL Backend

PostgreSQL 연결을 위한 백엔드입니다.

드라이버:
    - 동기: psycopg2 또는 psycopg (psycopg3)
    - 비동기: asyncpg

설치:
    pip install psycopg2-binary  # 동기
    pip install asyncpg          # 비동기
    pip install psycopg[binary]  # psycopg3 (동기+비동기)
"""

from __future__ import annotations
from typing import Any, AsyncIterator
from contextlib import asynccontextmanager
import threading
from queue import Queue, Empty

from .base import (
    DatabaseBackend,
    Connection,
    AsyncConnection,
    ConnectionPool,
    ConnectionConfig,
)


class PostgreSQLConnection(Connection):
    """PostgreSQL 동기 연결 래퍼 (psycopg2)"""
    
    def __init__(self, conn: Any):
        self._conn = conn
        self._cursor: Any = None
    
    @property
    def raw(self) -> Any:
        return self._conn
    
    def execute(self, sql: str, params: dict[str, Any] | None = None) -> "PostgreSQLConnection":
        # psycopg2는 %(name)s 형식 사용
        self._cursor = self._conn.cursor()
        self._cursor.execute(sql, params or {})
        return self
    
    def executemany(self, sql: str, params_list: list[dict[str, Any]]) -> "PostgreSQLConnection":
        self._cursor = self._conn.cursor()
        self._cursor.executemany(sql, params_list)
        return self
    
    def fetchone(self) -> dict[str, Any] | None:
        if self._cursor is None:
            return None
        row = self._cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in self._cursor.description]
        return dict(zip(columns, row))
    
    def fetchall(self) -> list[dict[str, Any]]:
        if self._cursor is None:
            return []
        rows = self._cursor.fetchall()
        columns = [desc[0] for desc in self._cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    
    def commit(self) -> None:
        self._conn.commit()
    
    def rollback(self) -> None:
        self._conn.rollback()
    
    def close(self) -> None:
        self._conn.close()
    
    @property
    def lastrowid(self) -> int | None:
        # PostgreSQL은 RETURNING 사용 권장
        # psycopg2의 lastrowid는 OID 반환 (deprecated)
        return None
    
    @property
    def rowcount(self) -> int:
        if self._cursor is None:
            return 0
        return self._cursor.rowcount


class AsyncpgConnection(AsyncConnection):
    """PostgreSQL 비동기 연결 래퍼 (asyncpg)"""
    
    def __init__(self, conn: Any):
        self._conn = conn
        self._result: Any = None
        self._rowcount: int = 0
    
    @property
    def raw(self) -> Any:
        return self._conn
    
    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> "AsyncpgConnection":
        # asyncpg는 $1, $2 형식 사용
        # %(name)s 형식을 $n 형식으로 변환
        if params:
            converted_sql, args = self._convert_params(sql, params)
            self._result = await self._conn.fetch(converted_sql, *args)
        else:
            self._result = await self._conn.fetch(sql)
        self._rowcount = len(self._result) if self._result else 0
        return self
    
    def _convert_params(self, sql: str, params: dict[str, Any]) -> tuple[str, list[Any]]:
        """%(name)s → $n 변환"""
        import re
        
        args: list[Any] = []
        param_map: dict[str, int] = {}
        
        def replacer(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in param_map:
                param_map[name] = len(args) + 1
                args.append(params[name])
            return f"${param_map[name]}"
        
        converted = re.sub(r"%\((\w+)\)s", replacer, sql)
        return converted, args
    
    async def executemany(self, sql: str, params_list: list[dict[str, Any]]) -> "AsyncpgConnection":
        for params in params_list:
            await self.execute(sql, params)
        return self
    
    async def fetchone(self) -> dict[str, Any] | None:
        if not self._result:
            return None
        row = self._result[0] if self._result else None
        return dict(row) if row else None
    
    async def fetchall(self) -> list[dict[str, Any]]:
        if not self._result:
            return []
        return [dict(row) for row in self._result]
    
    async def commit(self) -> None:
        # asyncpg는 자동 커밋, 트랜잭션은 별도 관리
        pass
    
    async def rollback(self) -> None:
        # 트랜잭션 컨텍스트에서 관리
        pass
    
    async def close(self) -> None:
        await self._conn.close()
    
    @property
    def lastrowid(self) -> int | None:
        # RETURNING 절 사용
        if self._result and len(self._result) > 0:
            row = self._result[0]
            # 첫 번째 컬럼이 ID라고 가정
            if len(row) > 0:
                return row[0]
        return None
    
    @property
    def rowcount(self) -> int:
        return self._rowcount


class PostgreSQLConnectionPool(ConnectionPool):
    """PostgreSQL 커넥션 풀"""
    
    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._sync_pool: Queue[Any] = Queue(maxsize=self._size)
        self._sync_connections: list[Any] = []
        self._async_pool: Any = None  # asyncpg Pool
        self._lock = threading.Lock()
    
    def _get_connect_params(self) -> dict[str, Any]:
        """연결 파라미터 반환"""
        return {
            "host": self.config.host,
            "port": self.config.port or 5432,
            "database": self.config.database,
            "user": self.config.user,
            "password": self.config.password,
            **self.config.options,
        }
    
    def _create_sync_connection(self) -> Any:
        """psycopg2 연결 생성"""
        try:
            import psycopg2
        except ImportError:
            try:
                import psycopg
                return psycopg.connect(**self._get_connect_params())
            except ImportError:
                raise ImportError(
                    "PostgreSQL driver not found. Install one of:\n"
                    "  pip install psycopg2-binary\n"
                    "  pip install psycopg[binary]"
                )
        
        return psycopg2.connect(**self._get_connect_params())
    
    def acquire(self) -> PostgreSQLConnection:
        try:
            conn = self._sync_pool.get_nowait()
        except Empty:
            with self._lock:
                if len(self._sync_connections) < self._size + self._max_overflow:
                    conn = self._create_sync_connection()
                    self._sync_connections.append(conn)
                else:
                    conn = self._sync_pool.get(timeout=self.config.pool_timeout)
        
        return PostgreSQLConnection(conn)
    
    def release(self, conn: Connection) -> None:
        try:
            # 연결 상태 확인
            raw = conn.raw
            if not raw.closed:
                raw.rollback()  # 미완료 트랜잭션 롤백
                self._sync_pool.put_nowait(raw)
            else:
                with self._lock:
                    if raw in self._sync_connections:
                        self._sync_connections.remove(raw)
        except:
            pass
    
    async def acquire_async(self) -> AsyncpgConnection:
        if self._async_pool is None:
            try:
                import asyncpg
            except ImportError:
                raise ImportError(
                    "asyncpg is required for async PostgreSQL. "
                    "Install it with: pip install asyncpg"
                )
            
            self._async_pool = await asyncpg.create_pool(
                host=self.config.host,
                port=self.config.port or 5432,
                database=self.config.database,
                user=self.config.user,
                password=self.config.password,
                min_size=1,
                max_size=self._size,
                **self.config.options,
            )
        
        conn = await self._async_pool.acquire()
        return AsyncpgConnection(conn)
    
    async def release_async(self, conn: AsyncConnection) -> None:
        if self._async_pool:
            await self._async_pool.release(conn.raw)
    
    def close_all(self) -> None:
        for conn in self._sync_connections:
            try:
                conn.close()
            except:
                pass
        self._sync_connections.clear()
        
        while not self._sync_pool.empty():
            try:
                conn = self._sync_pool.get_nowait()
                conn.close()
            except:
                break
    
    async def close_all_async(self) -> None:
        self.close_all()
        if self._async_pool:
            await self._async_pool.close()
            self._async_pool = None


class PostgreSQLBackend(DatabaseBackend):
    """PostgreSQL 백엔드
    
    Usage:
        # URL 형식
        backend = PostgreSQLBackend("postgresql://user:pass@localhost:5432/mydb")
        
        # 파라미터 형식
        backend = PostgreSQLBackend(
            host="localhost",
            port=5432,
            database="mydb",
            user="postgres",
            password="secret",
        )
        
        # 동기 연결
        with backend.connection() as conn:
            conn.execute("SELECT * FROM users WHERE id = %(id)s", {"id": 1})
            user = conn.fetchone()
        
        # 비동기 연결
        async with backend.connection_async() as conn:
            await conn.execute("SELECT * FROM users")
            users = await conn.fetchall()
    """
    
    name = "postgresql"
    driver_sync = "psycopg2"
    driver_async = "asyncpg"
    
    def __init__(
        self,
        url: str | None = None,
        *,
        host: str = "localhost",
        port: int = 5432,
        database: str = "postgres",
        user: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ):
        if url:
            config = ConnectionConfig.from_url(url, **kwargs)
        else:
            config = ConnectionConfig(
                driver="postgresql",
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                **kwargs,
            )
        super().__init__(config)
    
    def create_pool(self) -> PostgreSQLConnectionPool:
        return PostgreSQLConnectionPool(self.config)
    
    def check_driver(self) -> bool:
        try:
            import psycopg2
            return True
        except ImportError:
            pass
        
        try:
            import psycopg
            return True
        except ImportError:
            pass
        
        return False
    
    def check_async_driver(self) -> bool:
        try:
            import asyncpg
            return True
        except ImportError:
            return False
    
    def get_install_instruction(self) -> str:
        return (
            "Install PostgreSQL driver:\n"
            "  pip install psycopg2-binary  # Sync only\n"
            "  pip install asyncpg          # Async only\n"
            "  pip install psycopg[binary]  # Both (psycopg3)"
        )
