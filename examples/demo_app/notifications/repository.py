"""Notifications Repository"""

from __future__ import annotations

import logging
from datetime import datetime

from bloom.core import Repository, PostConstruct

from .entity import Notification

logger = logging.getLogger(__name__)


@Repository
class NotificationRepository:
    """알림 저장소"""

    def __init__(self):
        self._data: dict[int, Notification] = {}
        self._next_id = 1

    @PostConstruct
    async def initialize(self):
        logger.info("NotificationRepository initialized")

    async def save(self, notification: Notification) -> Notification:
        if not notification.id:
            notification.id = self._next_id
            self._next_id += 1
            notification.created_at = datetime.now()
        self._data[notification.id] = notification
        return notification

    async def find_by_user_id(self, user_id: int) -> list[Notification]:
        return [n for n in self._data.values() if n.user_id == user_id]

    async def mark_as_read(self, notification_id: int) -> bool:
        notification = self._data.get(notification_id)
        if notification:
            notification.is_read = True
            return True
        return False
