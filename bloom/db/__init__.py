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

from typing import TYPE_CHECKING

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
]


def __getattr__(name: str):
    """Lazy import"""

    # Expressions
    if name in (
        "FieldExpression",
        "Condition",
        "ConditionGroup",
        "OrderBy",
        "AggregateFunction",
        "Count",
        "Sum",
        "Avg",
        "Min",
        "Max",
        "HavingCondition",
        "HavingConditionGroup",
        "Subquery",
        "SubqueryCondition",
        "SubqueryInCondition",
        "ScalarSubquery",
        "JoinType",
        "JoinClause",
        "JoinCondition",
        "on",
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
    ):
        from . import expressions

        return getattr(expressions, name)

    # Columns
    if name in (
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
    ):
        from . import columns

        return getattr(columns, name)

    # Tracking
    if name == "DirtyTracker":
        from .tracker import DirtyTracker

        return DirtyTracker

    # Entity
    if name in ("Entity", "EntityMeta", "create"):
        from . import entity

        return getattr(entity, name)

    # Dialect
    if name in ("Dialect", "SQLiteDialect", "PostgreSQLDialect", "MySQLDialect"):
        from . import dialect

        return getattr(dialect, name)

    # Query
    if name in ("QueryBuilder", "Query", "FilterCondition", "JoinOnCondition"):
        from . import query

        return getattr(query, name)

    # Session
    if name in ("Session", "AsyncSession", "SessionFactory"):
        from . import session

        return getattr(session, name)

    # Repository
    if name in ("CrudRepository", "Repository"):
        from . import repository

        return getattr(repository, name)

    # Migrations
    if name in (
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
    ):
        from . import migrations

        return getattr(migrations, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# TYPE_CHECKING용 (IDE 지원)
if TYPE_CHECKING:
    from .expressions import (
        FieldExpression,
        Condition,
        ConditionGroup,
        OrderBy,
        AggregateFunction,
        Count,
        Sum,
        Avg,
        Min,
        Max,
        HavingCondition,
        HavingConditionGroup,
        Subquery,
        SubqueryCondition,
        SubqueryInCondition,
        ScalarSubquery,
        JoinType,
        JoinClause,
        JoinCondition,
        on,
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
