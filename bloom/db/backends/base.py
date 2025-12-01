"""Base Database Backend - Abstract interface"""

from __future__ import annotations
from abc import ABC, abstractmethod
from contextlib import contextmanager, asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, AsyncIterator, TypeVar, Generic, TYPE_CHECKING
import asyncio

if TYPE_CHECKING:
    from ..dialect import Dialect


T = TypeVar("T")


@dataclass
class ConnectionConfig:
    """연결 설정

    URL 형식:
        - sqlite:///path/to/db.sqlite3
        - postgresql://user:password@host:port/database
        - mysql://user:password@host:port/database

    또는 개별 파라미터로 설정 가능
    """

    # URL 기반 설정
    url: str | None = None

    # 개별 파라미터
    driver: str = "sqlite"
    host: str = "localhost"
    port: int | None = None
    database: str = ":memory:"
    user: str | None = None
    password: str | None = None

    # 커넥션 풀 설정
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: float = 30.0
    pool_recycle: int = 3600  # 1시간

    # 추가 옵션
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> ConnectionConfig:
        """URL에서 설정 파싱

        Examples:
            >>> config = ConnectionConfig.from_url("postgresql://user:pass@localhost:5432/mydb")
            >>> config.driver
            'postgresql'
            >>> config.host
            'localhost'
        """
        import urllib.parse

        parsed = urllib.parse.urlparse(url)

        driver = parsed.scheme
        if driver in ("postgres", "pg"):
            driver = "postgresql"

        # 기본 포트 설정
        default_ports = {
            "postgresql": 5432,
            "mysql": 3306,
            "sqlite": None,
        }

        config = cls(
            url=url,
            driver=driver,
            host=parsed.hostname or "localhost",
            port=parsed.port or default_ports.get(driver),
            database=parsed.path.lstrip("/") or ":memory:",
            user=parsed.username,
            password=parsed.password,
            **kwargs,
        )

        # 쿼리 파라미터를 options에 추가
        if parsed.query:
            config.options.update(urllib.parse.parse_qs(parsed.query))

        return config


