"""SQL Dialect - Database-specific SQL generation"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .columns import Column, ForeignKey
    from .entity import EntityMeta


class Dialect(ABC):
    """SQL 방언 추상 베이스 클래스

    각 데이터베이스별 SQL 생성을 담당합니다.
    """

    name: str = "generic"
    param_style: str = ":"  # :name, ?, %s 등

    @abstractmethod
    def get_type_mapping(self, column: Column[Any]) -> str:
        """컬럼 타입을 DB 타입으로 변환"""
        ...

    @abstractmethod
    def quote_identifier(self, name: str) -> str:
        """식별자 이스케이프"""
        ...

    def format_param(self, name: str) -> str:
        """파라미터 포맷팅"""
        return f"{self.param_style}{name}"

    def create_table_sql(self, meta: EntityMeta) -> str:
        """CREATE TABLE SQL 생성"""
        columns_sql: list[str] = []
        constraints_sql: list[str] = []

        for name, column in meta.columns.items():
            col_def = self._get_column_definition(column)
            columns_sql.append(col_def)

            # FK 제약조건 수집
            from .columns import ForeignKey

            if isinstance(column, ForeignKey):
                constraints_sql.append(column.get_constraint_definition())

        all_parts = columns_sql + constraints_sql
        columns_str = ",\n    ".join(all_parts)

        return f"CREATE TABLE IF NOT EXISTS {self.quote_identifier(meta.table_name)} (\n    {columns_str}\n)"

    def drop_table_sql(self, table_name: str) -> str:
        """DROP TABLE SQL 생성"""
        return f"DROP TABLE IF EXISTS {self.quote_identifier(table_name)}"

    def insert_sql(self, meta: EntityMeta, columns: list[str]) -> str:
        """INSERT SQL 생성"""
        cols = ", ".join(self.quote_identifier(c) for c in columns)
        vals = ", ".join(self.format_param(c) for c in columns)
        return f"INSERT INTO {self.quote_identifier(meta.table_name)} ({cols}) VALUES ({vals})"

    def insert_returning_sql(self, meta: EntityMeta, columns: list[str]) -> str:
        """INSERT ... RETURNING SQL 생성 (PK 반환용)"""
        base = self.insert_sql(meta, columns)
        if meta.primary_key:
            return f"{base} RETURNING {self.quote_identifier(meta.primary_key)}"
        return base

    def update_sql(self, meta: EntityMeta, columns: list[str], pk_column: str) -> str:
        """UPDATE SQL 생성"""
        sets = ", ".join(
            f"{self.quote_identifier(c)} = {self.format_param(c)}" for c in columns
        )
        return (
            f"UPDATE {self.quote_identifier(meta.table_name)} "
            f"SET {sets} "
            f"WHERE {self.quote_identifier(pk_column)} = {self.format_param(pk_column)}"
        )

    def delete_sql(self, meta: EntityMeta, pk_column: str) -> str:
        """DELETE SQL 생성"""
        return (
            f"DELETE FROM {self.quote_identifier(meta.table_name)} "
            f"WHERE {self.quote_identifier(pk_column)} = {self.format_param(pk_column)}"
        )

    def select_sql(
        self,
        meta: EntityMeta,
        columns: list[str] | None = None,
        where: str | None = None,
        order_by: list[str] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> str:
        """SELECT SQL 생성"""
        cols = ", ".join(
            self.quote_identifier(c) for c in (columns or meta.column_names)
        )
        sql = f"SELECT {cols} FROM {self.quote_identifier(meta.table_name)}"

        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {', '.join(order_by)}"
        if limit is not None:
            sql += f" LIMIT {limit}"
        if offset is not None:
            sql += f" OFFSET {offset}"

        return sql

    def count_sql(self, meta: EntityMeta, where: str | None = None) -> str:
        """COUNT SQL 생성"""
        sql = f"SELECT COUNT(*) FROM {self.quote_identifier(meta.table_name)}"
        if where:
            sql += f" WHERE {where}"
        return sql

    def exists_sql(self, meta: EntityMeta, where: str) -> str:
        """EXISTS SQL 생성"""
        return f"SELECT EXISTS(SELECT 1 FROM {self.quote_identifier(meta.table_name)} WHERE {where})"

    def _get_column_definition(self, column: Column[Any]) -> str:
        """컬럼 정의 생성"""
        return column.get_column_definition()


class SQLiteDialect(Dialect):
    """SQLite 방언"""

    name = "sqlite"
    param_style = ":"

    _type_map = {
        "INTEGER": "INTEGER",
        "VARCHAR": "TEXT",
        "TEXT": "TEXT",
        "BOOLEAN": "INTEGER",
        "TIMESTAMP": "TEXT",
        "DECIMAL": "REAL",
        "JSON": "TEXT",
        "REAL": "REAL",
        "BLOB": "BLOB",
    }

    def get_type_mapping(self, column: Column[Any]) -> str:
        sql_type = column.sql_type.upper()
        for key, value in self._type_map.items():
            if key in sql_type:
                return value
        return "TEXT"

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def insert_returning_sql(self, meta: EntityMeta, columns: list[str]) -> str:
        """SQLite는 RETURNING 지원 (3.35+)"""
        return super().insert_returning_sql(meta, columns)


class PostgreSQLDialect(Dialect):
    """PostgreSQL 방언"""

    name = "postgresql"
    param_style = "$"  # PostgreSQL은 $1, $2 형식

    _type_map = {
        "INTEGER": "INTEGER",
        "VARCHAR": "VARCHAR",
        "TEXT": "TEXT",
        "BOOLEAN": "BOOLEAN",
        "TIMESTAMP": "TIMESTAMP",
        "DECIMAL": "DECIMAL",
        "JSON": "JSONB",
        "REAL": "REAL",
        "BLOB": "BYTEA",
    }

    def get_type_mapping(self, column: Column[Any]) -> str:
        sql_type = column.sql_type.upper()
        for key, value in self._type_map.items():
            if key in sql_type:
                return value
        return "TEXT"

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def format_param(self, name: str) -> str:
        # PostgreSQL은 이름 기반 파라미터 사용
        return f"%({name})s"


class MySQLDialect(Dialect):
    """MySQL 방언"""

    name = "mysql"
    param_style = "%"

    _type_map = {
        "INTEGER": "INT",
        "VARCHAR": "VARCHAR",
        "TEXT": "TEXT",
        "BOOLEAN": "TINYINT(1)",
        "TIMESTAMP": "DATETIME",
        "DECIMAL": "DECIMAL",
        "JSON": "JSON",
        "REAL": "DOUBLE",
        "BLOB": "BLOB",
    }

    def get_type_mapping(self, column: Column[Any]) -> str:
        sql_type = column.sql_type.upper()
        for key, value in self._type_map.items():
            if key in sql_type:
                return value
        return "TEXT"

    def quote_identifier(self, name: str) -> str:
        return f"`{name}`"

    def format_param(self, name: str) -> str:
        return f"%({name})s"

    def insert_returning_sql(self, meta: EntityMeta, columns: list[str]) -> str:
        """MySQL은 RETURNING 미지원 - LAST_INSERT_ID 사용"""
        return self.insert_sql(meta, columns)


# Dialect 팩토리
_dialects: dict[str, type[Dialect]] = {
    "sqlite": SQLiteDialect,
    "postgresql": PostgreSQLDialect,
    "postgres": PostgreSQLDialect,
    "mysql": MySQLDialect,
}


def get_dialect(name: str) -> Dialect:
    """이름으로 Dialect 인스턴스 반환"""
    dialect_cls = _dialects.get(name.lower())
    if dialect_cls is None:
        raise ValueError(f"Unknown dialect: {name}")
    return dialect_cls()


def register_dialect(name: str, dialect_cls: type[Dialect]) -> None:
    """새 Dialect 등록"""
    _dialects[name.lower()] = dialect_cls
