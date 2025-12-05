"""
Migration: 0001_create_notification
App: notifications
Created: 2025-12-06

의존성:
- users:0001_create_user (Notification.user_id FK)
"""

from bloom.db.migrations import (
    CreateTable,
)
from bloom.db.migrations.app import AppMigration


migration = AppMigration(
    name="0001_create_notification",
    app_name="notifications",
    dependencies=[
        "users:0001_create_user",  # user_id FK
    ],
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
                ("user_id", "INTEGER NOT NULL"),
            ],
            constraints=[
                "FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE",
            ],
        ),
    ],
)
