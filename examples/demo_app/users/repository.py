"""Users Repository"""

import logging
from typing import Optional
from datetime import datetime

from bloom.core import Repository, PostConstruct
from bloom.db import Query
from bloom.db.repository import CrudRepository
from .entity import User

logger = logging.getLogger(__name__)


# @Repository
class UserRepository(CrudRepository[User, int]):
    """사용자 저장소"""

    async def find_by_email(self, email: str) -> User | None:
        return await self.find_one_by_async(email=email)
