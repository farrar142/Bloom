"""MySQL Backend

MySQL/MariaDB 연결을 위한 백엔드입니다.

드라이버:
    - 동기: pymysql 또는 mysql-connector-python
    - 비동기: aiomysql

설치:
    pip install pymysql           # 동기 (Pure Python)
    pip install mysql-connector-python  # 동기 (Oracle 공식)
    pip install aiomysql          # 비동기
"""

from __future__ import annotations
from typing import Any
import threading
from queue import Queue, Empty

from .base import (
    DatabaseBackend,
    Connection,
    AsyncConnection,
    ConnectionPool,
    ConnectionConfig,
)
from ..dialect import MySQLDialect, Dialect


class MySQLConnection(Connection):
    """MySQL 동기 연결 래퍼"""

    def __init__(self, conn: Any, dialect: Dialect):
        self._conn = conn
        self._cursor: Any = None
        self._dialect = dialect

    @property
    def raw(self) -> Any:
        return self._conn

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    def execute(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> "MySQLConnection":
        # pymysql은 %(name)s 형식 사용
        self._cursor = self._conn.cursor()
        self._cursor.execute(sql, params or {})
        return self

    def executemany(
        self, sql: str, params_list: list[dict[str, Any]]
    ) -> "MySQLConnection":
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
        if self._cursor is None:
            return None
        return self._cursor.lastrowid

    @property
    def rowcount(self) -> int:
        if self._cursor is None:
            return 0
        return self._cursor.rowcount


class AioMySQLConnection(AsyncConnection):
    """MySQL 비동기 연결 래퍼 (aiomysql)"""

    def __init__(self, conn: Any, dialect: Dialect):
        self._conn = conn
        self._cursor: Any = None
        self._dialect = dialect

    @property
    def raw(self) -> Any:
        return self._conn

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    async def execute(
        self, sql: str, params: dict[str, Any] | None = None
    ) -> "AioMySQLConnection":
        self._cursor = await self._conn.cursor()
        await self._cursor.execute(sql, params or {})
        return self

    async def executemany(
        self, sql: str, params_list: list[dict[str, Any]]
    ) -> "AioMySQLConnection":
        self._cursor = await self._conn.cursor()
        await self._cursor.executemany(sql, params_list)
        return self

    async def fetchone(self) -> dict[str, Any] | None:
        if self._cursor is None:
            return None
        row = await self._cursor.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in self._cursor.description]
        return dict(zip(columns, row))

    async def fetchall(self) -> list[dict[str, Any]]:
        if self._cursor is None:
            return []
        rows = await self._cursor.fetchall()
        columns = [desc[0] for desc in self._cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    async def commit(self) -> None:
        await self._conn.commit()

    async def rollback(self) -> None:
        await self._conn.rollback()

    async def close(self) -> None:
        self._conn.close()

    @property
    def lastrowid(self) -> int | None:
        if self._cursor is None:
            return None
        return self._cursor.lastrowid

    @property
    def rowcount(self) -> int:
        if self._cursor is None:
            return 0
        return self._cursor.rowcount


class MySQLConnectionPool(ConnectionPool):
    """MySQL 커넥션 풀"""

    def __init__(self, config: ConnectionConfig, dialect: Dialect):
        super().__init__(config)
        self._sync_pool: Queue[Any] = Queue(maxsize=self._size)
        self._sync_connections: list[Any] = []
        self._async_pool: Any = None
        self._lock = threading.Lock()
        self._dialect = dialect

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    def _get_connect_params(self) -> dict[str, Any]:
        """연결 파라미터 반환"""
        params = {
            "host": self.config.host,
            "port": self.config.port or 3306,
            "database": self.config.database,
            "user": self.config.user,
            "password": self.config.password,
            "charset": "utf8mb4",
            **self.config.options,
        }
        # None 값 제거
        return {k: v for k, v in params.items() if v is not None}

    def _create_sync_connection(self) -> Any:
        """pymysql 연결 생성"""
        try:
            import pymysql

            return pymysql.connect(**self._get_connect_params())
        except ImportError:
            pass

        try:
            import mysql.connector

            params = self._get_connect_params()
            # mysql-connector는 database 대신 db 사용 가능
            return mysql.connector.connect(**params)
        except ImportError:
            raise ImportError(
                "MySQL driver not found. Install one of:\n"
                "  pip install pymysql\n"
                "  pip install mysql-connector-python"
            )

    def acquire(self) -> MySQLConnection:
        try:
            conn = self._sync_pool.get_nowait()
            # 연결 유효성 확인
            if not self._is_connection_alive(conn):
                conn.close()
                conn = self._create_sync_connection()
        except Empty:
            with self._lock:
                if len(self._sync_connections) < self._size + self._max_overflow:
                    conn = self._create_sync_connection()
                    self._sync_connections.append(conn)
                else:
                    conn = self._sync_pool.get(timeout=self.config.pool_timeout)

        return MySQLConnection(conn, self._dialect)

    def _is_connection_alive(self, conn: Any) -> bool:
        """연결 유효성 확인"""
        try:
            conn.ping(reconnect=True)
            return True
        except:
            return False

    def release(self, conn: Connection) -> None:
        try:
            raw = conn.raw
            if self._is_connection_alive(raw):
                raw.rollback()
                self._sync_pool.put_nowait(raw)
            else:
                with self._lock:
                    if raw in self._sync_connections:
                        self._sync_connections.remove(raw)
        except:
            pass

    async def acquire_async(self) -> AioMySQLConnection:
        if self._async_pool is None:
            try:
                import aiomysql
            except ImportError:
                raise ImportError(
                    "aiomysql is required for async MySQL. "
                    "Install it with: pip install aiomysql"
                )

            params = self._get_connect_params()
            # aiomysql은 db 파라미터 사용
            if "database" in params:
                params["db"] = params.pop("database")

            self._async_pool = await aiomysql.create_pool(
                minsize=1,
                maxsize=self._size,
                **params,
            )

        conn = await self._async_pool.acquire()
        return AioMySQLConnection(conn, self._dialect)

    async def release_async(self, conn: AsyncConnection) -> None:
        if self._async_pool:
            self._async_pool.release(conn.raw)

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
            self._async_pool.close()
            await self._async_pool.wait_closed()
            self._async_pool = None


class MySQLBackend(DatabaseBackend):
    """MySQL/MariaDB 백엔드

    Usage:
        # URL 형식
        backend = MySQLBackend("mysql://user:pass@localhost:3306/mydb")

        # 파라미터 형식
        backend = MySQLBackend(
            host="localhost",
            port=3306,
            database="mydb",
            user="root",
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

    name = "mysql"
    driver_sync = "pymysql"
    driver_async = "aiomysql"

    def __init__(
        self,
        url: str | None = None,
        *,
        host: str = "localhost",
        port: int = 3306,
        database: str = "mysql",
        user: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ):
        if url:
            config = ConnectionConfig.from_url(url, **kwargs)
        else:
            config = ConnectionConfig(
                driver="mysql",
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                **kwargs,
            )
        super().__init__(config)
        self._dialect = MySQLDialect()

    def create_pool(self) -> MySQLConnectionPool:
        return MySQLConnectionPool(self.config, self._dialect)

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    def check_driver(self) -> bool:
        try:
            import pymysql

            return True
        except ImportError:
            pass

        try:
            import mysql.connector

            return True
        except ImportError:
            pass

        return False

    def check_async_driver(self) -> bool:
        try:
            import aiomysql

            return True
        except ImportError:
            return False

    def get_install_instruction(self) -> str:
        return (
            "Install MySQL driver:\n"
            "  pip install pymysql           # Sync (Pure Python, recommended)\n"
            "  pip install mysql-connector-python  # Sync (Oracle official)\n"
            "  pip install aiomysql          # Async"
        )
