"""Users Repository"""

from __future__ import annotations

import logging
from typing import Optional
from datetime import datetime

from bloom.core import Repository, PostConstruct

from .entity import User

logger = logging.getLogger(__name__)


@Repository
class UserRepository:
    """사용자 저장소"""

    def __init__(self):
        self._data: dict[int, User] = {}
        self._next_id = 1

    @PostConstruct
    async def initialize(self):
        # 샘플 데이터 생성
        admin = User()
        admin.id = self._next_id
        admin.name = "관리자"
        admin.email = "admin@example.com"
        admin.is_active = True
        admin.created_at = datetime.now()
        self._data[admin.id] = admin
        self._next_id += 1
        logger.info("UserRepository initialized with sample data")

    async def save(self, user: User) -> User:
        if not user.id:
            user.id = self._next_id
            self._next_id += 1
            user.created_at = datetime.now()
        user.updated_at = datetime.now()
        self._data[user.id] = user
        return user

    async def find_by_id(self, user_id: int) -> Optional[User]:
        return self._data.get(user_id)

    async def find_by_email(self, email: str) -> Optional[User]:
        for user in self._data.values():
            if user.email == email:
                return user
        return None

    async def find_all(self) -> list[User]:
        return list(self._data.values())

    async def delete(self, user_id: int) -> bool:
        if user_id in self._data:
            del self._data[user_id]
            return True
        return False
