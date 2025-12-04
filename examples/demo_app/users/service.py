"""Users Service"""

from __future__ import annotations

import logging
from typing import Optional

from bloom.core import Service, PostConstruct
from bloom.event import EventBus, Event

from .entity import User
from .repository import UserRepository

logger = logging.getLogger(__name__)


@Service
class UserService:
    """사용자 서비스"""

    user_repo: UserRepository
    event_bus: EventBus

    @PostConstruct
    async def initialize(self):
        logger.info("UserService initialized")

    async def create_user(self, name: str, email: str) -> User:
        """사용자 생성"""
        # 중복 체크
        existing = await self.user_repo.find_by_email(email)
        if existing:
            raise ValueError(f"Email already exists: {email}")

        # 생성
        user = User()
        user.name = name
        user.email = email
        user.is_active = True
        user = await self.user_repo.save_async(user)

        # 이벤트 발행
        await self.event_bus.publish(
            Event(
                event_type="user.created",
                payload={
                    "user_id": user.id,
                    "name": user.name,
                    "email": user.email,
                },
            )
        )

        logger.info(f"User created: {user.id} - {user.name}")
        return user

    async def get_user(self, user_id: int) -> Optional[User]:
        """사용자 조회"""
        return await self.user_repo.find_by_id_async(user_id)

    async def get_all_users(self) -> list[User]:
        """모든 사용자 조회"""
        return await self.user_repo.find_all_async()
