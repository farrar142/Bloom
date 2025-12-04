"""Event Configuration"""

from __future__ import annotations

import logging

from bloom.core import Configuration, Factory, PostConstruct, PreDestroy
from bloom.event import EventBus, LocalEventBus

logger = logging.getLogger(__name__)


@Configuration
class EventConfig:
    """이벤트 설정 - EventBus"""

    @PostConstruct
    async def initialize(self):
        logger.info("EventConfig initialized")

    @PreDestroy
    async def cleanup(self):
        logger.info("EventConfig cleanup")

    @Factory
    def event_bus(self) -> EventBus:
        """EventBus 팩토리 - LocalEventBus (인메모리)"""
        logger.info("Creating LocalEventBus")
        return LocalEventBus()
