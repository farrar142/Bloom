"""Notifications Service"""

from __future__ import annotations

import asyncio
import logging

from bloom.core import Service, PostConstruct, PreDestroy
from bloom.event import EventListener, Event
from bloom.task import TaskDecorator as Task

from .entity import Notification, NotificationType
from .repository import NotificationRepository
from ..users import UserRepository
from ..orders import OrderStatus

logger = logging.getLogger(__name__)


@Service
class NotificationService:
    """알림 서비스 - 이벤트 기반 + 태스크 큐"""

    notification_repo: NotificationRepository
    user_repo: UserRepository

    @PostConstruct
    async def initialize(self):
        logger.info("NotificationService initialized")

    @PreDestroy
    async def cleanup(self):
        logger.info("NotificationService cleanup")

    # =========================================================================
    # Event Listeners - 이벤트 수신 시 태스크 큐잉
    # =========================================================================

    @EventListener("user.created")
    async def on_user_created(self, event: Event):
        """사용자 생성 시 환영 이메일 발송"""
        logger.info(f"[EventListener] user.created - {event.payload}")
        await self.send_welcome_email.apply_async(
            args=(event.payload["user_id"], event.payload["email"])
        )

    @EventListener("order.created")
    async def on_order_created(self, event: Event):
        """주문 생성 시 주문 확인 알림 발송"""
        logger.info(f"[EventListener] order.created - {event.payload}")
        await self.send_order_confirmation.apply_async(
            args=(
                event.payload["user_id"],
                event.payload["order_id"],
                event.payload["total_amount"],
            )
        )

    @EventListener("order.status_changed")
    async def on_order_status_changed(self, event: Event):
        """주문 상태 변경 시 알림"""
        logger.info(f"[EventListener] order.status_changed - {event.payload}")

        if event.payload["new_status"] == OrderStatus.SHIPPED.value:
            await self.send_shipping_notification.apply_async(
                args=(event.payload["order_id"],)
            )

    # =========================================================================
    # Background Tasks - 워커에서 실행
    # =========================================================================

    @Task(queue="emails")
    async def send_welcome_email(self, user_id: int, email: str) -> dict:
        """환영 이메일 발송 (워커에서 실행)"""
        logger.info(f"[Task] Sending welcome email to {email}")
        await asyncio.sleep(1)  # 이메일 발송 시뮬레이션

        user = await self.user_repo.find_by_id(user_id)
        if user:
            notification = Notification()
            notification.user_id = user_id
            notification.type = NotificationType.EMAIL.value
            notification.title = "회원가입을 환영합니다!"
            notification.message = (
                f"{user.name}님, 가입을 환영합니다. 다양한 혜택을 누려보세요."
            )
            await self.notification_repo.save(notification)

        return {
            "status": "sent",
            "type": "welcome_email",
            "email": email,
        }

    @Task(queue="notifications")
    async def send_order_confirmation(
        self, user_id: int, order_id: int, total_amount: int
    ) -> dict:
        """주문 확인 알림 발송 (워커에서 실행)"""
        logger.info(f"[Task] Sending order confirmation for order {order_id}")
        await asyncio.sleep(0.5)

        user = await self.user_repo.find_by_id(user_id)
        if user:
            notification = Notification()
            notification.user_id = user_id
            notification.type = NotificationType.PUSH.value
            notification.title = "주문이 접수되었습니다"
            notification.message = (
                f"주문번호 {order_id}, 총 {total_amount:,}원 결제가 완료되었습니다."
            )
            await self.notification_repo.save(notification)

        return {
            "status": "sent",
            "type": "order_confirmation",
            "order_id": order_id,
        }

    @Task(queue="notifications")
    async def send_shipping_notification(self, order_id: int) -> dict:
        """배송 시작 알림 (워커에서 실행)"""
        logger.info(f"[Task] Sending shipping notification for order {order_id}")
        await asyncio.sleep(0.5)

        return {
            "status": "sent",
            "type": "shipping_notification",
            "order_id": order_id,
        }

    # =========================================================================
    # 일반 메서드
    # =========================================================================

    async def get_user_notifications(self, user_id: int) -> list[Notification]:
        """사용자 알림 목록"""
        return await self.notification_repo.find_by_user_id(user_id)
