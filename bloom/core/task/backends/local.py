"""bloom.core.task.backends.local - 로컬 인메모리 브로커/백엔드

단일 프로세스 내에서 동작하는 인메모리 브로커와 백엔드입니다.
개발 및 테스트용으로 사용됩니다.
"""

from __future__ import annotations

import asyncio
import heapq
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, TYPE_CHECKING

from ..broker import TaskBroker
from ..backend import TaskBackend
from ..models import TaskMessage, TaskResult, TaskStatus, TaskPriority

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


# =============================================================================
# Priority Queue Item
# =============================================================================


@dataclass(order=True)
class PriorityItem:
    """우선순위 큐 아이템"""

    priority: int
    eta_timestamp: float  # eta를 timestamp로 저장 (비교 가능)
    created_at_timestamp: float  # 생성 시간 (동일 우선순위 시 FIFO)
    message: TaskMessage = field(compare=False)
    delivery_tag: str = field(compare=False)


# =============================================================================
# Local Broker
# =============================================================================


class LocalBroker(TaskBroker):
    """로컬 인메모리 브로커

    단일 프로세스 내에서 동작하는 인메모리 메시지 브로커입니다.
    우선순위 큐와 지연 실행을 지원합니다.

    Features:
        - 우선순위 기반 메시지 처리
        - 지연 실행 (eta/countdown)
        - 메시지 TTL
        - 큐 관리

    Note:
        개발 및 테스트용으로만 사용하세요.
        프로덕션에서는 Redis나 RabbitMQ 브로커를 사용하세요.
    """

    def __init__(self):
        # 큐별 메시지 저장 (우선순위 큐)
        self._queues: dict[str, list[PriorityItem]] = defaultdict(list)
        # 배달 태그 -> (큐 이름, 메시지) 매핑
        self._pending: dict[str, tuple[str, TaskMessage]] = {}
        # 큐별 이벤트 (새 메시지 알림)
        self._events: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self._lock = asyncio.Lock()
        self._connected = False
        self._delivery_counter = 0

    async def connect(self) -> None:
        """브로커 연결"""
        self._connected = True
        logger.debug("LocalBroker connected")

    async def disconnect(self) -> None:
        """브로커 연결 해제"""
        self._connected = False
        self._queues.clear()
        self._pending.clear()
        logger.debug("LocalBroker disconnected")

    async def publish(
        self,
        message: TaskMessage,
        *,
        queue: str | None = None,
    ) -> None:
        """메시지 발행"""
        queue_name = queue or message.queue

        async with self._lock:
            # 배달 태그 생성
            self._delivery_counter += 1
            delivery_tag = f"local-{self._delivery_counter}"

            # 우선순위 아이템 생성
            eta_timestamp = (
                message.eta.timestamp() if message.eta else 0
            )
            created_timestamp = message.created_at.timestamp()

            item = PriorityItem(
                priority=message.priority.value,
                eta_timestamp=eta_timestamp,
                created_at_timestamp=created_timestamp,
                message=message,
                delivery_tag=delivery_tag,
            )

            # 힙에 추가
            heapq.heappush(self._queues[queue_name], item)

            # 이벤트 설정 (대기 중인 소비자 깨우기)
            self._events[queue_name].set()

        logger.debug(f"Published message {message.task_id} to queue {queue_name}")

    async def consume(
        self,
        queues: list[str],
        *,
        prefetch_count: int = 1,
    ) -> AsyncIterator[tuple[TaskMessage, Any]]:
        """메시지 소비

        지연 실행 메시지는 eta 시간이 될 때까지 대기합니다.
        """
        try:
            while self._connected:
                message_to_yield: tuple[TaskMessage, str] | None = None

                for queue_name in queues:
                    async with self._lock:
                        heap = self._queues.get(queue_name)
                        if not heap:
                            continue

                        # eta 확인
                        now = datetime.now().timestamp()

                        while heap:
                            # 가장 높은 우선순위 메시지 확인 (팝하지 않음)
                            item = heap[0]

                            # eta가 있고 아직 시간이 안 됐으면 스킵
                            if item.eta_timestamp > 0 and item.eta_timestamp > now:
                                break

                            # 만료 확인
                            if item.message.is_expired():
                                heapq.heappop(heap)
                                logger.debug(
                                    f"Message {item.message.task_id} expired, discarding"
                                )
                                continue

                            # 메시지 팝
                            item = heapq.heappop(heap)
                            self._pending[item.delivery_tag] = (queue_name, item.message)
                            message_to_yield = (item.message, item.delivery_tag)
                            break

                    # lock 해제 후 yield (다른 코루틴이 lock 획득 가능)
                    if message_to_yield:
                        yield message_to_yield
                        message_to_yield = None

                if message_to_yield is None:
                    # 메시지가 없으면 잠시 대기 후 다시 확인
                    for queue_name in queues:
                        self._events[queue_name].clear()

                    await asyncio.sleep(0.1)
        except (asyncio.CancelledError, GeneratorExit):
            # 제너레이터 종료 시 정상 종료
            return

    async def ack(self, delivery_tag: Any) -> None:
        """메시지 확인"""
        async with self._lock:
            if delivery_tag in self._pending:
                del self._pending[delivery_tag]
                logger.debug(f"Acked delivery {delivery_tag}")

    async def nack(
        self,
        delivery_tag: Any,
        *,
        requeue: bool = True,
    ) -> None:
        """메시지 거부"""
        async with self._lock:
            if delivery_tag not in self._pending:
                return

            queue_name, message = self._pending.pop(delivery_tag)

            if requeue:
                # 다시 큐에 추가
                self._delivery_counter += 1
                new_tag = f"local-{self._delivery_counter}"

                item = PriorityItem(
                    priority=message.priority.value,
                    eta_timestamp=0,  # 즉시 실행 가능
                    created_at_timestamp=message.created_at.timestamp(),
                    message=message,
                    delivery_tag=new_tag,
                )
                heapq.heappush(self._queues[queue_name], item)
                self._events[queue_name].set()

                logger.debug(f"Nacked and requeued delivery {delivery_tag}")
            else:
                logger.debug(f"Nacked and discarded delivery {delivery_tag}")

    async def declare_queue(
        self,
        name: str,
        *,
        durable: bool = True,
        auto_delete: bool = False,
    ) -> None:
        """큐 선언"""
        async with self._lock:
            if name not in self._queues:
                self._queues[name] = []
                logger.debug(f"Declared queue {name}")

    async def delete_queue(self, name: str) -> None:
        """큐 삭제"""
        async with self._lock:
            if name in self._queues:
                del self._queues[name]
                logger.debug(f"Deleted queue {name}")

    async def purge_queue(self, name: str) -> int:
        """큐 비우기"""
        async with self._lock:
            if name in self._queues:
                count = len(self._queues[name])
                self._queues[name].clear()
                logger.debug(f"Purged {count} messages from queue {name}")
                return count
            return 0

    async def queue_length(self, name: str) -> int:
        """큐의 메시지 수"""
        async with self._lock:
            return len(self._queues.get(name, []))


