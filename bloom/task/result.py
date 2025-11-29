"""TaskResult - 태스크 실행 결과

TaskResult: 동기 실행 결과 (ThreadPoolExecutor 기반)
AsyncTaskResult: 비동기 실행 결과 (asyncio.Task 기반)
ScheduledTask: 스케줄된 태스크 제어
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar

if TYPE_CHECKING:
    from .trigger import Trigger

T = TypeVar("T")


class TaskResult(Generic[T]):
    """
    태스크 실행 결과 (동기)

    Celery의 AsyncResult와 유사한 인터페이스를 제공합니다.

    Example:
        result = service.send_email.delay("user@example.com", "Hello")

        # 결과 대기
        value = result.get()
        value = result.get(timeout=5)

        # 상태 확인
        result.ready()      # 완료 여부
        result.successful() # 성공 여부
        result.failed()     # 실패 여부
    """

    def __init__(
        self,
        future: concurrent.futures.Future[T],
        executor: concurrent.futures.ThreadPoolExecutor | None = None,
        task_id: str | None = None,
    ):
        self._future = future
        self._executor = executor
        self._task_id = task_id or id(future)

    @property
    def task_id(self) -> str:
        """태스크 ID"""
        return str(self._task_id)

    @property
    def future(self) -> concurrent.futures.Future[T]:
        """내부 Future 객체"""
        return self._future

    def get(self, timeout: float | None = None) -> T:
        """
        결과를 반환합니다. 완료될 때까지 대기합니다.

        Args:
            timeout: 대기 시간 (초). None이면 무한 대기

        Returns:
            태스크 결과

        Raises:
            TimeoutError: timeout 초과 시
            Exception: 태스크 실행 중 발생한 예외
        """
        try:
            return self._future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Task did not complete within {timeout} seconds")

    def ready(self) -> bool:
        """태스크가 완료되었는지 확인 (성공/실패 무관)"""
        return self._future.done()

    def successful(self) -> bool:
        """태스크가 성공적으로 완료되었는지 확인"""
        if not self._future.done():
            return False
        return self._future.exception() is None

    def failed(self) -> bool:
        """태스크가 실패했는지 확인"""
        if not self._future.done():
            return False
        return self._future.exception() is not None

    def wait(self, timeout: float | None = None) -> TaskResult[T]:
        """
        태스크 완료를 대기합니다 (결과 반환 없음)

        Args:
            timeout: 대기 시간 (초)

        Returns:
            self (메서드 체이닝)
        """
        try:
            self._future.result(timeout=timeout)
        except Exception:
            pass  # 예외는 get()에서 처리
        return self

    def revoke(self) -> bool:
        """
        태스크 취소를 시도합니다.

        Returns:
            True: 취소 성공
            False: 이미 실행 중이거나 완료됨
        """
        return self._future.cancel()

    def add_callback(self, fn: Callable[[TaskResult[T]], Any]) -> TaskResult[T]:
        """
        태스크 완료 시 호출될 콜백을 등록합니다.

        Args:
            fn: 콜백 함수

        Returns:
            self (메서드 체이닝)
        """

        def wrapper(future: concurrent.futures.Future[T]) -> None:
            fn(self)

        self._future.add_done_callback(wrapper)
        return self

    def __repr__(self) -> str:
        if self._future.cancelled():
            status = "REVOKED"
        elif self._future.running():
            status = "STARTED"
        elif self._future.done():
            status = "SUCCESS" if self.successful() else "FAILURE"
        else:
            status = "PENDING"
        return f"<TaskResult: {self.task_id} ({status})>"


class AsyncTaskResult(Generic[T]):
    """
    태스크 실행 결과 (비동기)

    asyncio.Task 기반으로 동작합니다.

    Example:
        result = await service.send_email.delay_async("user@example.com")
        value = await result.get()
    """

    def __init__(
        self,
        task: asyncio.Task[T],
        task_id: str | None = None,
    ):
        self._task = task
        self._task_id = task_id or id(task)

    @property
    def task_id(self) -> str:
        """태스크 ID"""
        return str(self._task_id)

    async def get(self, timeout: float | None = None) -> T:
        """결과를 반환합니다."""
        if timeout is not None:
            return await asyncio.wait_for(self._task, timeout=timeout)
        return await self._task

    def ready(self) -> bool:
        """태스크가 완료되었는지 확인"""
        return self._task.done()

    def successful(self) -> bool:
        """태스크가 성공적으로 완료되었는지 확인"""
        if not self._task.done():
            return False
        return self._task.exception() is None

    def failed(self) -> bool:
        """태스크가 실패했는지 확인"""
        if not self._task.done():
            return False
        return self._task.exception() is not None

    def revoke(self) -> bool:
        """태스크 취소"""
        return self._task.cancel()

    def __repr__(self) -> str:
        if self._task.cancelled():
            status = "REVOKED"
        elif self._task.done():
            status = "SUCCESS" if self.successful() else "FAILURE"
        else:
            status = "PENDING"
        return f"<AsyncTaskResult: {self.task_id} ({status})>"


class ScheduledTask(Generic[T]):
    """
    스케줄된 태스크

    주기적으로 실행되는 태스크를 제어합니다.

    Example:
        task = service.cleanup.schedule(fixed_rate=60)

        task.pause()   # 일시정지
        task.resume()  # 재개
        task.cancel()  # 취소

        info = task.info()  # 상태 조회
    """

    def __init__(
        self,
        name: str,
        handler: Callable[..., T],
        trigger: Trigger,
        args: tuple = (),
        kwargs: dict | None = None,
        instance: Any = None,
    ):
        self._name = name
        self._handler = handler
        self._trigger = trigger
        self._args = args
        self._kwargs = kwargs or {}
        self._instance = instance

        self._enabled = True
        self._execution_count = 0
        self._last_execution: datetime | None = None
        self._last_result: T | None = None
        self._last_error: Exception | None = None
        self._asyncio_task: asyncio.Task | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def trigger(self) -> Trigger:
        return self._trigger

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def execution_count(self) -> int:
        return self._execution_count

    @property
    def last_execution(self) -> datetime | None:
        return self._last_execution

    @property
    def last_result(self) -> T | None:
        return self._last_result

    @property
    def last_error(self) -> Exception | None:
        return self._last_error

    def pause(self) -> None:
        """스케줄 일시정지"""
        self._enabled = False

    def resume(self) -> None:
        """스케줄 재개"""
        self._enabled = True

    def cancel(self) -> bool:
        """스케줄 취소"""
        self._enabled = False
        if self._asyncio_task is not None:
            self._asyncio_task.cancel()
            return True
        return False

    async def execute(self) -> T:
        """태스크를 즉시 실행합니다."""
        self._last_execution = datetime.now()
        self._execution_count += 1

        try:
            if self._instance is not None:
                result = self._handler(self._instance, *self._args, **self._kwargs)
            else:
                result = self._handler(*self._args, **self._kwargs)

            # 비동기 함수면 await
            if asyncio.iscoroutine(result):
                result = await result

            self._last_result = result
            self._last_error = None
            return result
        except Exception as e:
            self._last_error = e
            raise

    def run(self) -> TaskResult[T]:
        """
        태스크를 즉시 실행하고 TaskResult를 반환합니다 (스케줄과 별개)
        """
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="task-run")

        def execute_sync() -> T:
            if self._instance is not None:
                return self._handler(self._instance, *self._args, **self._kwargs)
            return self._handler(*self._args, **self._kwargs)

        future = executor.submit(execute_sync)
        return TaskResult(future, executor)

    def info(self) -> dict[str, Any]:
        """태스크 정보 반환"""
        return {
            "name": self._name,
            "trigger": repr(self._trigger),
            "enabled": self._enabled,
            "execution_count": self._execution_count,
            "last_execution": (
                self._last_execution.isoformat() if self._last_execution else None
            ),
            "last_error": str(self._last_error) if self._last_error else None,
        }

    def __repr__(self) -> str:
        status = "enabled" if self._enabled else "paused"
        return f"<ScheduledTask: {self._name} ({status}, runs={self._execution_count})>"
