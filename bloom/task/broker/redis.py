"""RedisBroker - Redis 기반 메시지 브로커

분산 환경용 Redis 브로커입니다.
여러 프로세스/서버에서 태스크를 공유할 수 있습니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import Broker

if TYPE_CHECKING:
    from bloom.task.message import TaskMessage
    from bloom.task.message import TaskResult as TaskResultMessage

logger = logging.getLogger(__name__)

# Redis 키 접두사
KEY_PREFIX = "bloom:task:"
QUEUE_PREFIX = f"{KEY_PREFIX}queue:"
RESULT_PREFIX = f"{KEY_PREFIX}result:"


class RedisBroker(Broker):
    """
    Redis 기반 메시지 브로커

    분산 환경에서 태스크를 공유할 수 있습니다.
    BRPOP을 사용하여 블로킹 방식으로 태스크를 가져옵니다.

    Example:
        broker = RedisBroker("redis://localhost:6379/0")
        await broker.connect()

        # 태스크 추가 (LPUSH)
        await broker.enqueue(message, queue="high-priority")

        # 태스크 가져오기 (BRPOP)
        message = await broker.dequeue(queue="high-priority", timeout=5)

        # 결과 저장 (HSET)
        await broker.set_result(result)

        await broker.disconnect()

    Redis 데이터 구조:
        - bloom:task:queue:{name} - LIST (LPUSH/BRPOP)
        - bloom:task:result:{task_id} - STRING (JSON)
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        result_ttl: int = 86400,  # 결과 보관 시간 (초)
        **redis_options: Any,
    ):
        """
        Args:
            url: Redis 연결 URL
            result_ttl: 결과 보관 시간 (초). 기본 24시간
            **redis_options: redis.asyncio.Redis 추가 옵션
        """
        self._url = url
        self._result_ttl = result_ttl
        self._redis_options = redis_options
        self._redis: Any = None
        self._connected = False

    async def connect(self) -> None:
        """Redis 연결"""
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "redis package is required for RedisBroker. "
                "Install it with: pip install redis"
            )

        self._redis = aioredis.from_url(self._url, **self._redis_options)
        # 연결 테스트
        await self._redis.ping()
        self._connected = True
        logger.info(f"RedisBroker connected to {self._url}")

    async def disconnect(self) -> None:
        """Redis 연결 해제"""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
        self._connected = False
        logger.info("RedisBroker disconnected")

    async def enqueue(self, message: TaskMessage, queue: str = "default") -> None:
        """태스크 메시지를 큐에 추가 (LPUSH)"""
        if not self._connected or self._redis is None:
            raise RuntimeError("Broker is not connected")

        key = f"{QUEUE_PREFIX}{queue}"
        await self._redis.lpush(key, message.to_json())
        logger.debug(f"Task enqueued: {message.task_id} -> {queue}")

    async def dequeue(
        self, queue: str = "default", timeout: float | None = None
    ) -> TaskMessage | None:
        """큐에서 태스크 메시지를 가져옴 (BRPOP/RPOP)"""
        if not self._connected or self._redis is None:
            raise RuntimeError("Broker is not connected")

        from bloom.task.message import TaskMessage

        key = f"{QUEUE_PREFIX}{queue}"

        if timeout is None or timeout == 0:
            # 즉시 반환 (RPOP)
            data = await self._redis.rpop(key)
        else:
            # 타임아웃까지 대기 (BRPOP)
            result = await self._redis.brpop(key, timeout=int(timeout))
            data = result[1] if result else None

        if data is None:
            return None

        # bytes -> str 변환
        if isinstance(data, bytes):
            data = data.decode("utf-8")

        message = TaskMessage.from_json(data)
        logger.debug(f"Task dequeued: {message.task_id} <- {queue}")
        return message

    async def set_result(self, result: TaskResultMessage) -> None:
        """태스크 결과 저장 (SETEX)"""
        if not self._connected or self._redis is None:
            raise RuntimeError("Broker is not connected")

        key = f"{RESULT_PREFIX}{result.task_id}"
        await self._redis.setex(key, self._result_ttl, result.to_json())
        logger.debug(f"Result stored: {result.task_id} ({result.state.value})")

    async def get_result(self, task_id: str) -> TaskResultMessage | None:
        """태스크 결과 조회 (GET)"""
        if not self._connected or self._redis is None:
            raise RuntimeError("Broker is not connected")

        from bloom.task.message import TaskResult

        key = f"{RESULT_PREFIX}{task_id}"
        data = await self._redis.get(key)

        if data is None:
            return None

        if isinstance(data, bytes):
            data = data.decode("utf-8")

        return TaskResult.from_json(data)

    async def delete_result(self, task_id: str) -> bool:
        """태스크 결과 삭제 (DEL)"""
        if not self._connected or self._redis is None:
            raise RuntimeError("Broker is not connected")

        key = f"{RESULT_PREFIX}{task_id}"
        deleted = await self._redis.delete(key)
        return deleted > 0

    async def queue_length(self, queue: str = "default") -> int:
        """큐 길이 조회 (LLEN)"""
        if not self._connected or self._redis is None:
            raise RuntimeError("Broker is not connected")

        key = f"{QUEUE_PREFIX}{queue}"
        return await self._redis.llen(key)

    @property
    def is_connected(self) -> bool:
        """연결 상태"""
        return self._connected

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"<RedisBroker {self._url} ({status})>"
