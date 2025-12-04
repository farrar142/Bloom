"""bloom.task.broker - 태스크 브로커 인터페이스

메시지 브로커 추상 인터페이스를 정의합니다.
브로커는 태스크 메시지를 큐에 전달하고 워커가 소비할 수 있게 합니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, TYPE_CHECKING

from .models import TaskMessage, TaskPriority

if TYPE_CHECKING:
    pass


class TaskBroker(ABC):
    """태스크 브로커 추상 인터페이스

    메시지 브로커의 공통 인터페이스를 정의합니다.
    Redis, RabbitMQ, 인메모리 등 다양한 구현이 가능합니다.

    Responsibilities:
        - 메시지 전송 (publish)
        - 메시지 소비 (consume)
        - 큐 관리 (declare, delete)
        - 메시지 확인 (ack, nack)
    """

    @abstractmethod
    async def connect(self) -> None:
        """브로커 연결"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """브로커 연결 해제"""
        pass

    @abstractmethod
    async def publish(
        self,
        message: TaskMessage,
        *,
        queue: str | None = None,
    ) -> None:
        """메시지 발행

        Args:
            message: 발행할 태스크 메시지
            queue: 대상 큐 (None이면 메시지의 queue 속성 사용)
        """
        pass

    @abstractmethod
    async def consume(
        self,
        queues: list[str],
        *,
        prefetch_count: int = 1,
    ) -> AsyncIterator[tuple[TaskMessage, Any]]:
        """메시지 소비

        Args:
            queues: 소비할 큐 목록
            prefetch_count: 한 번에 가져올 메시지 수

        Yields:
            (메시지, 배달 태그) 튜플
        """
        pass

    @abstractmethod
    async def ack(self, delivery_tag: Any) -> None:
        """메시지 확인 (처리 완료)"""
        pass

    @abstractmethod
    async def nack(
        self,
        delivery_tag: Any,
        *,
        requeue: bool = True,
    ) -> None:
        """메시지 거부

        Args:
            delivery_tag: 배달 태그
            requeue: True면 큐에 다시 추가
        """
        pass

    @abstractmethod
    async def declare_queue(
        self,
        name: str,
        *,
        durable: bool = True,
        auto_delete: bool = False,
    ) -> None:
        """큐 선언

        Args:
            name: 큐 이름
            durable: 서버 재시작 후에도 유지
            auto_delete: 소비자가 없으면 자동 삭제
        """
        pass

    @abstractmethod
    async def delete_queue(self, name: str) -> None:
        """큐 삭제"""
        pass

    @abstractmethod
    async def purge_queue(self, name: str) -> int:
        """큐 비우기

        Returns:
            삭제된 메시지 수
        """
        pass

    @abstractmethod
    async def queue_length(self, name: str) -> int:
        """큐의 메시지 수"""
        pass

    async def __aenter__(self) -> "TaskBroker":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    # =========================================================================
    # Optional Methods (기본 구현 제공)
    # =========================================================================

    async def health_check(self) -> bool:
        """브로커 연결 상태 확인"""
        return True

    async def get_queue_info(self, name: str) -> dict[str, Any]:
        """큐 정보 조회"""
        return {
            "name": name,
            "length": await self.queue_length(name),
        }
