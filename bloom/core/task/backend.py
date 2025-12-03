"""bloom.core.task.backend - 태스크 결과 백엔드 인터페이스

태스크 실행 결과를 저장하고 조회하는 백엔드 인터페이스입니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

from .models import TaskResult, TaskStatus

if TYPE_CHECKING:
    pass


class TaskBackend(ABC):
    """태스크 결과 백엔드 추상 인터페이스

    태스크 실행 결과를 저장하고 조회하는 인터페이스입니다.
    Redis, Database, 인메모리 등 다양한 구현이 가능합니다.

    Responsibilities:
        - 결과 저장
        - 결과 조회
        - 상태 업데이트
        - TTL 관리
    """

    @abstractmethod
    async def connect(self) -> None:
        """백엔드 연결"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """백엔드 연결 해제"""
        pass

    @abstractmethod
    async def store_result(
        self,
        task_id: str,
        result: TaskResult[Any],
        *,
        ttl: int | None = None,
    ) -> None:
        """결과 저장

        Args:
            task_id: 태스크 ID
            result: 태스크 결과
            ttl: 결과 보관 시간 (초), None이면 영구 보관
        """
        pass

    @abstractmethod
    async def get_result(self, task_id: str) -> TaskResult[Any] | None:
        """결과 조회

        Args:
            task_id: 태스크 ID

        Returns:
            태스크 결과, 없으면 None
        """
        pass

    @abstractmethod
    async def delete_result(self, task_id: str) -> bool:
        """결과 삭제

        Returns:
            삭제 성공 여부
        """
        pass

    @abstractmethod
    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        result: Any | None = None,
        error: str | None = None,
        traceback: str | None = None,
    ) -> None:
        """상태 업데이트

        Args:
            task_id: 태스크 ID
            status: 새로운 상태
            result: 결과값 (SUCCESS 시)
            error: 에러 메시지 (FAILURE 시)
            traceback: 스택 트레이스 (FAILURE 시)
        """
        pass

    async def __aenter__(self) -> "TaskBackend":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.disconnect()

    # =========================================================================
    # Optional Methods (기본 구현 제공)
    # =========================================================================

    async def health_check(self) -> bool:
        """백엔드 연결 상태 확인"""
        return True

    async def exists(self, task_id: str) -> bool:
        """결과 존재 여부 확인"""
        return await self.get_result(task_id) is not None

    async def wait_for_result(
        self,
        task_id: str,
        *,
        timeout: float | None = None,
        interval: float = 0.1,
    ) -> TaskResult[Any] | None:
        """결과 대기

        폴링 방식으로 결과가 준비될 때까지 대기합니다.

        Args:
            task_id: 태스크 ID
            timeout: 최대 대기 시간 (초)
            interval: 폴링 간격 (초)

        Returns:
            태스크 결과, 타임아웃 시 None
        """
        import asyncio
        from datetime import datetime, timedelta

        start = datetime.now()
        deadline = start + timedelta(seconds=timeout) if timeout else None

        while True:
            result = await self.get_result(task_id)
            if result and result.is_ready():
                return result

            if deadline and datetime.now() >= deadline:
                return None

            await asyncio.sleep(interval)
