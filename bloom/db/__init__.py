"""bloom.db - Spring-style ORM with QueryDSL and Django migrations

Features:
- Entity/Column descriptors with type-safe field expressions
- CrudRepository pattern
- QueryDSL-style type-safe queries
- Dirty tracking for optimized updates
- Django-style migrations
"""

from .expressions import (
    FieldExpression,
    Condition,
    ConditionGroup,
    OrderBy,
)
from .columns import (
    Column,
    PrimaryKey,
    ForeignKey,
    IntegerColumn,
    StringColumn,
    BooleanColumn,
    DateTimeColumn,
    DecimalColumn,
    TextColumn,
    JSONColumn,
    OneToMany,
)
from .tracker import DirtyTracker
from .entity import Entity, EntityMeta, create
from .dialect import Dialect, SQLiteDialect, PostgreSQLDialect, MySQLDialect
from .query import QueryBuilder, Query
from .session import Session, AsyncSession, SessionFactory
from .repository import CrudRepository, Repository
from .migrations import (
    Migration,
    MigrationManager,
    MigrationRegistry,
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    AlterColumn,
    CreateIndex,
    DropIndex,
)

__all__ = [
    # Expressions
    "FieldExpression",
    "Condition",
    "ConditionGroup",
    "OrderBy",
    # Columns
    "Column",
    "PrimaryKey",
    "ForeignKey",
    "IntegerColumn",
    "StringColumn",
    "BooleanColumn",
    "DateTimeColumn",
    "DecimalColumn",
    "TextColumn",
    "JSONColumn",
    "OneToMany",
    # Tracking
    "DirtyTracker",
    # Entity
    "Entity",
    "EntityMeta",
    "create",
    # Dialect
    "Dialect",
    "SQLiteDialect",
    "PostgreSQLDialect",
    "MySQLDialect",
    # Query
    "QueryBuilder",
    "Query",
    # Session
    "Session",
    "AsyncSession",
    "SessionFactory",
    # Repository
    "CrudRepository",
    "Repository",
    # Migrations
    "Migration",
    "MigrationManager",
    "MigrationRegistry",
    "CreateTable",
    "DropTable",
    "AddColumn",
    "DropColumn",
    "AlterColumn",
    "CreateIndex",
    "DropIndex",
]
