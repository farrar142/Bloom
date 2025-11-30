"""SQL Dialects

데이터베이스별 SQL 방언 구현체입니다.

Usage:
    from bloom.db.dialects import SQLiteDialect, PostgreSQLDialect, MySQLDialect
    from bloom.db.dialects import get_dialect

    # 직접 인스턴스 생성
    dialect = PostgreSQLDialect()

    # 이름으로 생성
    dialect = get_dialect("postgresql")
"""

from .base import Dialect
from .sqlite import SQLiteDialect
from .postgresql import PostgreSQLDialect
from .mysql import MySQLDialect

# Dialect 레지스트리
_dialects: dict[str, type[Dialect]] = {
    "sqlite": SQLiteDialect,
    "sqlite3": SQLiteDialect,
    "postgresql": PostgreSQLDialect,
    "postgres": PostgreSQLDialect,
    "pg": PostgreSQLDialect,
    "mysql": MySQLDialect,
    "mariadb": MySQLDialect,
}


def get_dialect(name: str) -> Dialect:
    """이름으로 Dialect 인스턴스 반환

    Args:
        name: dialect 이름 (sqlite, postgresql, mysql 등)

    Returns:
        Dialect 인스턴스

    Raises:
        ValueError: 알 수 없는 dialect 이름

    Examples:
        >>> dialect = get_dialect("postgresql")
        >>> dialect.name
        'postgresql'
    """
    dialect_cls = _dialects.get(name.lower())
    if dialect_cls is None:
        available = ", ".join(sorted(set(_dialects.keys())))
        raise ValueError(f"Unknown dialect: {name}. Available: {available}")
    return dialect_cls()


def register_dialect(name: str, dialect_cls: type[Dialect]) -> None:
    """새 Dialect 등록

    Args:
        name: dialect 이름
        dialect_cls: Dialect 클래스
    """
    _dialects[name.lower()] = dialect_cls


__all__ = [
    "Dialect",
    "SQLiteDialect",
    "PostgreSQLDialect",
    "MySQLDialect",
    "get_dialect",
    "register_dialect",
]
