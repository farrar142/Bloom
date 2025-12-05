"""Users Entity"""

from __future__ import annotations

from bloom.db import (
    Entity,
    PrimaryKey,
    StringColumn,
    BooleanColumn,
    DateTimeColumn,
    OneToMany,
    FetchType,
)


@Entity
class User:
    """사용자 엔티티"""

    __app__ = "users"

    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(nullable=False, max_length=100)
    email = StringColumn(nullable=False, unique=True, max_length=255)
    is_active = BooleanColumn(default=True)
    created_at = DateTimeColumn(auto_now_add=True)
    updated_at = DateTimeColumn(auto_now=True)

    # Relations (문자열로 참조 - 순환 참조 방지)
    orders = OneToMany["Order"](
        target="examples.demo_app.orders.Order",
        foreign_key="user_id",
        fetch=FetchType.LAZY,
    )
    notifications = OneToMany["Notification"](
        target="examples.demo_app.notifications.Notification",
        foreign_key="user_id",
        fetch=FetchType.LAZY,
    )
