"""Database Backends

데이터베이스 연결 및 커넥션 풀 관리를 위한 백엔드입니다.

사용 가능한 백엔드:
    - SQLiteBackend: SQLite (기본, 의존성 없음)
    - PostgreSQLBackend: PostgreSQL (psycopg2 또는 asyncpg 필요)
    - MySQLBackend: MySQL/MariaDB (pymysql 또는 aiomysql 필요)

Usage:
    # 직접 사용
    from bloom.db.backends import SQLiteBackend
    
    backend = SQLiteBackend("mydb.db")
    with backend.connection() as conn:
        conn.execute("SELECT * FROM users")
        users = conn.fetchall()
    
    # 팩토리를 통한 사용
    backend = get_backend("sqlite:///mydb.db")
    backend = get_backend("postgresql://user:pass@localhost/mydb")
    backend = get_backend("mysql://user:pass@localhost/mydb")
"""

from .base import (
    DatabaseBackend,
    Connection,
    AsyncConnection,
    ConnectionPool,
    ConnectionConfig,
)
from .sqlite import SQLiteBackend, SQLiteConnectionPool, SQLiteConnection

__all__ = [
    # Base
    "DatabaseBackend",
    "Connection",
    "AsyncConnection", 
    "ConnectionPool",
    "ConnectionConfig",
    # SQLite
    "SQLiteBackend",
    "SQLiteConnectionPool",
    "SQLiteConnection",
    # Factory
    "get_backend",
    "BACKENDS",
]

# Backend registry
BACKENDS: dict[str, type[DatabaseBackend]] = {
    "sqlite": SQLiteBackend,
}

# Optional: PostgreSQL
try:
    from .postgresql import PostgreSQLBackend, PostgreSQLConnectionPool, PostgreSQLConnection
    __all__.extend(["PostgreSQLBackend", "PostgreSQLConnectionPool", "PostgreSQLConnection"])
    BACKENDS["postgresql"] = PostgreSQLBackend
    BACKENDS["postgres"] = PostgreSQLBackend  # alias
except ImportError:
    PostgreSQLBackend = None  # type: ignore

# Optional: MySQL
try:
    from .mysql import MySQLBackend, MySQLConnectionPool, MySQLConnection
    __all__.extend(["MySQLBackend", "MySQLConnectionPool", "MySQLConnection"])
    BACKENDS["mysql"] = MySQLBackend
    BACKENDS["mariadb"] = MySQLBackend  # alias
except ImportError:
    MySQLBackend = None  # type: ignore


def get_backend(url: str, **kwargs) -> DatabaseBackend:
    """URL에서 적절한 백엔드를 반환합니다.
    
    Args:
        url: 데이터베이스 연결 URL
            - sqlite:///path/to/db.db
            - sqlite:///:memory:
            - postgresql://user:pass@host:port/database
            - mysql://user:pass@host:port/database
        **kwargs: 추가 연결 옵션
    
    Returns:
        DatabaseBackend: 연결된 백엔드 인스턴스
    
    Raises:
        ValueError: 지원하지 않는 스킴
        ImportError: 필요한 드라이버가 없는 경우
    
    Example:
        backend = get_backend("sqlite:///mydb.db")
        backend = get_backend("postgresql://user:pass@localhost/mydb", pool_size=10)
    """
    # URL 스킴 파싱
    if "://" not in url:
        raise ValueError(f"Invalid database URL: {url}")
    
    scheme = url.split("://")[0].lower()
    
    # sqlite3:// 도 지원
    if scheme == "sqlite3":
        scheme = "sqlite"
    
    if scheme not in BACKENDS:
        available = ", ".join(BACKENDS.keys())
        raise ValueError(
            f"Unsupported database scheme: {scheme}. "
            f"Available: {available}"
        )
    
    backend_class = BACKENDS[scheme]
    
    # 드라이버 설치 확인
    backend = backend_class(url, **kwargs)
    if not backend.check_driver():
        raise ImportError(backend.get_install_instruction())
    
    return backend
