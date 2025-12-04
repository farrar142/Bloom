"""Schema utilities - SchemaEditor, SchemaDiff, SchemaIntrospector"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
import sqlite3

if TYPE_CHECKING:
    from ..dialect import Dialect
    from ..session import Connection
    from ..entity import EntityMeta


# =============================================================================
# Schema Information
# =============================================================================


@dataclass
class ColumnInfo:
    """컬럼 정보"""

    name: str
    type: str
    nullable: bool
    default: Any
    primary_key: bool


@dataclass
class TableInfo:
    """테이블 정보"""

    name: str
    columns: dict[str, ColumnInfo] = field(default_factory=dict)
    indexes: list[str] = field(default_factory=list)
    foreign_keys: list[tuple[str, str, str]] = field(
        default_factory=list
    )  # (column, ref_table, ref_column)


@dataclass
class SchemaDiff:
    """스키마 차이점"""

    tables_to_create: list[str] = field(default_factory=list)
    tables_to_drop: list[str] = field(default_factory=list)
    columns_to_add: list[tuple[str, str, str]] = field(
        default_factory=list
    )  # (table, column, definition)
    columns_to_drop: list[tuple[str, str]] = field(
        default_factory=list
    )  # (table, column)
    columns_to_alter: list[tuple[str, str, str, str]] = field(
        default_factory=list
    )  # (table, column, old_def, new_def)
    indexes_to_create: list[tuple[str, str, list[str]]] = field(
        default_factory=list
    )  # (table, index_name, columns)
    indexes_to_drop: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(
            [
                self.tables_to_create,
                self.tables_to_drop,
                self.columns_to_add,
                self.columns_to_drop,
                self.columns_to_alter,
                self.indexes_to_create,
                self.indexes_to_drop,
            ]
        )


# =============================================================================
# Schema Introspector
# =============================================================================


class SchemaIntrospector:
    """데이터베이스 스키마 검사

    현재 DB의 스키마 정보를 읽어옵니다.
    """

    def __init__(self, connection: Connection):
        self._connection = connection

    def get_tables(self) -> list[str]:
        """모든 테이블 목록"""
        result = self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row["name"] for row in result.fetchall()]

    def get_table_info(self, table_name: str) -> TableInfo:
        """테이블 상세 정보"""
        info = TableInfo(name=table_name)

        # 컬럼 정보 (PRAGMA table_info returns: cid, name, type, notnull, dflt_value, pk)
        result = self._connection.execute(f"PRAGMA table_info({table_name})")
        for row in result.fetchall():
            col = ColumnInfo(
                name=row["name"],
                type=row["type"],
                nullable=not row["notnull"],
                default=row["dflt_value"],
                primary_key=bool(row["pk"]),
            )
            info.columns[col.name] = col

        # 인덱스 정보 (PRAGMA index_list returns: seq, name, unique, origin, partial)
        result = self._connection.execute(f"PRAGMA index_list({table_name})")
        for row in result.fetchall():
            info.indexes.append(row["name"])

        # FK 정보 (PRAGMA foreign_key_list returns: id, seq, table, from, to, on_update, on_delete, match)
        result = self._connection.execute(f"PRAGMA foreign_key_list({table_name})")
        for row in result.fetchall():
            info.foreign_keys.append((row["from"], row["table"], row["to"]))

        return info

    def get_all_schema(self) -> dict[str, TableInfo]:
        """전체 스키마 정보"""
        tables = self.get_tables()
        return {name: self.get_table_info(name) for name in tables}

    def compare_with_models(self, entity_metas: list[EntityMeta]) -> SchemaDiff:
        """모델과 DB 스키마 비교"""
        from ..entity import EntityMeta

        diff = SchemaDiff()
        current_tables = set(self.get_tables())
        model_tables = {meta.table_name: meta for meta in entity_metas}

        # 새로 생성할 테이블
        for table_name in model_tables:
            if table_name not in current_tables:
                diff.tables_to_create.append(table_name)

        # 삭제할 테이블 (선택적 - 보통 자동 삭제는 안 함)
        # for table_name in current_tables:
        #     if table_name not in model_tables:
        #         diff.tables_to_drop.append(table_name)

        # 컬럼 비교
        for table_name, meta in model_tables.items():
            if table_name not in current_tables:
                continue

            table_info = self.get_table_info(table_name)
            current_columns = set(table_info.columns.keys())
            model_columns = set(meta.columns.keys())

            # 추가할 컬럼
            for col_name in model_columns - current_columns:
                column = meta.columns[col_name]
                diff.columns_to_add.append(
                    (table_name, col_name, column.get_column_definition())
                )

            # 삭제할 컬럼
            for col_name in current_columns - model_columns:
                diff.columns_to_drop.append((table_name, col_name))

        return diff


# =============================================================================
# Schema Editor
# =============================================================================


class SchemaEditor:
    """스키마 변경 실행기

    DDL 명령을 실행합니다.
    """

    def __init__(self, connection: Connection):
        self._connection = connection

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """SQL 실행"""
        return self._connection.execute(sql, params)

    def create_table(
        self,
        table_name: str,
        columns: list[tuple[str, str]],
        constraints: list[str] | None = None,
    ) -> None:
        """테이블 생성"""
        col_defs = [f"{name} {definition}" for name, definition in columns]
        all_defs = col_defs + (constraints or [])
        col_str = ",\n    ".join(all_defs)
        sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" (\n    {col_str}\n)'
        self.execute(sql)

    def drop_table(self, table_name: str) -> None:
        """테이블 삭제"""
        self.execute(f'DROP TABLE IF EXISTS "{table_name}"')

    def rename_table(self, old_name: str, new_name: str) -> None:
        """테이블 이름 변경"""
        self.execute(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"')

    def add_column(
        self, table_name: str, column_name: str, column_definition: str
    ) -> None:
        """컬럼 추가"""
        self.execute(
            f'ALTER TABLE "{table_name}" ADD COLUMN {column_name} {column_definition}'
        )

    def drop_column(self, table_name: str, column_name: str) -> None:
        """컬럼 삭제 (SQLite 3.35+)"""
        self.execute(f'ALTER TABLE "{table_name}" DROP COLUMN {column_name}')

    def rename_column(self, table_name: str, old_name: str, new_name: str) -> None:
        """컬럼 이름 변경"""
        self.execute(
            f'ALTER TABLE "{table_name}" RENAME COLUMN {old_name} TO {new_name}'
        )

    def alter_column(
        self, table_name: str, column_name: str, new_definition: str
    ) -> None:
        """컬럼 변경 (SQLite는 제한적 - 테이블 재생성 필요)

        Note: SQLite는 ALTER COLUMN을 지원하지 않아 테이블 재생성이 필요합니다.
        PostgreSQL, MySQL 등에서는 직접 ALTER를 사용합니다.
        """
        # SQLite 테이블 재생성 방식
        # 1. 임시 테이블 생성
        # 2. 데이터 복사
        # 3. 원본 삭제
        # 4. 임시 테이블 이름 변경

        # 간단한 구현 - 실제로는 더 복잡한 로직 필요
        raise NotImplementedError(
            "ALTER COLUMN is not directly supported in SQLite. Consider table recreation."
        )

    def create_index(
        self,
        table_name: str,
        index_name: str,
        columns: list[str],
        unique: bool = False,
    ) -> None:
        """인덱스 생성"""
        unique_str = "UNIQUE " if unique else ""
        cols = ", ".join(columns)
        self.execute(
            f'CREATE {unique_str}INDEX IF NOT EXISTS {index_name} ON "{table_name}" ({cols})'
        )

    def drop_index(self, index_name: str) -> None:
        """인덱스 삭제"""
        self.execute(f"DROP INDEX IF EXISTS {index_name}")

    def add_constraint(
        self, table_name: str, constraint_name: str, constraint_sql: str
    ) -> None:
        """제약조건 추가 (SQLite는 제한적)"""
        # SQLite는 ADD CONSTRAINT를 지원하지 않음 - 테이블 재생성 필요
        raise NotImplementedError(
            "ADD CONSTRAINT is not supported in SQLite. Consider table recreation."
        )

    def drop_constraint(self, table_name: str, constraint_name: str) -> None:
        """제약조건 삭제"""
        raise NotImplementedError(
            "DROP CONSTRAINT is not supported in SQLite. Consider table recreation."
        )
