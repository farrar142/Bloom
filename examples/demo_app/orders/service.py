"""Orders Service"""

from __future__ import annotations

import logging
from typing import Optional

from bloom.core import Service, PostConstruct
from bloom.event import EventBus, Event

from .entity import Order, OrderStatus
from .repository import OrderRepository
from ..users import UserRepository
from ..products import ProductService

logger = logging.getLogger(__name__)


@Service
class OrderService:
    """주문 서비스"""

    order_repo: OrderRepository
    event_bus: EventBus
    user_repo: UserRepository
    product_service: ProductService

    @PostConstruct
    async def initialize(self):
        logger.info("OrderService initialized")

    async def create_order(
        self,
        user_id: int,
        items: list[dict],  # [{"product_id": 1, "quantity": 2}, ...]
    ) -> Order:
        """주문 생성"""
        # 사용자 확인
        user = await self.user_repo.find_by_id(user_id)
        if not user:
            raise ValueError(f"User not found: {user_id}")

        # 재고 확인 및 총액 계산
        total = 0
        for item in items:
            product = await self.product_service.get_product(item["product_id"])
            if not product:
                raise ValueError(f"Product not found: {item['product_id']}")
            if not await self.product_service.check_stock(
                item["product_id"], item["quantity"]
            ):
                raise ValueError(f"Insufficient stock for product: {product.name}")
            total += product.price * item["quantity"]

        # 재고 차감
        for item in items:
            await self.product_service.reserve_stock(
                item["product_id"], item["quantity"]
            )

        # 주문 생성
        order = Order()
        order.user_id = user_id
        order.status = OrderStatus.PENDING.value
        order.total_amount = total
        order = await self.order_repo.save(order)

        # 이벤트 발행
        await self.event_bus.publish(
            Event(
                event_type="order.created",
                payload={
                    "order_id": order.id,
                    "user_id": user_id,
                    "total_amount": total,
                    "items": items,
                },
            )
        )

        logger.info(f"Order created: {order.id} - total: {total:,}원")
        return order

    async def get_order(self, order_id: int) -> Optional[Order]:
        """주문 조회"""
        return await self.order_repo.find_by_id(order_id)

    async def get_user_orders(self, user_id: int) -> list[Order]:
        """사용자 주문 목록"""
        return await self.order_repo.find_by_user_id(user_id)

    async def update_order_status(
        self, order_id: int, new_status: OrderStatus
    ) -> Optional[Order]:
        """주문 상태 변경"""
        order = await self.order_repo.find_by_id(order_id)
        if not order:
            return None

        old_status = order.status
        order = await self.order_repo.update_status(order_id, new_status)

        # 이벤트 발행
        await self.event_bus.publish(
            Event(
                event_type="order.status_changed",
                payload={
                    "order_id": order_id,
                    "old_status": old_status,
                    "new_status": new_status.value,
                },
            )
        )

        return order
