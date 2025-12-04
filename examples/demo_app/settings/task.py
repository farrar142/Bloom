"""Task Configuration"""

from __future__ import annotations

import os
import logging

from bloom.core import Configuration, Factory, PostConstruct, PreDestroy
from bloom.task.broker import TaskBroker
from bloom.task.backend import TaskBackend
from bloom.task.backends import RedisBroker, RedisBackend

logger = logging.getLogger(__name__)

# =============================================================================
# 환경 설정
# =============================================================================

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_DB = os.environ.get("REDIS_DB", "0")
REDIS_URL = os.environ.get("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")


@Configuration
class TaskConfig:
    """태스크 설정 - TaskBroker, TaskBackend"""

    @PostConstruct
    async def initialize(self):
        logger.info("TaskConfig initialized")

    @PreDestroy
    async def cleanup(self):
        logger.info("TaskConfig cleanup")

    @Factory
    def task_broker(self) -> TaskBroker:
        """TaskBroker 팩토리 - RedisBroker"""
        logger.info(f"Creating RedisBroker: {REDIS_URL}")
        return RedisBroker(REDIS_URL)

    @Factory
    def task_backend(self) -> TaskBackend:
        """TaskBackend 팩토리 - RedisBackend"""
        logger.info(f"Creating RedisBackend: {REDIS_URL}")
        return RedisBackend(REDIS_URL)
