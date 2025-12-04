"""Database Configuration"""

from __future__ import annotations

import os
import logging

from bloom.core import Configuration, Factory, PostConstruct, PreDestroy
from bloom.core.scope import ScopeEnum
from bloom.db import SessionFactory
from bloom.db.backends import SQLiteBackend
from bloom.db.session import AsyncSession, Session

logger = logging.getLogger(__name__)

# =============================================================================
# 환경 설정
# =============================================================================

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///demo.db?mode=memory")


@Configuration
class DatabaseConfig:
    """데이터베이스 설정 - SQLite"""

    @PostConstruct
    async def initialize(self):
        logger.info(f"DatabaseConfig initialized: {DATABASE_URL}")

    @PreDestroy
    async def cleanup(self):
        logger.info("DatabaseConfig cleanup")

    @Factory
    def session_factory(self) -> SessionFactory:
        """SessionFactory 팩토리 - SQLite"""
        logger.info(f"Creating SQLite SessionFactory: {DATABASE_URL}")
        backend = SQLiteBackend(DATABASE_URL)
        return SessionFactory(backend)

    @Factory(scope=ScopeEnum.CALL)
    def session(self, session_factory: SessionFactory) -> Session:
        logger.info(f"Creating Session: {DATABASE_URL}")
        return session_factory.create()

    @Factory(scope=ScopeEnum.CALL)
    async def async_session(self, session_factory: SessionFactory) -> AsyncSession:
        logger.info(f"Creating AsyncSession: {DATABASE_URL}")
        return await session_factory.create_async()
