"""
Migration: 0001_create_notification
Created: 2025-12-04T15:32:03.343478
"""

from bloom.db.migrations import (
    Migration,
    CreateTable,
    DropTable,
    AddColumn,
    DropColumn,
    CreateIndex,
    DropIndex,
)


migration = Migration(
    name="0001_create_notification",
    dependencies=[],
    operations=[
        CreateTable(
            "notification",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("type", "VARCHAR(20) NOT NULL DEFAULT 'email'"),
                ("title", "VARCHAR(200) NOT NULL"),
                ("message", "TEXT NOT NULL"),
                ("is_read", "BOOLEAN DEFAULT 0"),
                ("created_at", "TIMESTAMP"),
                ("user_id", "INTEGER NOT NULL")
            ],
        ),
        CreateTable(
            "order",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("status", "VARCHAR(20) NOT NULL DEFAULT 'pending'"),
                ("total_amount", "INTEGER NOT NULL DEFAULT 0"),
                ("created_at", "TIMESTAMP"),
                ("updated_at", "TIMESTAMP"),
                ("user_id", "INTEGER NOT NULL")
            ],
        ),
        CreateTable(
            "orderitem",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("quantity", "INTEGER NOT NULL DEFAULT 1"),
                ("unit_price", "INTEGER NOT NULL DEFAULT 0"),
                ("order_id", "INTEGER NOT NULL"),
                ("product_id", "INTEGER NOT NULL")
            ],
        ),
        CreateTable(
            "product",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("name", "VARCHAR(200) NOT NULL"),
                ("description", "TEXT"),
                ("price", "INTEGER NOT NULL DEFAULT 0"),
                ("stock", "INTEGER NOT NULL DEFAULT 0"),
                ("is_available", "BOOLEAN DEFAULT 1"),
                ("created_at", "TIMESTAMP")
            ],
        ),
        CreateTable(
            "user",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("name", "VARCHAR(100) NOT NULL"),
                ("email", "VARCHAR(255) NOT NULL UNIQUE"),
                ("is_active", "BOOLEAN DEFAULT 1"),
                ("created_at", "TIMESTAMP"),
                ("updated_at", "TIMESTAMP")
            ],
        )
    ],
)