# =============================================================================
# Local Backend
# =============================================================================


class LocalBackend(TaskBackend):
    """로컬 인메모리 백엔드

    단일 프로세스 내에서 동작하는 인메모리 결과 저장소입니다.

    Note:
        개발 및 테스트용으로만 사용하세요.
        프로덕션에서는 Redis나 Database 백엔드를 사용하세요.
    """

    def __init__(self):
        self._results: dict[str, TaskResult[Any]] = {}
        self._result_events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> None:
        """백엔드 연결"""
        self._connected = True
        logger.debug("LocalBackend connected")

    async def disconnect(self) -> None:
        """백엔드 연결 해제"""
        self._connected = False
        self._results.clear()
        self._result_events.clear()
        logger.debug("LocalBackend disconnected")

    async def store_result(
        self,
        task_id: str,
        result: TaskResult[Any],
        *,
        ttl: int | None = None,
    ) -> None:
        """결과 저장"""
        async with self._lock:
            self._results[task_id] = result

            # 대기 중인 클라이언트 깨우기
            if task_id in self._result_events:
                self._result_events[task_id].set()

        logger.debug(f"Stored result for task {task_id}: {result.status}")

    async def get_result(self, task_id: str) -> TaskResult[Any] | None:
        """결과 조회"""
        async with self._lock:
            return self._results.get(task_id)

    async def delete_result(self, task_id: str) -> bool:
        """결과 삭제"""
        async with self._lock:
            if task_id in self._results:
                del self._results[task_id]
                return True
            return False

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
        async with self._lock:
            if task_id in self._results:
                task_result = self._results[task_id]
                task_result.status = status

                if result is not None:
                    task_result.result = result
                if error is not None:
                    task_result.error = error
                if traceback is not None:
                    task_result.traceback = traceback

                if status == TaskStatus.STARTED:
                    task_result.started_at = datetime.now()
                elif status in (
                    TaskStatus.SUCCESS,
                    TaskStatus.FAILURE,
                    TaskStatus.REVOKED,
                ):
                    task_result.completed_at = datetime.now()
            else:
                # 새 결과 생성
                self._results[task_id] = TaskResult(
                    task_id=task_id,
                    status=status,
                    result=result,
                    error=error,
                    traceback=traceback,
                )

            # 대기 중인 클라이언트 깨우기
            if task_id in self._result_events:
                self._result_events[task_id].set()

    async def wait_for_result(
        self,
        task_id: str,
        *,
        timeout: float | None = None,
        interval: float = 0.1,
    ) -> TaskResult[Any] | None:
        """결과 대기 (이벤트 기반 최적화)"""
        # 이미 결과가 있으면 즉시 반환
        result = await self.get_result(task_id)
        if result and result.is_ready():
            return result

        # 이벤트 생성
        async with self._lock:
            if task_id not in self._result_events:
                self._result_events[task_id] = asyncio.Event()
            event = self._result_events[task_id]

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return await self.get_result(task_id)
        except asyncio.TimeoutError:
            return await self.get_result(task_id)
        finally:
            # 이벤트 정리
            async with self._lock:
                if task_id in self._result_events:
                    del self._result_events[task_id]
