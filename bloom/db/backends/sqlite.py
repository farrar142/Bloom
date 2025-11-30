"""SQLite Backend"""

from __future__ import annotations
from typing import Any, Iterator
from contextlib import contextmanager
import sqlite3
import threading
from queue import Queue, Empty

from .base import (
    DatabaseBackend,
    Connection,
    AsyncConnection,
    ConnectionPool,
    ConnectionConfig,
)


class SQLiteConnection(Connection):
    """SQLite 연결 래퍼"""
    
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._cursor: sqlite3.Cursor | None = None
        conn.row_factory = sqlite3.Row
    
    @property
    def raw(self) -> sqlite3.Connection:
        return self._conn
    
    def execute(self, sql: str, params: dict[str, Any] | None = None) -> "SQLiteConnection":
        self._cursor = self._conn.cursor()
        if params:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        return self
    
    def executemany(self, sql: str, params_list: list[dict[str, Any]]) -> "SQLiteConnection":
        self._cursor = self._conn.cursor()
        self._cursor.executemany(sql, params_list)
        return self
    
    def fetchone(self) -> dict[str, Any] | None:
        if self._cursor is None:
            return None
        row = self._cursor.fetchone()
        return dict(row) if row else None
    
    def fetchall(self) -> list[dict[str, Any]]:
        if self._cursor is None:
            return []
        return [dict(row) for row in self._cursor.fetchall()]
    
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


class SQLiteConnectionPool(ConnectionPool):
    """SQLite 커넥션 풀
    
    SQLite는 기본적으로 파일 기반이므로 커넥션 풀이 단순합니다.
    :memory: DB의 경우 단일 연결을 공유해야 합니다.
    """
    
    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._db_path = config.database
        self._is_memory = self._db_path == ":memory:"
        
        # :memory: DB는 단일 연결 공유
        self._shared_conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        
        # 파일 DB는 풀 사용
        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=self._size)
        self._connections: list[sqlite3.Connection] = []
    
    def _create_connection(self) -> sqlite3.Connection:
        """새 연결 생성"""
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            **self.config.options,
        )
        conn.row_factory = sqlite3.Row
        # FK 활성화
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    def acquire(self) -> SQLiteConnection:
        if self._is_memory:
            with self._lock:
                if self._shared_conn is None:
                    self._shared_conn = self._create_connection()
                return SQLiteConnection(self._shared_conn)
        
        try:
            conn = self._pool.get_nowait()
        except Empty:
            if len(self._connections) < self._size + self._max_overflow:
                conn = self._create_connection()
                self._connections.append(conn)
            else:
                # 대기
                conn = self._pool.get(timeout=self.config.pool_timeout)
        
        return SQLiteConnection(conn)
    
    def release(self, conn: Connection) -> None:
        if self._is_memory:
            # :memory: DB는 연결 유지
            return
        
        raw = conn.raw
        try:
            self._pool.put_nowait(raw)
        except:
            # 풀이 가득 차면 연결 닫기
            raw.close()
    
    async def acquire_async(self) -> AsyncConnection:
        # SQLite는 동기 연결만 지원, aiosqlite 필요
        raise NotImplementedError(
            "SQLite async requires aiosqlite. "
            "Install it with: pip install aiosqlite"
        )
    
    async def release_async(self, conn: AsyncConnection) -> None:
        raise NotImplementedError("Use aiosqlite for async SQLite")
    
    def close_all(self) -> None:
        if self._shared_conn:
            self._shared_conn.close()
            self._shared_conn = None
        
        for conn in self._connections:
            try:
                conn.close()
            except:
                pass
        self._connections.clear()
        
        # 풀 비우기
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except:
                break
    
    async def close_all_async(self) -> None:
        self.close_all()


class SQLiteBackend(DatabaseBackend):
    """SQLite 백엔드
    
    Usage:
        # 파일 DB
        backend = SQLiteBackend("db.sqlite3")
        backend = SQLiteBackend("sqlite:///db.sqlite3")
        
        # 메모리 DB
        backend = SQLiteBackend(":memory:")
        backend = SQLiteBackend()  # 기본값 :memory:
        
        # 연결 사용
        with backend.connection() as conn:
            conn.execute("SELECT * FROM users")
            rows = conn.fetchall()
    """
    
    name = "sqlite"
    driver_sync = "sqlite3"
    driver_async = "aiosqlite"
    
    def __init__(
        self,
        database: str = ":memory:",
        **kwargs: Any,
    ):
        # URL 형식 처리
        if database.startswith("sqlite:///"):
            database = database[len("sqlite:///"):]
        elif database.startswith("sqlite://"):
            database = database[len("sqlite://"):]
        
        config = ConnectionConfig(
            driver="sqlite",
            database=database,
            **kwargs,
        )
        super().__init__(config)
    
    def create_pool(self) -> SQLiteConnectionPool:
        return SQLiteConnectionPool(self.config)
    
    def check_driver(self) -> bool:
        # sqlite3는 표준 라이브러리
        return True
    
    def get_install_instruction(self) -> str:
        return "sqlite3 is included in Python standard library"
