"""
Migration: 0001_create_product
App: products
Created: 2025-12-06
"""

from bloom.db.migrations import (
    CreateTable,
)
from bloom.db.migrations.app import AppMigration


migration = AppMigration(
    name="0001_create_product",
    app_name="products",
    dependencies=[],  # 다른 앱에 의존하지 않음
    operations=[
        CreateTable(
            "product",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("name", "VARCHAR(200) NOT NULL"),
                ("description", "TEXT"),
                ("price", "INTEGER NOT NULL DEFAULT 0"),
                ("stock", "INTEGER NOT NULL DEFAULT 0"),
                ("is_available", "BOOLEAN DEFAULT 1"),
                ("created_at", "TIMESTAMP"),
            ],
        ),
    ],
)
