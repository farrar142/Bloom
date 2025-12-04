"""bloom.task.backends.redis - Redis 브로커/백엔드

Redis를 사용하는 태스크 브로커와 결과 백엔드입니다.
분산 환경에서 여러 프로세스 간 태스크 전달에 사용됩니다.

Requirements:
    pip install redis

Usage:
    from bloom.task.backends.redis import RedisBroker, RedisBackend

    broker = RedisBroker("redis://localhost:6379/0")
    backend = RedisBackend("redis://localhost:6379/1")
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, TYPE_CHECKING

from ..broker import TaskBroker
from ..backend import TaskBackend
from ..models import TaskMessage, TaskResult, TaskStatus, TaskPriority

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


def _serialize_message(message: TaskMessage) -> str:
    """TaskMessage를 JSON 문자열로 직렬화"""
    return json.dumps(
        {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "args": message.args,
            "kwargs": message.kwargs,
            "queue": message.queue,
            "priority": message.priority.value,
            "eta": message.eta.isoformat() if message.eta else None,
            "expires": message.expires.isoformat() if message.expires else None,
            "retries": message.retries,
            "max_retries": message.max_retries,
            "correlation_id": message.correlation_id,
            "created_at": message.created_at.isoformat(),
        }
    )


def _deserialize_message(data: str) -> TaskMessage:
    """JSON 문자열을 TaskMessage로 역직렬화"""
    obj = json.loads(data)
    return TaskMessage(
        task_id=obj["task_id"],
        task_name=obj["task_name"],
        args=tuple(obj["args"]),
        kwargs=obj["kwargs"],
        queue=obj["queue"],
        priority=TaskPriority(obj["priority"]),
        eta=datetime.fromisoformat(obj["eta"]) if obj["eta"] else None,
        expires=datetime.fromisoformat(obj["expires"]) if obj["expires"] else None,
        retries=obj["retries"],
        max_retries=obj["max_retries"],
        correlation_id=obj["correlation_id"],
        created_at=datetime.fromisoformat(obj["created_at"]),
    )


def _serialize_result(result: TaskResult) -> str:
    """TaskResult를 JSON 문자열로 직렬화"""
    return json.dumps(
        {
            "task_id": result.task_id,
            "status": result.status.value,
            "result": result.result,
            "error": result.error,
            "traceback": result.traceback,
            "started_at": result.started_at.isoformat() if result.started_at else None,
            "completed_at": (
                result.completed_at.isoformat() if result.completed_at else None
            ),
        }
    )


def _deserialize_result(data: str) -> TaskResult:
    """JSON 문자열을 TaskResult로 역직렬화"""
    obj = json.loads(data)
    return TaskResult(
        task_id=obj["task_id"],
        status=TaskStatus(obj["status"]),
        result=obj["result"],
        error=obj["error"],
        traceback=obj["traceback"],
        started_at=(
            datetime.fromisoformat(obj["started_at"]) if obj["started_at"] else None
        ),
        completed_at=(
            datetime.fromisoformat(obj["completed_at"]) if obj["completed_at"] else None
        ),
    )


# =============================================================================
# Redis Broker
# =============================================================================


class RedisBroker(TaskBroker):
    """Redis 기반 태스크 브로커

    Redis List를 사용하여 메시지 큐를 구현합니다.
    BLPOP을 사용한 블로킹 소비를 지원합니다.

    Args:
        url: Redis 연결 URL (예: "redis://localhost:6379/0")
        prefix: 키 프리픽스 (기본: "bloom:task:")

    Examples:
        broker = RedisBroker("redis://localhost:6379/0")
        await broker.connect()

        # 메시지 발행
        await broker.publish(message, queue="default")

        # 메시지 소비
        async for msg, tag in broker.consume(["default"]):
            process(msg)
            await broker.ack(tag)
    """

    def __init__(
        self, url: str = "redis://localhost:6379/0", prefix: str = "bloom:task:"
    ):
        self.url = url
        self.prefix = prefix
        self._redis: Any = None
        self._connected = False

    def _queue_key(self, name: str) -> str:
        """큐 이름을 Redis 키로 변환"""
        return f"{self.prefix}queue:{name}"

    def _delayed_key(self) -> str:
        """지연 태스크용 Sorted Set 키"""
        return f"{self.prefix}delayed"

    async def connect(self) -> None:
        """Redis 연결"""
        try:
            import redis.asyncio as redis
        except ImportError:
            raise ImportError(
                "redis package is required for RedisBroker. "
                "Install it with: pip install redis"
            )

        self._redis = redis.from_url(self.url, decode_responses=True)
        self._connected = True
        logger.info(f"RedisBroker connected to {self.url}")

    async def disconnect(self) -> None:
        """Redis 연결 해제"""
        if self._redis:
            await self._redis.close()
            self._redis = None
        self._connected = False
        logger.info("RedisBroker disconnected")

    async def publish(
        self,
        message: TaskMessage,
        *,
        queue: str | None = None,
    ) -> None:
        """메시지 발행"""
        if not self._redis:
            raise RuntimeError("Broker not connected")

        queue_name = queue or message.queue
        data = _serialize_message(message)

        # eta가 있으면 지연 큐에 추가
        if message.eta and message.eta > datetime.now():
            score = message.eta.timestamp()
            await self._redis.zadd(self._delayed_key(), {f"{queue_name}:{data}": score})
            logger.debug(
                f"Published delayed message {message.task_id} to queue {queue_name}"
            )
        else:
            # 즉시 실행 큐에 추가
            await self._redis.rpush(self._queue_key(queue_name), data)
            logger.debug(f"Published message {message.task_id} to queue {queue_name}")

    async def _process_delayed_tasks(self) -> None:
        """지연된 태스크를 처리 큐로 이동"""
        if not self._redis:
            return

        now = datetime.now().timestamp()
        delayed_key = self._delayed_key()

        # 실행 시간이 된 태스크들 가져오기
        items = await self._redis.zrangebyscore(delayed_key, 0, now)

        for item in items:
            # "queue_name:message_data" 형식 파싱
            queue_name, data = item.split(":", 1)
            await self._redis.rpush(self._queue_key(queue_name), data)
            await self._redis.zrem(delayed_key, item)
            logger.debug(f"Moved delayed task to queue {queue_name}")

    async def consume(
        self,
        queues: list[str],
        *,
        prefetch_count: int = 1,
    ) -> AsyncIterator[tuple[TaskMessage, Any]]:
        """메시지 소비"""
        if not self._redis:
            raise RuntimeError("Broker not connected")

        queue_keys = [self._queue_key(q) for q in queues]
        reconnect_attempts = 0
        max_reconnect_attempts = 10
        base_delay = 1.0

        try:
            while self._connected:
                try:
                    # 지연된 태스크 처리
                    await self._process_delayed_tasks()

                    # BLPOP으로 메시지 대기 (1초 타임아웃)
                    result = await self._redis.blpop(queue_keys, timeout=1)

                    if result:
                        queue_key, data = result
                        message = _deserialize_message(data)

                        # 만료 확인
                        if message.is_expired():
                            logger.debug(
                                f"Message {message.task_id} expired, discarding"
                            )
                            continue

                        # 배달 태그로 task_id 사용
                        reconnect_attempts = 0  # 성공하면 리셋
                        yield message, message.task_id
                except Exception as e:
                    # Redis 연결 오류 시 재연결 시도
                    error_str = str(e)
                    error_type = type(e).__name__

                    if (
                        "Connection closed" in error_str
                        or "ConnectionError" in error_type
                    ):
                        reconnect_attempts += 1

                        if reconnect_attempts > max_reconnect_attempts:
                            logger.error(
                                f"Max reconnect attempts ({max_reconnect_attempts}) exceeded. "
                                f"Stopping consumer."
                            )
                            self._connected = False
                            return

                        # Exponential backoff
                        delay = min(base_delay * (2 ** (reconnect_attempts - 1)), 30)
                        logger.warning(
                            f"Redis connection lost ({error_str}), "
                            f"reconnecting in {delay:.1f}s... "
                            f"(attempt {reconnect_attempts}/{max_reconnect_attempts})"
                        )
                        await asyncio.sleep(delay)

                        try:
                            await self.connect()
                            logger.info("Reconnected to Redis successfully")
                            reconnect_attempts = 0
                        except Exception as conn_err:
                            logger.warning(f"Reconnect failed: {conn_err}")
                    else:
                        raise

        except asyncio.CancelledError:
            return

    async def ack(self, delivery_tag: Any) -> None:
        """메시지 확인 (Redis는 BLPOP 시 자동 제거)"""
        logger.debug(f"Acked delivery {delivery_tag}")

    async def nack(
        self,
        delivery_tag: Any,
        *,
        requeue: bool = True,
    ) -> None:
        """메시지 거부 (requeue는 별도 구현 필요)"""
        logger.debug(f"Nacked delivery {delivery_tag}, requeue={requeue}")
        # TODO: requeue 구현

    async def declare_queue(
        self,
        name: str,
        *,
        durable: bool = True,
        auto_delete: bool = False,
    ) -> None:
        """큐 선언 (Redis는 자동 생성)"""
        logger.debug(f"Queue {name} declared (Redis auto-creates)")

    async def delete_queue(self, name: str) -> None:
        """큐 삭제"""
        if self._redis:
            await self._redis.delete(self._queue_key(name))
            logger.debug(f"Queue {name} deleted")

    async def purge_queue(self, name: str) -> int:
        """큐 비우기"""
        if self._redis:
            key = self._queue_key(name)
            count = await self._redis.llen(key)
            await self._redis.delete(key)
            return count
        return 0

    async def queue_length(self, name: str) -> int:
        """큐의 메시지 수"""
        if self._redis:
            return await self._redis.llen(self._queue_key(name))
        return 0


# =============================================================================
# Redis Backend
# =============================================================================


class RedisBackend(TaskBackend):
    """Redis 기반 결과 백엔드

    Redis를 사용하여 태스크 결과를 저장합니다.
    Pub/Sub을 사용하여 결과 대기를 최적화합니다.

    Args:
        url: Redis 연결 URL
        prefix: 키 프리픽스 (기본: "bloom:result:")
        default_ttl: 기본 결과 TTL (초, 기본: 3600)
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        prefix: str = "bloom:result:",
        default_ttl: int = 3600,
    ):
        self.url = url
        self.prefix = prefix
        self.default_ttl = default_ttl
        self._redis: Any = None
        self._connected = False

    def _result_key(self, task_id: str) -> str:
        """task_id를 Redis 키로 변환"""
        return f"{self.prefix}{task_id}"

    def _channel_key(self, task_id: str) -> str:
        """결과 알림 채널 키"""
        return f"{self.prefix}channel:{task_id}"

    async def connect(self) -> None:
        """Redis 연결"""
        try:
            import redis.asyncio as redis
        except ImportError:
            raise ImportError(
                "redis package is required for RedisBackend. "
                "Install it with: pip install redis"
            )

        self._redis = redis.from_url(self.url, decode_responses=True)
        self._connected = True
        logger.info(f"RedisBackend connected to {self.url}")

    async def disconnect(self) -> None:
        """Redis 연결 해제"""
        if self._redis:
            await self._redis.close()
            self._redis = None
        self._connected = False
        logger.info("RedisBackend disconnected")

    async def store_result(
        self,
        task_id: str,
        result: TaskResult[Any],
        *,
        ttl: int | None = None,
    ) -> None:
        """결과 저장"""
        if not self._redis:
            raise RuntimeError("Backend not connected")

        key = self._result_key(task_id)
        data = _serialize_result(result)
        ttl_value = ttl or self.default_ttl

        await self._redis.setex(key, ttl_value, data)

        # 결과 알림 발행
        await self._redis.publish(self._channel_key(task_id), "ready")

        logger.debug(f"Stored result for task {task_id}")

    async def get_result(self, task_id: str) -> TaskResult[Any] | None:
        """결과 조회"""
        if not self._redis:
            raise RuntimeError("Backend not connected")

        key = self._result_key(task_id)
        data = await self._redis.get(key)

        if data:
            return _deserialize_result(data)
        return None

    async def delete_result(self, task_id: str) -> bool:
        """결과 삭제"""
        if not self._redis:
            raise RuntimeError("Backend not connected")

        key = self._result_key(task_id)
        deleted = await self._redis.delete(key)
        return deleted > 0

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        result: Any | None = None,
        error: str | None = None,
        traceback: str | None = None,
    ) -> None:
        """상태 업데이트"""
        if not self._redis:
            raise RuntimeError("Backend not connected")

        # 기존 결과 가져오기
        existing = await self.get_result(task_id)

        if existing:
            existing.status = status
            if result is not None:
                existing.result = result
            if error is not None:
                existing.error = error
            if traceback is not None:
                existing.traceback = traceback
            if status == TaskStatus.STARTED:
                existing.started_at = datetime.now()
            elif status in (TaskStatus.SUCCESS, TaskStatus.FAILURE, TaskStatus.REVOKED):
                existing.completed_at = datetime.now()

            await self.store_result(task_id, existing)
        else:
            # 새 결과 생성
            new_result = TaskResult(
                task_id=task_id,
                status=status,
                result=result,
                error=error,
                traceback=traceback,
            )
            await self.store_result(task_id, new_result)

    async def wait_for_result(
        self,
        task_id: str,
        *,
        timeout: float | None = None,
        interval: float = 0.1,
    ) -> TaskResult[Any] | None:
        """결과 대기 (Pub/Sub 사용)"""
        # 이미 결과가 있으면 즉시 반환
        result = await self.get_result(task_id)
        if result and result.is_ready():
            return result

        if not self._redis:
            raise RuntimeError("Backend not connected")

        try:
            import redis.asyncio as redis
        except ImportError:
            raise ImportError("redis package is required")

        # Pub/Sub 구독
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self._channel_key(task_id))

        try:

            async def wait_for_message():
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        return await self.get_result(task_id)

            result = await asyncio.wait_for(wait_for_message(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return await self.get_result(task_id)
        finally:
            await pubsub.unsubscribe(self._channel_key(task_id))
            await pubsub.close()