class Connection(ABC):
    """데이터베이스 연결 추상 클래스"""

    @property
    @abstractmethod
    def raw(self) -> Any:
        """원본 연결 객체 반환"""
        ...

    @property
    @abstractmethod
    def dialect(self) -> "Dialect":
        """SQL Dialect 반환"""
        ...

    @abstractmethod
    def execute(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """SQL 실행"""
        ...

    @abstractmethod
    def executemany(self, sql: str, params_list: list[dict[str, Any]]) -> Any:
        """여러 SQL 실행"""
        ...

    @abstractmethod
    def fetchone(self) -> dict[str, Any] | None:
        """한 행 조회"""
        ...

    @abstractmethod
    def fetchall(self) -> list[dict[str, Any]]:
        """모든 행 조회"""
        ...

    @abstractmethod
    def commit(self) -> None:
        """커밋"""
        ...

    @abstractmethod
    def rollback(self) -> None:
        """롤백"""
        ...

    @abstractmethod
    def close(self) -> None:
        """연결 닫기"""
        ...

    @property
    @abstractmethod
    def lastrowid(self) -> int | None:
        """마지막 INSERT의 ID"""
        ...

    @property
    @abstractmethod
    def rowcount(self) -> int:
        """영향받은 행 수"""
        ...


class AsyncConnection(ABC):
    """비동기 데이터베이스 연결 추상 클래스"""

    @property
    @abstractmethod
    def raw(self) -> Any:
        """원본 연결 객체 반환"""
        ...

    @abstractmethod
    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """SQL 실행"""
        ...

    @abstractmethod
    async def executemany(self, sql: str, params_list: list[dict[str, Any]]) -> Any:
        """여러 SQL 실행"""
        ...

    @abstractmethod
    async def fetchone(self) -> dict[str, Any] | None:
        """한 행 조회"""
        ...

    @abstractmethod
    async def fetchall(self) -> list[dict[str, Any]]:
        """모든 행 조회"""
        ...

    @abstractmethod
    async def commit(self) -> None:
        """커밋"""
        ...

    @abstractmethod
    async def rollback(self) -> None:
        """롤백"""
        ...

    @abstractmethod
    async def close(self) -> None:
        """연결 닫기"""
        ...

    @property
    @abstractmethod
    def lastrowid(self) -> int | None:
        """마지막 INSERT의 ID"""
        ...

    @property
    @abstractmethod
    def rowcount(self) -> int:
        """영향받은 행 수"""
        ...


class ConnectionPool(ABC):
    """커넥션 풀 추상 클래스"""

    def __init__(self, config: ConnectionConfig):
        self.config = config
        self._size = config.pool_size
        self._max_overflow = config.max_overflow

    @abstractmethod
    def acquire(self) -> Connection:
        """연결 획득 (동기)"""
        ...

    @abstractmethod
    def release(self, conn: Connection) -> None:
        """연결 반환 (동기)"""
        ...

    @abstractmethod
    async def acquire_async(self) -> AsyncConnection:
        """연결 획득 (비동기)"""
        ...

    @abstractmethod
    async def release_async(self, conn: AsyncConnection) -> None:
        """연결 반환 (비동기)"""
        ...

    @abstractmethod
    def close_all(self) -> None:
        """모든 연결 닫기"""
        ...

    @abstractmethod
    async def close_all_async(self) -> None:
        """모든 연결 닫기 (비동기)"""
        ...

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """컨텍스트 매니저로 연결 획득/반환"""
        conn = self.acquire()
        try:
            yield conn
        finally:
            self.release(conn)

    @asynccontextmanager
    async def connection_async(self) -> AsyncIterator[AsyncConnection]:
        """비동기 컨텍스트 매니저로 연결 획득/반환"""
        conn = await self.acquire_async()
        try:
            yield conn
        finally:
            await self.release_async(conn)


class DatabaseBackend(ABC):
    """데이터베이스 백엔드 추상 클래스

    각 DB별 연결 구현의 베이스 클래스입니다.
    동기/비동기 연결을 모두 지원합니다.
    """

    name: str = "generic"
    driver_sync: str | None = None  # 동기 드라이버 (예: psycopg2)
    driver_async: str | None = None  # 비동기 드라이버 (예: asyncpg)

    def __init__(self, config: ConnectionConfig | str | None = None, **kwargs: Any):
        if config is None:
            self.config = ConnectionConfig(**kwargs)
        elif isinstance(config, str):
            self.config = ConnectionConfig.from_url(config, **kwargs)
        else:
            self.config = config

        self._pool: ConnectionPool | None = None

    @abstractmethod
    def create_pool(self) -> ConnectionPool:
        """커넥션 풀 생성"""
        ...

    @property
    def pool(self) -> ConnectionPool:
        """커넥션 풀 반환 (lazy initialization)"""
        if self._pool is None:
            self._pool = self.create_pool()
        return self._pool

    def connect(self) -> Connection:
        """동기 연결 획득"""
        return self.pool.acquire()

    async def connect_async(self) -> AsyncConnection:
        """비동기 연결 획득"""
        return await self.pool.acquire_async()

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """동기 연결 컨텍스트 매니저"""
        with self.pool.connection() as conn:
            yield conn

    @asynccontextmanager
    async def connection_async(self) -> AsyncIterator[AsyncConnection]:
        """비동기 연결 컨텍스트 매니저"""
        async with self.pool.connection_async() as conn:
            yield conn

    def close(self) -> None:
        """백엔드 종료"""
        if self._pool:
            self._pool.close_all()

    async def close_async(self) -> None:
        """백엔드 종료 (비동기)"""
        if self._pool:
            await self._pool.close_all_async()

    @abstractmethod
    def check_driver(self) -> bool:
        """드라이버 설치 여부 확인"""
        ...

    def get_install_instruction(self) -> str:
        """드라이버 설치 안내 메시지"""
        return f"Please install the required driver for {self.name}"

    @property
    @abstractmethod
    def dialect(self) -> Dialect:
        """해당 백엔드의 SQL Dialect 반환"""
        ...
