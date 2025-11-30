"""Broker - 메시지 브로커 추상 인터페이스

브로커는 태스크 메시지의 전달과 결과 저장을 담당합니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bloom.task.message import TaskMessage
    from bloom.task.message import TaskResult as TaskResultMessage


class Broker(ABC):
    """
    메시지 브로커 추상 인터페이스

    브로커는 다음 역할을 수행합니다:
    1. 태스크 메시지를 큐에 추가 (enqueue)
    2. 큐에서 태스크 메시지를 가져옴 (dequeue)
    3. 태스크 결과를 저장/조회

    구현체:
    - InMemoryBroker: 테스트/개발용 인메모리 브로커
    - RedisBroker: 분산 환경용 Redis 브로커
    """

    @abstractmethod
    async def connect(self) -> None:
        """브로커에 연결"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """브로커 연결 해제"""
        ...

    @abstractmethod
    async def enqueue(self, message: TaskMessage, queue: str = "default") -> None:
        """
        태스크 메시지를 큐에 추가

        Args:
            message: 태스크 메시지
            queue: 큐 이름
        """
        ...

    @abstractmethod
    async def dequeue(
        self, queue: str = "default", timeout: float | None = None
    ) -> TaskMessage | None:
        """
        큐에서 태스크 메시지를 가져옴

        Args:
            queue: 큐 이름
            timeout: 대기 시간 (초). None이면 즉시 반환

        Returns:
            TaskMessage 또는 None (큐가 비어있으면)
        """
        ...

    @abstractmethod
    async def set_result(self, result: TaskResultMessage) -> None:
        """
        태스크 결과 저장

        Args:
            result: 태스크 결과
        """
        ...

    @abstractmethod
    async def get_result(self, task_id: str) -> TaskResultMessage | None:
        """
        태스크 결과 조회

        Args:
            task_id: 태스크 ID

        Returns:
            TaskResult 또는 None
        """
        ...

    @abstractmethod
    async def delete_result(self, task_id: str) -> bool:
        """
        태스크 결과 삭제

        Args:
            task_id: 태스크 ID

        Returns:
            True: 삭제됨, False: 없음
        """
        ...

    @abstractmethod
    async def queue_length(self, queue: str = "default") -> int:
        """
        큐 길이 조회

        Args:
            queue: 큐 이름

        Returns:
            큐에 있는 메시지 수
        """
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """연결 상태"""
        ...
