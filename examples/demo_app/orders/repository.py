"""Orders Repository"""

from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime

from bloom.core import Repository, PostConstruct

from .entity import Order, OrderStatus

logger = logging.getLogger(__name__)


@Repository
class OrderRepository:
    """주문 저장소"""

    def __init__(self):
        self._data: dict[int, Order] = {}
        self._next_id = 1

    @PostConstruct
    async def initialize(self):
        logger.info("OrderRepository initialized")

    async def save(self, order: Order) -> Order:
        if not order.id:
            order.id = self._next_id
            self._next_id += 1
            order.created_at = datetime.now()
        order.updated_at = datetime.now()
        self._data[order.id] = order
        return order

    async def find_by_id(self, order_id: int) -> Optional[Order]:
        return self._data.get(order_id)

    async def find_by_user_id(self, user_id: int) -> list[Order]:
        return [o for o in self._data.values() if o.user_id == user_id]

    async def find_all(self) -> list[Order]:
        return list(self._data.values())

    async def update_status(
        self, order_id: int, status: OrderStatus
    ) -> Optional[Order]:
        order = self._data.get(order_id)
        if order:
            order.status = status.value
            order.updated_at = datetime.now()
        return order
