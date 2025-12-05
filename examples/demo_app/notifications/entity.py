"""Notifications Entity"""

from __future__ import annotations

from typing import TYPE_CHECKING
from enum import Enum

from bloom.db import (
    Entity,
    PrimaryKey,
    StringColumn,
    IntegerColumn,
    BooleanColumn,
    DateTimeColumn,
    TextColumn,
    ManyToOne,
    FetchType,
)

if TYPE_CHECKING:
    from ..users import User


class NotificationType(str, Enum):
    """알림 타입"""

    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


@Entity
class Notification:
    """알림 엔티티"""

    __app__ = "notifications"

    id = PrimaryKey[int](auto_increment=True)
    type = StringColumn(
        nullable=False, max_length=20, default=NotificationType.EMAIL.value
    )
    title = StringColumn(nullable=False, max_length=200)
    message = TextColumn(nullable=False)
    is_read = BooleanColumn(default=False)
    created_at = DateTimeColumn(auto_now_add=True)

    # FK
    user_id = IntegerColumn(nullable=False)
    user = ManyToOne["User"](
        target="examples.demo_app.users.User",
        foreign_key="user_id",
        fetch=FetchType.LAZY,
    )
