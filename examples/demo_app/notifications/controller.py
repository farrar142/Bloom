"""Notifications Controller"""

from __future__ import annotations

from bloom.web import (
    Controller,
    GetMapping,
    RequestMapping,
    JSONResponse,
    Query,
)

from .service import NotificationService


@Controller
@RequestMapping("/api/notifications")
class NotificationController:
    """알림 API"""

    notification_service: NotificationService

    @GetMapping("")
    async def list_notifications(self, user_id: Query[int]) -> JSONResponse:
        """사용자 알림 목록"""
        notifications = await self.notification_service.get_user_notifications(user_id)
        return JSONResponse(
            {
                "notifications": [
                    {
                        "id": n.id,
                        "type": n.type,
                        "title": n.title,
                        "message": n.message,
                        "is_read": n.is_read,
                        "created_at": (
                            n.created_at.isoformat() if n.created_at else None
                        ),
                    }
                    for n in notifications
                ]
            }
        )
