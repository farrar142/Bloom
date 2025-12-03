"""bloom.core.task.worker - 태스크 워커

태스크를 소비하고 실행하는 워커 프로세스입니다.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Awaitable, TYPE_CHECKING

from .models import (
    TaskMessage,
    TaskResult,
    TaskStatus,
    TaskError,
    TaskRetryError,
    TaskRejectError,
    TaskTimeoutError,
)
from .broker import TaskBroker
from .backend import TaskBackend

if TYPE_CHECKING:
    from .app import TaskApp


logger = logging.getLogger(__name__)


# =============================================================================
# Worker State
# =============================================================================


class WorkerState(Enum):
    """워커 상태"""

    CREATED = auto()  # 생성됨
    STARTING = auto()  # 시작 중
    RUNNING = auto()  # 실행 중
    STOPPING = auto()  # 종료 중
    STOPPED = auto()  # 종료됨


# =============================================================================
# Worker Config
# =============================================================================


@dataclass
class WorkerConfig:
    """워커 설정

    Attributes:
        concurrency: 동시 실행 워커 수
        queues: 소비할 큐 목록
        prefetch_count: 한 번에 가져올 메시지 수
        task_timeout: 기본 태스크 타임아웃 (초)
        result_expires: 결과 보관 시간 (초)
        acks_late: 완료 후 ACK 전송
        enable_utc: UTC 시간 사용
        worker_prefetch_multiplier: prefetch 승수
        max_tasks_per_child: 워커당 최대 태스크 수 (0=무제한)
    """

    concurrency: int = 1
    queues: list[str] = field(default_factory=lambda: ["default"])
    prefetch_count: int = 1
    task_timeout: float = 300.0  # 5분
    result_expires: int = 3600  # 1시간
    acks_late: bool = False
    enable_utc: bool = True
    worker_prefetch_multiplier: int = 4
    max_tasks_per_child: int = 0

    def __post_init__(self):
        if not self.queues:
            self.queues = ["default"]


# =============================================================================
# Worker
# =============================================================================


class Worker:
    """태스크 워커

    브로커에서 메시지를 소비하고 태스크를 실행합니다.

    Features:
        - 동시성 설정 가능
        - 우아한 종료 (graceful shutdown)
        - 재시도 처리
        - 타임아웃 처리
        - 결과 저장

    Examples:
        from bloom.core.task import TaskApp, Worker, WorkerConfig
        from bloom.core.task.backends import LocalBroker, LocalBackend

        task_app = TaskApp("my_app")
        task_app.broker = LocalBroker()
        task_app.backend = LocalBackend()

        @task_app.task
        async def my_task(data):
            return data * 2

        # 워커 실행
        worker = Worker(task_app, config=WorkerConfig(concurrency=4))
        await worker.start()
    """

    def __init__(
        self,
        app: "TaskApp",
        *,
        config: WorkerConfig | None = None,
        broker: TaskBroker | None = None,
        backend: TaskBackend | None = None,
    ):
        self.app = app
        self.config = config or WorkerConfig()
        self.broker = broker or app.broker
        self.backend = backend or app.backend

        # 워커 ID
        self.worker_id = f"worker-{uuid.uuid4().hex[:8]}"

        # 상태
        self.state = WorkerState.CREATED
        self._running = False
        self._tasks: list[asyncio.Task[None]] = []
        self._shutdown_event = asyncio.Event()

        # 통계
        self._tasks_processed = 0
        self._tasks_succeeded = 0
        self._tasks_failed = 0
        self._tasks_retried = 0

    @property
    def stats(self) -> dict[str, Any]:
        """워커 통계"""
        return {
            "worker_id": self.worker_id,
            "state": self.state.name,
            "tasks_processed": self._tasks_processed,
            "tasks_succeeded": self._tasks_succeeded,
            "tasks_failed": self._tasks_failed,
            "tasks_retried": self._tasks_retried,
            "concurrency": self.config.concurrency,
            "queues": self.config.queues,
        }

    async def start(self) -> None:
        """워커 시작"""
        if self.state == WorkerState.RUNNING:
            logger.warning("Worker is already running")
            return

        if not self.broker:
            raise RuntimeError("Broker is not configured")

        self.state = WorkerState.STARTING
        self._running = True
        self._shutdown_event.clear()

        # 브로커/백엔드 연결
        await self.broker.connect()
        if self.backend:
            await self.backend.connect()

        # 큐 선언
        for queue in self.config.queues:
            await self.broker.declare_queue(queue)

        # 워커 태스크 시작
        for i in range(self.config.concurrency):
            task = asyncio.create_task(
                self._worker_loop(i), name=f"{self.worker_id}-{i}"
            )
            self._tasks.append(task)

        self.state = WorkerState.RUNNING
        logger.info(
            f"Worker {self.worker_id} started with {self.config.concurrency} workers "
            f"on queues: {self.config.queues}"
        )

        # 종료 이벤트 대기
        await self._shutdown_event.wait()

    async def stop(self, wait: bool = True) -> None:
        """워커 종료

        Args:
            wait: True면 진행 중인 태스크 완료까지 대기
        """
        if self.state == WorkerState.STOPPED:
            return

        self.state = WorkerState.STOPPING
        self._running = False

        logger.info(f"Stopping worker {self.worker_id}...")

        if wait:
            # 진행 중인 태스크 완료 대기
            for task in self._tasks:
                task.cancel()

            await asyncio.gather(*self._tasks, return_exceptions=True)
        else:
            # 즉시 취소
            for task in self._tasks:
                task.cancel()

        # 연결 해제
        if self.broker:
            await self.broker.disconnect()
        if self.backend:
            await self.backend.disconnect()

        self.state = WorkerState.STOPPED
        self._shutdown_event.set()
        logger.info(f"Worker {self.worker_id} stopped")

    def shutdown(self) -> None:
        """워커 종료 요청 (시그널 핸들러용)"""
        if self._running:
            self._running = False
            logger.info("Shutdown requested...")

    async def _worker_loop(self, worker_num: int) -> None:
        """워커 루프"""
        logger.debug(f"Worker {worker_num} started")
        tasks_count = 0

        try:
            async for message, delivery_tag in self.broker.consume(
                self.config.queues,
                prefetch_count=self.config.prefetch_count,
            ):
                if not self._running:
                    # NACK하고 종료
                    await self.broker.nack(delivery_tag, requeue=True)
                    break

                try:
                    await self._process_message(message, delivery_tag)
                    tasks_count += 1

                    # 최대 태스크 수 확인
                    if (
                        self.config.max_tasks_per_child > 0
                        and tasks_count >= self.config.max_tasks_per_child
                    ):
                        logger.info(
                            f"Worker {worker_num} reached max tasks, restarting..."
                        )
                        break

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await self.broker.nack(delivery_tag, requeue=False)

        except asyncio.CancelledError:
            logger.debug(f"Worker {worker_num} cancelled")
        except Exception as e:
            logger.error(f"Worker {worker_num} error: {e}")
        finally:
            logger.debug(f"Worker {worker_num} stopped")

    async def _process_message(
        self,
        message: TaskMessage,
        delivery_tag: Any,
    ) -> None:
        """메시지 처리"""
        task_id = message.task_id
        task_name = message.task_name

        logger.debug(f"Processing task {task_name}[{task_id}]")

        # 태스크 조회
        task = self.app.registry.get(task_name)
        if task is None:
            logger.error(f"Unknown task: {task_name}")
            await self._store_failure(
                task_id,
                error=f"Unknown task: {task_name}",
                error_type="KeyError",
            )
            await self.broker.ack(delivery_tag)
            return

        # STARTED 상태 업데이트
        if self.backend and task.track_started:
            await self.backend.update_status(task_id, TaskStatus.STARTED)

        # 태스크 실행
        try:
            result = await self._execute_task(task, message)

            # 성공
            self._tasks_succeeded += 1
            if self.backend and not task.ignore_result:
                await self._store_success(task_id, result)

            # ACK
            if not task.acks_late:
                await self.broker.ack(delivery_tag)

        except TaskRetryError as e:
            # 재시도
            self._tasks_retried += 1
            await self._handle_retry(message, task, e)
            await self.broker.ack(delivery_tag)

        except TaskRejectError as e:
            # 거부 (재시도 없이 실패)
            self._tasks_failed += 1
            await self._store_failure(
                task_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            await self.broker.ack(delivery_tag)

        except TaskTimeoutError as e:
            # 타임아웃
            self._tasks_failed += 1
            if message.can_retry():
                await self._handle_retry(message, task)
            else:
                await self._store_failure(
                    task_id,
                    error=str(e),
                    error_type="TaskTimeoutError",
                )
            await self.broker.ack(delivery_tag)

        except Exception as e:
            # 일반 예외
            self._tasks_failed += 1

            # autoretry_for 확인
            if task.autoretry_for and isinstance(e, task.autoretry_for):
                if message.can_retry():
                    await self._handle_retry(message, task)
                    await self.broker.ack(delivery_tag)
                    return

            # 일반 재시도 확인
            if message.can_retry():
                await self._handle_retry(message, task)
            else:
                await self._store_failure(
                    task_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    tb=traceback.format_exc(),
                )

            await self.broker.ack(delivery_tag)

        finally:
            self._tasks_processed += 1

            # acks_late인 경우 여기서 ACK
            if task.acks_late and self._running:
                await self.broker.ack(delivery_tag)

    async def _execute_task(
        self,
        task: Any,  # Task model
        message: TaskMessage,
    ) -> Any:
        """태스크 실행"""
        func = task.func
        if func is None:
            raise ValueError(f"Task {task.name} has no function")

        # 타임아웃 설정
        timeout = task.timeout or self.config.task_timeout

        try:
            # 비동기 실행
            if asyncio.iscoroutinefunction(func):
                coro = func(*message.args, **message.kwargs)
                return await asyncio.wait_for(coro, timeout=timeout)
            else:
                # 동기 함수는 executor에서 실행
                loop = asyncio.get_running_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(
                        None, lambda: func(*message.args, **message.kwargs)
                    ),
                    timeout=timeout,
                )

        except asyncio.TimeoutError:
            raise TaskTimeoutError(
                f"Task {task.name} timed out after {timeout}s",
                task_id=message.task_id,
            )

    async def _handle_retry(
        self,
        message: TaskMessage,
        task: Any,
        retry_error: TaskRetryError | None = None,
    ) -> None:
        """재시도 처리"""
        # 재시도 횟수 증가
        new_retries = message.retries + 1

        # 재시도 지연 계산
        if retry_error and retry_error.countdown:
            countdown = retry_error.countdown
        elif retry_error and retry_error.eta:
            eta = retry_error.eta
            countdown = None
        else:
            countdown = task.get_retry_delay(new_retries)
            eta = None

        # 새 메시지 생성
        new_message = TaskMessage(
            task_id=message.task_id,
            task_name=message.task_name,
            args=message.args,
            kwargs=message.kwargs,
            queue=message.queue,
            priority=message.priority,
            countdown=countdown,
            eta=retry_error.eta if retry_error else None,
            expires=message.expires,
            retries=new_retries,
            max_retries=message.max_retries,
            correlation_id=message.correlation_id,
            root_id=message.root_id,
            parent_id=message.parent_id,
        )

        # 상태 업데이트
        if self.backend:
            await self.backend.update_status(
                message.task_id,
                TaskStatus.RETRY,
            )

        # 브로커에 다시 발행
        await self.broker.publish(new_message)

        logger.info(
            f"Task {message.task_name}[{message.task_id}] "
            f"retry {new_retries}/{message.max_retries}"
        )

    async def _store_success(self, task_id: str, result: Any) -> None:
        """성공 결과 저장"""
        if not self.backend:
            return

        task_result = TaskResult(
            task_id=task_id,
            status=TaskStatus.SUCCESS,
            result=result,
            completed_at=datetime.now(),
            worker_id=self.worker_id,
        )

        await self.backend.store_result(
            task_id,
            task_result,
            ttl=self.config.result_expires,
        )

    async def _store_failure(
        self,
        task_id: str,
        *,
        error: str,
        error_type: str = "Exception",
        tb: str | None = None,
    ) -> None:
        """실패 결과 저장"""
        if not self.backend:
            return

        task_result = TaskResult(
            task_id=task_id,
            status=TaskStatus.FAILURE,
            error=error,
            error_type=error_type,
            traceback=tb,
            completed_at=datetime.now(),
            worker_id=self.worker_id,
        )

        await self.backend.store_result(
            task_id,
            task_result,
            ttl=self.config.result_expires,
        )


# =============================================================================
# Worker Runner
# =============================================================================


async def run_worker(
    app: "TaskApp",
    *,
    concurrency: int = 1,
    queues: list[str] | None = None,
    **kwargs: Any,
) -> None:
    """워커 실행 헬퍼

    Examples:
        await run_worker(task_app, concurrency=4, queues=["default", "high"])
    """
    config = WorkerConfig(
        concurrency=concurrency,
        queues=queues or ["default"],
        **kwargs,
    )

    worker = Worker(app, config=config)

    # 시그널 핸들러 설정
    loop = asyncio.get_running_loop()

    def signal_handler() -> None:
        worker.shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows에서는 지원 안함
            pass

    try:
        await worker.start()
    finally:
        await worker.stop()
