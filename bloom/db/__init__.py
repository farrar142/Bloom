"""bloom.db - Spring-style ORM with QueryDSL and Django migrations

Features:
- Entity/Column descriptors with type-safe field expressions
- CrudRepository pattern
- QueryDSL-style type-safe queries
- Dirty tracking for optimized updates
- Django-style migrations
- Django-style annotate/aggregate with GROUP BY
- Subquery support (IN, EXISTS, scalar)
- JOIN support (INNER, LEFT, RIGHT, FULL, CROSS)
- Window functions (ROW_NUMBER, RANK, LAG, LEAD, etc.)
"""

from .expressions import (
    FieldExpression,
    Condition,
    ConditionGroup,
    OrderBy,
    # Aggregate functions
    AggregateFunction,
    Count,
    Sum,
    Avg,
    Min,
    Max,
    HavingCondition,
    HavingConditionGroup,
    # Subquery
    Subquery,
    SubqueryCondition,
    SubqueryInCondition,
    ScalarSubquery,
    # JOIN
    JoinType,
    JoinClause,
    JoinCondition,
    on,
    # Window functions
    FrameBound,
    WindowFrame,
    WindowSpec,
    WindowFunction,
    RowNumber,
    Rank,
    DenseRank,
    NTile,
    PercentRank,
    CumeDist,
    Lag,
    Lead,
    FirstValue,
    LastValue,
    NthValue,
    SumOver,
    AvgOver,
    CountOver,
    MinOver,
    MaxOver,
)
from .columns import (
    Column,
    PrimaryKey,
    ForeignKey,
    ManyToOne,
    IntegerColumn,
    StringColumn,
    BooleanColumn,
    DateTimeColumn,
    DecimalColumn,
    TextColumn,
    JSONColumn,
    OneToMany,
    FetchType,
    TrackedList,
)
from .tracker import DirtyTracker
from .entity import Entity, EntityMeta, create
from .dialect import Dialect, SQLiteDialect, PostgreSQLDialect, MySQLDialect
from .query import QueryBuilder, Query, FilterCondition, JoinOnCondition
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
from .transaction import (
    Propagation,
    TransactionError,
    TransactionRequiredError,
    TransactionNotAllowedError,
    TransactionalElement,
    Transactional,
    TransactionContext,
    TransactionAdvice,
    create_transaction_method_advice,
    get_current_transaction,
    has_active_transaction,
)

__all__ = [
    # Expressions
    "FieldExpression",
    "Condition",
    "ConditionGroup",
    "OrderBy",
    # Aggregate functions
    "AggregateFunction",
    "Count",
    "Sum",
    "Avg",
    "Min",
    "Max",
    "HavingCondition",
    "HavingConditionGroup",
    # Subquery
    "Subquery",
    "SubqueryCondition",
    "SubqueryInCondition",
    "ScalarSubquery",
    # JOIN
    "JoinType",
    "JoinClause",
    "JoinCondition",
    "on",
    # Window functions
    "FrameBound",
    "WindowFrame",
    "WindowSpec",
    "WindowFunction",
    "RowNumber",
    "Rank",
    "DenseRank",
    "NTile",
    "PercentRank",
    "CumeDist",
    "Lag",
    "Lead",
    "FirstValue",
    "LastValue",
    "NthValue",
    "SumOver",
    "AvgOver",
    "CountOver",
    "MinOver",
    "MaxOver",
    # Columns
    "Column",
    "PrimaryKey",
    "ForeignKey",
    "ManyToOne",
    "IntegerColumn",
    "StringColumn",
    "BooleanColumn",
    "DateTimeColumn",
    "DecimalColumn",
    "TextColumn",
    "JSONColumn",
    "OneToMany",
    "FetchType",
    "TrackedList",
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
    "FilterCondition",
    "JoinOnCondition",
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
    # Transaction
    "Propagation",
    "TransactionError",
    "TransactionRequiredError",
    "TransactionNotAllowedError",
    "TransactionalElement",
    "Transactional",
    "TransactionContext",
    "TransactionAdvice",
    "create_transaction_method_advice",
    "get_current_transaction",
    "has_active_transaction",
]
