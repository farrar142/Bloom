"""Migration operations - DDL commands"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..dialect import Dialect
    from ..columns import Column
    from .schema import SchemaEditor


class Operation(ABC):
    """마이그레이션 연산 추상 베이스"""

    @abstractmethod
    def forward(self, schema: SchemaEditor) -> None:
        """순방향 마이그레이션 실행"""
        ...

    @abstractmethod
    def backward(self, schema: SchemaEditor) -> None:
        """역방향 마이그레이션 실행 (롤백)"""
        ...

    @abstractmethod
    def describe(self) -> str:
        """연산 설명"""
        ...

    @abstractmethod
    def to_sql(self, dialect: Dialect | None) -> str:
        """SQL 문 생성"""
        ...


@dataclass
class CreateTable(Operation):
    """테이블 생성

    Examples:
        CreateTable(
            "users",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("name", "VARCHAR(100) NOT NULL"),
                ("email", "VARCHAR(255) UNIQUE"),
            ]
        )
    """

    table_name: str
    columns: list[tuple[str, str]]  # [(name, definition), ...]
    constraints: list[str] = field(default_factory=list)

    def forward(self, schema: SchemaEditor) -> None:
        schema.create_table(self.table_name, self.columns, self.constraints)

    def backward(self, schema: SchemaEditor) -> None:
        schema.drop_table(self.table_name)

    def describe(self) -> str:
        return f"Create table {self.table_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """CREATE TABLE SQL 생성"""
        # 테이블 이름을 인용부호로 감싸서 예약어 충돌 방지
        quoted_table = f'"{self.table_name}"'
        col_defs = [f"    {name} {definition}" for name, definition in self.columns]
        if self.constraints:
            col_defs.extend(f"    {c}" for c in self.constraints)
        cols_sql = ",\n".join(col_defs)
        return f"CREATE TABLE {quoted_table} (\n{cols_sql}\n)"


@dataclass
class DropTable(Operation):
    """테이블 삭제"""

    table_name: str
    # 롤백용 컬럼 정의 (선택적)
    columns: list[tuple[str, str]] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)

    def forward(self, schema: SchemaEditor) -> None:
        schema.drop_table(self.table_name)

    def backward(self, schema: SchemaEditor) -> None:
        if self.columns:
            schema.create_table(self.table_name, self.columns, self.constraints)

    def describe(self) -> str:
        return f"Drop table {self.table_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """DROP TABLE SQL 생성"""
        return f'DROP TABLE "{self.table_name}"'


@dataclass
class AddColumn(Operation):
    """컬럼 추가"""

    table_name: str
    column_name: str
    column_definition: str

    def forward(self, schema: SchemaEditor) -> None:
        schema.add_column(self.table_name, self.column_name, self.column_definition)

    def backward(self, schema: SchemaEditor) -> None:
        schema.drop_column(self.table_name, self.column_name)

    def describe(self) -> str:
        return f"Add column {self.column_name} to {self.table_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """ALTER TABLE ADD COLUMN SQL 생성"""
        return f'ALTER TABLE "{self.table_name}" ADD COLUMN {self.column_name} {self.column_definition}'


@dataclass
class DropColumn(Operation):
    """컬럼 삭제"""

    table_name: str
    column_name: str
    # 롤백용 컬럼 정의
    column_definition: str = ""

    def forward(self, schema: SchemaEditor) -> None:
        schema.drop_column(self.table_name, self.column_name)

    def backward(self, schema: SchemaEditor) -> None:
        if self.column_definition:
            schema.add_column(self.table_name, self.column_name, self.column_definition)

    def describe(self) -> str:
        return f"Drop column {self.column_name} from {self.table_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """ALTER TABLE DROP COLUMN SQL 생성"""
        return f'ALTER TABLE "{self.table_name}" DROP COLUMN {self.column_name}'


@dataclass
class AlterColumn(Operation):
    """컬럼 변경"""

    table_name: str
    column_name: str
    new_definition: str
    old_definition: str = ""  # 롤백용

    def forward(self, schema: SchemaEditor) -> None:
        schema.alter_column(self.table_name, self.column_name, self.new_definition)

    def backward(self, schema: SchemaEditor) -> None:
        if self.old_definition:
            schema.alter_column(self.table_name, self.column_name, self.old_definition)

    def describe(self) -> str:
        return f"Alter column {self.column_name} in {self.table_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """ALTER TABLE ALTER COLUMN SQL 생성"""
        return f'ALTER TABLE "{self.table_name}" ALTER COLUMN {self.column_name} {self.new_definition}'


@dataclass
class RenameColumn(Operation):
    """컬럼 이름 변경"""

    table_name: str
    old_name: str
    new_name: str

    def forward(self, schema: SchemaEditor) -> None:
        schema.rename_column(self.table_name, self.old_name, self.new_name)

    def backward(self, schema: SchemaEditor) -> None:
        schema.rename_column(self.table_name, self.new_name, self.old_name)

    def describe(self) -> str:
        return f"Rename column {self.old_name} to {self.new_name} in {self.table_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """ALTER TABLE RENAME COLUMN SQL 생성"""
        return f'ALTER TABLE "{self.table_name}" RENAME COLUMN {self.old_name} TO {self.new_name}'


@dataclass
class RenameTable(Operation):
    """테이블 이름 변경"""

    old_name: str
    new_name: str

    def forward(self, schema: SchemaEditor) -> None:
        schema.rename_table(self.old_name, self.new_name)

    def backward(self, schema: SchemaEditor) -> None:
        schema.rename_table(self.new_name, self.old_name)

    def describe(self) -> str:
        return f"Rename table {self.old_name} to {self.new_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """ALTER TABLE RENAME SQL 생성"""
        return f'ALTER TABLE "{self.old_name}" RENAME TO "{self.new_name}"'


@dataclass
class CreateIndex(Operation):
    """인덱스 생성"""

    table_name: str
    index_name: str
    columns: list[str]
    unique: bool = False

    def forward(self, schema: SchemaEditor) -> None:
        schema.create_index(self.table_name, self.index_name, self.columns, self.unique)

    def backward(self, schema: SchemaEditor) -> None:
        schema.drop_index(self.index_name)

    def describe(self) -> str:
        unique_str = "unique " if self.unique else ""
        return f"Create {unique_str}index {self.index_name} on {self.table_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """CREATE INDEX SQL 생성"""
        unique_str = "UNIQUE " if self.unique else ""
        cols = ", ".join(self.columns)
        return f'CREATE {unique_str}INDEX {self.index_name} ON "{self.table_name}" ({cols})'


@dataclass
class DropIndex(Operation):
    """인덱스 삭제"""

    index_name: str
    # 롤백용
    table_name: str = ""
    columns: list[str] = field(default_factory=list)
    unique: bool = False

    def forward(self, schema: SchemaEditor) -> None:
        schema.drop_index(self.index_name)

    def backward(self, schema: SchemaEditor) -> None:
        if self.table_name and self.columns:
            schema.create_index(
                self.table_name, self.index_name, self.columns, self.unique
            )

    def describe(self) -> str:
        return f"Drop index {self.index_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """DROP INDEX SQL 생성"""
        return f"DROP INDEX {self.index_name}"


@dataclass
class AddConstraint(Operation):
    """제약조건 추가"""

    table_name: str
    constraint_name: str
    constraint_sql: str

    def forward(self, schema: SchemaEditor) -> None:
        schema.add_constraint(
            self.table_name, self.constraint_name, self.constraint_sql
        )

    def backward(self, schema: SchemaEditor) -> None:
        schema.drop_constraint(self.table_name, self.constraint_name)

    def describe(self) -> str:
        return f"Add constraint {self.constraint_name} to {self.table_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """ALTER TABLE ADD CONSTRAINT SQL 생성"""
        return f'ALTER TABLE "{self.table_name}" ADD CONSTRAINT {self.constraint_name} {self.constraint_sql}'


@dataclass
class DropConstraint(Operation):
    """제약조건 삭제"""

    table_name: str
    constraint_name: str
    constraint_sql: str = ""  # 롤백용

    def forward(self, schema: SchemaEditor) -> None:
        schema.drop_constraint(self.table_name, self.constraint_name)

    def backward(self, schema: SchemaEditor) -> None:
        if self.constraint_sql:
            schema.add_constraint(
                self.table_name, self.constraint_name, self.constraint_sql
            )

    def describe(self) -> str:
        return f"Drop constraint {self.constraint_name} from {self.table_name}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """ALTER TABLE DROP CONSTRAINT SQL 생성"""
        return f'ALTER TABLE "{self.table_name}" DROP CONSTRAINT {self.constraint_name}'


@dataclass
class RunSQL(Operation):
    """SQL 직접 실행"""

    sql: str
    reverse_sql: str = ""

    def forward(self, schema: SchemaEditor) -> None:
        schema.execute(self.sql)

    def backward(self, schema: SchemaEditor) -> None:
        if self.reverse_sql:
            schema.execute(self.reverse_sql)

    def describe(self) -> str:
        return f"Run SQL: {self.sql[:50]}..."

    def to_sql(self, dialect: Dialect | None) -> str:
        """직접 SQL 반환"""
        return self.sql


@dataclass
class RunPython(Operation):
    """Python 코드 실행"""

    code: Callable[[SchemaEditor], None]
    reverse_code: Callable[[SchemaEditor], None] | None = None

    def forward(self, schema: SchemaEditor) -> None:
        self.code(schema)

    def backward(self, schema: SchemaEditor) -> None:
        if self.reverse_code:
            self.reverse_code(schema)

    def describe(self) -> str:
        return f"Run Python: {self.code.__name__}"

    def to_sql(self, dialect: Dialect | None) -> str:
        """Python 코드는 SQL로 변환 불가"""
        return f"-- Python code: {self.code.__name__} (cannot be represented as SQL)"
