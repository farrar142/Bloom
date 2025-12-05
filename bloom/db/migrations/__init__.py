"""Migrations - Django-style database migrations"""

from .base import Migration, MigrationManager, MigrationRegistry
from .operations import (
    Operation,
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    AlterColumn,
    CreateIndex,
    DropIndex,
    RenameColumn,
    RenameTable,
    AddConstraint,
    DropConstraint,
    RunSQL,
    RunPython,
)
from .schema import SchemaEditor, SchemaDiff, SchemaIntrospector
from .generator import MigrationGenerator
from .app import (
    AppMigration,
    AppDependencyGraph,
    AppDependencyAnalyzer,
    AppMigrationGenerator,
    AppMigrationManager,
)

__all__ = [
    # Base
    "Migration",
    "MigrationManager",
    "MigrationRegistry",
    # Operations
    "Operation",
    "CreateTable",
    "DropTable",
    "AddColumn",
    "DropColumn",
    "AlterColumn",
    "CreateIndex",
    "DropIndex",
    "RenameColumn",
    "RenameTable",
    "AddConstraint",
    "DropConstraint",
    "RunSQL",
    "RunPython",
    # Schema
    "SchemaEditor",
    "SchemaDiff",
    "SchemaIntrospector",
    # Generator
    "MigrationGenerator",
    # App-based migrations
    "AppMigration",
    "AppDependencyGraph",
    "AppDependencyAnalyzer",
    "AppMigrationGenerator",
    "AppMigrationManager",
]
