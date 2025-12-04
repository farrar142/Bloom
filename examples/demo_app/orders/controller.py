"""Orders Controller"""

from __future__ import annotations

from bloom.web import (
    Controller,
    GetMapping,
    PostMapping,
    PutMapping,
    RequestMapping,
    JSONResponse,
    PathVariable,
    Query,
    RequestField,
)

from .entity import OrderStatus
from .service import OrderService


@Controller
@RequestMapping("/api/orders")
class OrderController:
    """주문 API"""

    order_service: OrderService

    @GetMapping("")
    async def list_orders(self, user_id: Query[int | None] = None) -> JSONResponse:
        """주문 목록"""
        if user_id:
            orders = await self.order_service.get_user_orders(user_id)
        else:
            orders = await self.order_service.order_repo.find_all()

        return JSONResponse(
            {
                "orders": [
                    {
                        "id": o.id,
                        "user_id": o.user_id,
                        "status": o.status,
                        "total_amount": o.total_amount,
                        "created_at": (
                            o.created_at.isoformat() if o.created_at else None
                        ),
                    }
                    for o in orders
                ]
            }
        )

    @GetMapping("/{order_id}")
    async def get_order(self, order_id: PathVariable[int]) -> JSONResponse:
        """주문 상세"""
        order = await self.order_service.get_order(order_id)
        if not order:
            return JSONResponse({"error": "Order not found"}, status_code=404)
        return JSONResponse(
            {
                "id": order.id,
                "user_id": order.user_id,
                "status": order.status,
                "total_amount": order.total_amount,
                "created_at": (
                    order.created_at.isoformat() if order.created_at else None
                ),
            }
        )

    @PostMapping("")
    async def create_order(
        self,
        user_id: RequestField[int],
        items: RequestField[list[dict]],
    ) -> JSONResponse:
        """주문 생성

        Body:
            {
                "user_id": 1,
                "items": [
                    {"product_id": 1, "quantity": 2},
                    {"product_id": 2, "quantity": 1}
                ]
            }
        """
        try:
            order = await self.order_service.create_order(
                user_id=user_id,
                items=items,
            )
            return JSONResponse(
                {
                    "id": order.id,
                    "user_id": order.user_id,
                    "status": order.status,
                    "total_amount": order.total_amount,
                    "message": "Order created. Confirmation notification queued.",
                },
                status_code=201,
            )
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    @PutMapping("/{order_id}/status")
    async def update_order_status(
        self,
        order_id: PathVariable[int],
        status: RequestField[str],
    ) -> JSONResponse:
        """주문 상태 변경

        Body: {"status": "confirmed" | "shipped" | "delivered" | "cancelled"}
        """
        try:
            new_status = OrderStatus(status)

            order = await self.order_service.update_order_status(order_id, new_status)
            if not order:
                return JSONResponse({"error": "Order not found"}, status_code=404)

            return JSONResponse(
                {
                    "id": order.id,
                    "status": order.status,
                    "message": f"Order status updated to {order.status}",
                }
            )
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
