"""Orders Entity"""

from __future__ import annotations

from typing import TYPE_CHECKING
from enum import Enum

from bloom.db import (
    Entity,
    PrimaryKey,
    StringColumn,
    IntegerColumn,
    DateTimeColumn,
    ManyToOne,
    OneToMany,
    FetchType,
)

if TYPE_CHECKING:
    from ..users import User
    from ..products import Product


class OrderStatus(str, Enum):
    """주문 상태"""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@Entity
class Order:
    """주문 엔티티"""

    __app__ = "orders"

    id = PrimaryKey[int](auto_increment=True)
    status = StringColumn(
        nullable=False, default=OrderStatus.PENDING.value, max_length=20
    )
    total_amount = IntegerColumn(nullable=False, default=0)
    created_at = DateTimeColumn(auto_now_add=True)
    updated_at = DateTimeColumn(auto_now=True)

    # FK
    user_id = IntegerColumn(nullable=False)
    user = ManyToOne["User"](
        target="examples.demo_app.users.User",
        foreign_key="user_id",
        fetch=FetchType.LAZY,
    )

    # Relations
    items = OneToMany["OrderItem"](
        target="OrderItem",
        foreign_key="order_id",
        fetch=FetchType.LAZY,
    )


@Entity
class OrderItem:
    """주문 항목 엔티티"""

    __app__ = "orders"

    id = PrimaryKey[int](auto_increment=True)
    quantity = IntegerColumn(nullable=False, default=1)
    unit_price = IntegerColumn(nullable=False, default=0)

    # FK - Order
    order_id = IntegerColumn(nullable=False)
    order = ManyToOne["Order"](
        target=Order,
        foreign_key="order_id",
        fetch=FetchType.LAZY,
    )

    # FK - Product
    product_id = IntegerColumn(nullable=False)
    product = ManyToOne["Product"](
        target="examples.demo_app.products.Product",
        foreign_key="product_id",
        fetch=FetchType.LAZY,
    )
