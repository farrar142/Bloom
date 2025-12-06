"""
Migration: 0001_create_user
App: users
Created: 2025-12-06
"""

from bloom.db.migrations import (
    Migration,
    CreateTable,
)
from bloom.db.migrations.app import AppMigration


migration = AppMigration(
    name="0001_create_user",
    app_name="users",
    dependencies=[],  # 다른 앱에 의존하지 않음
    operations=[
        CreateTable(
            "user",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("name", "VARCHAR(100) NOT NULL"),
                ("email", "VARCHAR(255) NOT NULL UNIQUE"),
                ("is_active", "BOOLEAN DEFAULT 1"),
                ("created_at", "TIMESTAMP"),
                ("updated_at", "TIMESTAMP"),
            ],
        ),
    ],
)
