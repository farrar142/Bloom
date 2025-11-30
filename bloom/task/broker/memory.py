"""InMemoryBroker - 인메모리 메시지 브로커

테스트 및 개발 환경용 인메모리 브로커입니다.
단일 프로세스에서만 동작하며, 프로세스 종료 시 모든 데이터가 사라집니다.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import TYPE_CHECKING

from .base import Broker

if TYPE_CHECKING:
    from bloom.task.message import TaskMessage
    from bloom.task.message import TaskResult as TaskResultMessage


class InMemoryBroker(Broker):
    """
    인메모리 메시지 브로커

    테스트 및 개발 환경용입니다.
    단일 프로세스에서만 동작합니다.

    Example:
        broker = InMemoryBroker()
        await broker.connect()

        # 태스크 추가
        await broker.enqueue(message)

        # 태스크 가져오기
        message = await broker.dequeue(timeout=5)

        await broker.disconnect()
    """

    def __init__(self):
        self._queues: dict[str, asyncio.Queue[TaskMessage]] = defaultdict(asyncio.Queue)
        self._results: dict[str, TaskResultMessage] = {}
        self._connected = False

    async def connect(self) -> None:
        """연결 (인메모리라 실제 연결 없음)"""
        self._connected = True

    async def disconnect(self) -> None:
        """연결 해제"""
        self._connected = False
        self._queues.clear()
        self._results.clear()

    async def enqueue(self, message: TaskMessage, queue: str = "default") -> None:
        """태스크 메시지를 큐에 추가"""
        if not self._connected:
            raise RuntimeError("Broker is not connected")
        await self._queues[queue].put(message)

    async def dequeue(
        self, queue: str = "default", timeout: float | None = None
    ) -> TaskMessage | None:
        """큐에서 태스크 메시지를 가져옴"""
        if not self._connected:
            raise RuntimeError("Broker is not connected")

        q = self._queues[queue]

        if timeout is None:
            # 즉시 반환
            try:
                return q.get_nowait()
            except asyncio.QueueEmpty:
                return None
        else:
            # 타임아웃까지 대기
            try:
                return await asyncio.wait_for(q.get(), timeout=timeout)
            except asyncio.TimeoutError:
                return None

    async def set_result(self, result: TaskResultMessage) -> None:
        """태스크 결과 저장"""
        if not self._connected:
            raise RuntimeError("Broker is not connected")
        self._results[result.task_id] = result

    async def get_result(self, task_id: str) -> TaskResultMessage | None:
        """태스크 결과 조회"""
        if not self._connected:
            raise RuntimeError("Broker is not connected")
        return self._results.get(task_id)

    async def delete_result(self, task_id: str) -> bool:
        """태스크 결과 삭제"""
        if not self._connected:
            raise RuntimeError("Broker is not connected")
        if task_id in self._results:
            del self._results[task_id]
            return True
        return False

    async def queue_length(self, queue: str = "default") -> int:
        """큐 길이 조회"""
        if not self._connected:
            raise RuntimeError("Broker is not connected")
        return self._queues[queue].qsize()

    # =========================================================================
    # Raw 메시지 API
    # =========================================================================

    def _get_raw_queue(self, queue: str) -> asyncio.Queue[str]:
        """raw 큐 가져오기 (없으면 생성)"""
        if not hasattr(self, "_raw_queues"):
            self._raw_queues: dict[str, asyncio.Queue[str]] = defaultdict(asyncio.Queue)
        return self._raw_queues[queue]

    def enqueue_raw_sync(self, queue: str, message: str) -> None:
        """원시 문자열 메시지를 동기적으로 큐에 추가"""
        if not self._connected:
            raise RuntimeError("Broker is not connected")
        self._get_raw_queue(queue).put_nowait(message)

    async def enqueue_raw(self, queue: str, message: str) -> None:
        """원시 문자열 메시지를 큐에 추가"""
        if not self._connected:
            raise RuntimeError("Broker is not connected")
        await self._get_raw_queue(queue).put(message)

    async def dequeue_raw(self, queue: str, timeout: float | None = None) -> str | None:
        """큐에서 원시 문자열 메시지를 가져옴"""
        if not self._connected:
            raise RuntimeError("Broker is not connected")

        q = self._get_raw_queue(queue)
        if timeout is None:
            try:
                return q.get_nowait()
            except asyncio.QueueEmpty:
                return None
        else:
            try:
                return await asyncio.wait_for(q.get(), timeout=timeout)
            except asyncio.TimeoutError:
                return None

    @property
    def is_connected(self) -> bool:
        """연결 상태"""
        return self._connected

    def __repr__(self) -> str:
        queues = len(self._queues)
        results = len(self._results)
        return f"<InMemoryBroker queues={queues} results={results}>"
