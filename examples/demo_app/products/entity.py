"""Products Entity"""

from __future__ import annotations

from bloom.db import (
    Entity,
    PrimaryKey,
    StringColumn,
    IntegerColumn,
    BooleanColumn,
    DateTimeColumn,
    TextColumn,
)


@Entity
class Product:
    """상품 엔티티"""

    id = PrimaryKey[int](auto_increment=True)
    name = StringColumn(nullable=False, max_length=200)
    description = TextColumn(nullable=True)
    price = IntegerColumn(nullable=False, default=0)
    stock = IntegerColumn(nullable=False, default=0)
    is_available = BooleanColumn(default=True)
    created_at = DateTimeColumn(auto_now_add=True)
