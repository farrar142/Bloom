"""TaskBackend - 태스크 실행 백엔드

TaskBackend: 백엔드 추상 인터페이스
AsyncioTaskBackend: asyncio 기반 기본 구현
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, TypeVar

from .result import AsyncTaskResult, ScheduledTask, TaskResult
from .trigger import Trigger

T = TypeVar("T")
logger = logging.getLogger(__name__)


class TaskBackend(ABC):
    """
    태스크 실행 백엔드 추상 인터페이스

    모든 태스크 실행 백엔드는 이 인터페이스를 구현해야 합니다.

    구현체 예시:
        - AsyncioTaskBackend: asyncio 기반 (기본)
        - ThreadPoolBackend: ThreadPoolExecutor 기반
        - ProcessPoolBackend: ProcessPoolExecutor 기반
        - CeleryBackend: Celery 연동 (외부 구현)
    """

    @abstractmethod
    def submit(
        self,
        fn: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> TaskResult[T]:
        """
        태스크를 백그라운드에서 실행합니다.

        Args:
            fn: 실행할 함수
            *args: 위치 인자
            **kwargs: 키워드 인자

        Returns:
            TaskResult: 실행 결과
        """
        ...

    @abstractmethod
    async def submit_async(
        self,
        fn: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> AsyncTaskResult[T]:
        """
        태스크를 비동기로 실행합니다.

        Args:
            fn: 실행할 함수 (동기/비동기 모두 가능)
            *args: 위치 인자
            **kwargs: 키워드 인자

        Returns:
            AsyncTaskResult: 실행 결과
        """
        ...

    @abstractmethod
    def schedule(self, task: ScheduledTask) -> ScheduledTask:
        """
        태스크를 스케줄에 등록합니다.

        Args:
            task: 스케줄할 태스크

        Returns:
            등록된 ScheduledTask
        """
        ...

    @abstractmethod
    def unschedule(self, task: ScheduledTask) -> bool:
        """
        스케줄에서 태스크를 제거합니다.

        Args:
            task: 제거할 태스크

        Returns:
            True: 제거 성공, False: 태스크가 없음
        """
        ...

    @abstractmethod
    async def start(self) -> None:
        """백엔드를 시작합니다."""
        ...

    @abstractmethod
    async def shutdown(self, wait: bool = True) -> None:
        """
        백엔드를 종료합니다.

        Args:
            wait: True면 실행 중인 태스크 완료 대기
        """
        ...


class AsyncioTaskBackend(TaskBackend):
    """
    asyncio 기반 태스크 백엔드

    기본 구현체로, asyncio 이벤트 루프에서 태스크를 실행합니다.

    Example:
        backend = AsyncioTaskBackend(max_workers=4)
        await backend.start()

        # 백그라운드 실행
        result = backend.submit(my_function, arg1, arg2)
        value = result.get()

        # 스케줄 등록
        task = ScheduledTask(...)
        backend.schedule(task)

        await backend.shutdown()
    """

    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers
        self._executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._scheduled_tasks: dict[str, ScheduledTask] = {}
        self._running = False
        self._scheduler_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def scheduled_tasks(self) -> list[ScheduledTask]:
        return list(self._scheduled_tasks.values())

    def submit(
        self,
        fn: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> TaskResult[T]:
        """태스크를 백그라운드에서 실행"""
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="task-worker",
            )

        def execute() -> T:
            result = fn(*args, **kwargs)
            # 코루틴이면 이벤트 루프에서 실행
            if asyncio.iscoroutine(result):
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(result)
                finally:
                    loop.close()
            return result

        future = self._executor.submit(execute)
        return TaskResult(future, self._executor)

    async def submit_async(
        self,
        fn: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> AsyncTaskResult[T]:
        """태스크를 비동기로 실행"""

        async def execute() -> T:
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result

        task = asyncio.create_task(execute())
        return AsyncTaskResult(task)

    def schedule(self, task: ScheduledTask) -> ScheduledTask:
        """태스크를 스케줄에 등록"""
        self._scheduled_tasks[task.name] = task
        logger.debug(f"Scheduled task registered: {task.name}")
        return task

    def unschedule(self, task: ScheduledTask) -> bool:
        """스케줄에서 태스크 제거"""
        if task.name in self._scheduled_tasks:
            del self._scheduled_tasks[task.name]
            task.cancel()
            logger.debug(f"Scheduled task removed: {task.name}")
            return True
        return False

    async def start(self) -> None:
        """백엔드 시작"""
        if self._running:
            return

        self._running = True
        self._loop = asyncio.get_running_loop()

        # ThreadPoolExecutor 초기화
        if self._executor is None:
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=self._max_workers,
                thread_name_prefix="task-worker",
            )

        # 스케줄러 태스크 시작
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("AsyncioTaskBackend started")

    async def shutdown(self, wait: bool = True) -> None:
        """백엔드 종료"""
        self._running = False

        # 스케줄러 태스크 취소
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        # 스케줄된 태스크 취소
        for task in list(self._scheduled_tasks.values()):
            task.cancel()
        self._scheduled_tasks.clear()

        # ThreadPoolExecutor 종료
        if self._executor is not None:
            self._executor.shutdown(wait=wait)
            self._executor = None

        logger.info("AsyncioTaskBackend shutdown")

    async def _scheduler_loop(self) -> None:
        """스케줄러 메인 루프"""
        while self._running:
            now = datetime.now()

            for task in list(self._scheduled_tasks.values()):
                if not task.is_enabled:
                    continue

                next_time = task.trigger.next_execution_time(task.last_execution)
                if next_time is None:
                    continue

                if next_time <= now:
                    # 태스크 실행
                    asyncio.create_task(self._execute_scheduled_task(task))

            # 100ms 간격으로 체크
            await asyncio.sleep(0.1)

    async def _execute_scheduled_task(self, task: ScheduledTask) -> None:
        """스케줄된 태스크 실행"""
        try:
            await task.execute()
            logger.debug(f"Scheduled task executed: {task.name}")
        except Exception as e:
            logger.error(f"Scheduled task failed: {task.name} - {e}")
