"""
Migration: 0001_create_order
App: orders
Created: 2025-12-06

의존성:
- users:0001_create_user (Order.user_id FK)
- products:0001_create_product (OrderItem.product_id FK)
"""

from bloom.db.migrations import (
    CreateTable,
)
from bloom.db.migrations.app import AppMigration


migration = AppMigration(
    name="0001_create_order",
    app_name="orders",
    dependencies=[
        "users:0001_create_user",  # user_id FK
        "products:0001_create_product",  # product_id FK
    ],
    operations=[
        CreateTable(
            "orders",  # 'order'는 SQL 예약어이므로 'orders' 사용
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("status", "VARCHAR(20) NOT NULL DEFAULT 'pending'"),
                ("total_amount", "INTEGER NOT NULL DEFAULT 0"),
                ("created_at", "TIMESTAMP"),
                ("updated_at", "TIMESTAMP"),
                ("user_id", "INTEGER NOT NULL"),
            ],
            constraints=[
                "FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE ON UPDATE CASCADE",
            ],
        ),
        CreateTable(
            "orderitem",
            columns=[
                ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("quantity", "INTEGER NOT NULL DEFAULT 1"),
                ("unit_price", "INTEGER NOT NULL DEFAULT 0"),
                ("order_id", "INTEGER NOT NULL"),
                ("product_id", "INTEGER NOT NULL"),
            ],
            constraints=[
                "FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE ON UPDATE CASCADE",
                "FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE ON UPDATE CASCADE",
            ],
        ),
    ],
)
