"""DistributedTaskBackend - 분산 태스크 백엔드

Redis 브로커를 사용하여 여러 인스턴스에서 태스크를 분산 처리합니다.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from bloom.log import get_logger
from bloom.task.backend import TaskBackend
from bloom.task.broker import Broker, InMemoryBroker, RedisBroker
from bloom.task.message import TaskMessage, TaskState
from bloom.task.message import TaskResult as TaskResultMessage
from bloom.task.registry import TaskRegistry
from bloom.task.result import AbstractTaskResult, ScheduledTask

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager

T = TypeVar("T")
logger = get_logger(__name__)


class DistributedTaskResult[T](AbstractTaskResult[T]):
    """
    분산 태스크 결과

    브로커에 저장된 결과를 폴링 방식으로 조회합니다.
    """

    def __init__(
        self,
        task_id: str,
        broker: Broker,
        poll_interval: float = 0.1,
    ):
        self._task_id = task_id
        self._broker = broker
        self._poll_interval = poll_interval
        self._cached_result: TaskResultMessage | None = None

    @property
    def task_id(self) -> str:
        return self._task_id

    async def _fetch_result(self) -> TaskResultMessage | None:
        """브로커에서 결과 조회 (캐싱)"""
        if self._cached_result is not None and self._cached_result.is_ready:
            return self._cached_result
        self._cached_result = await self._broker.get_result(self._task_id)
        return self._cached_result

    async def get(self, timeout: float | None = None) -> T:
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
        start_time = datetime.now()

        while True:
            result = await self._fetch_result()

            if result is not None and result.is_ready:
                if result.is_failed:
                    raise RuntimeError(result.error or "Task failed")
                return result.result

            # 타임아웃 체크
            if timeout is not None:
                elapsed = (datetime.now() - start_time).total_seconds()
                if elapsed >= timeout:
                    raise TimeoutError(
                        f"Task {self._task_id} did not complete within {timeout}s"
                    )

            await asyncio.sleep(self._poll_interval)

    async def ready(self) -> bool:
        """태스크가 완료되었는지 확인"""
        result = await self._fetch_result()
        return result is not None and result.is_ready

    async def successful(self) -> bool:
        """태스크가 성공적으로 완료되었는지 확인"""
        result = await self._fetch_result()
        return result is not None and result.is_successful

    async def failed(self) -> bool:
        """태스크가 실패했는지 확인"""
        result = await self._fetch_result()
        return result is not None and result.is_failed

    async def state(self) -> TaskState:
        """현재 상태"""
        result = await self._fetch_result()
        return result.state if result else TaskState.PENDING

    def revoke(self) -> bool:
        """
        태스크 취소를 시도합니다.

        Note:
            분산 환경에서는 이미 큐에 들어간 태스크를 취소하기 어렵습니다.
            현재는 지원하지 않으며, 항상 False를 반환합니다.

        Returns:
            False (미지원)
        """
        # TODO: 브로커에 취소 메시지를 보내는 방식으로 구현 가능
        return False

    def __repr__(self) -> str:
        return f"<DistributedTaskResult {self._task_id[:8]}...>"


class DistributedTaskBackend[**P, T](TaskBackend[P, T]):
    """
    분산 태스크 백엔드

    Redis 브로커를 사용하여 여러 Bloom 인스턴스에서 태스크를 분산 처리합니다.

    **아키텍처:**

    ```
    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
    │   Producer   │     │    Worker    │     │    Worker    │
    │ (enqueue)    │     │  (dequeue)   │     │  (dequeue)   │
    └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
           │                    │                    │
           └────────────────────┼────────────────────┘
                                │
                         ┌──────▼──────┐
                         │    Redis    │
                         │  - Queue    │
                         │  - Results  │
                         └─────────────┘
    ```

    **사용법 (Producer):**

    ```python
    from bloom.task.distributed import DistributedTaskBackend
    from bloom.task.broker import RedisBroker

    @Component
    class TaskConfig:
        @Factory
        async def task_backend(self) -> TaskBackend:
            broker = RedisBroker("redis://localhost:6379/0")
            backend = DistributedTaskBackend(broker)
            await backend.start()
            return backend
    ```

    **사용법 (Worker):**

    ```python
    # worker.py
    import asyncio
    from bloom import Application
    from bloom.task.distributed import DistributedTaskBackend

    app = Application("worker").scan(my_module)
    asyncio.run(app.ready_async())

    # 워커 시작 (태스크 처리)
    backend = app.manager.get_instance(DistributedTaskBackend)
    await backend.start_worker(app.manager)
    ```
    """

    def __init__(
        self,
        broker: Broker | None = None,
        redis_url: str | None = None,
        queue: str = "default",
        worker_count: int = 1,
        poll_interval: float = 0.1,
    ):
        """
        Args:
            broker: 브로커 인스턴스 (None이면 InMemoryBroker)
            redis_url: Redis URL (broker가 None일 때 RedisBroker 생성)
            queue: 기본 큐 이름
            worker_count: 워커 수 (start_worker 시)
            poll_interval: 결과 폴링 간격 (초)
        """
        if broker is None:
            if redis_url:
                broker = RedisBroker(redis_url)
            else:
                broker = InMemoryBroker()

        self._broker = broker
        self._queue = queue
        self._worker_count = worker_count
        self._poll_interval = poll_interval

        self._registry: TaskRegistry | None = None
        self._running = False
        self._worker_tasks: list[asyncio.Task] = []
        self._scheduled_tasks: dict[str, ScheduledTask] = {}
        self._scheduler_task: asyncio.Task | None = None

    @property
    def broker(self) -> Broker:
        """브로커"""
        return self._broker

    @property
    def registry(self) -> TaskRegistry | None:
        """태스크 레지스트리"""
        return self._registry

    @property
    def is_running(self) -> bool:
        """워커 실행 중 여부"""
        return self._running

    async def start(self) -> None:
        """백엔드 시작 (브로커 연결)"""
        if not self._broker.is_connected:
            await self._broker.connect()
        logger.info("DistributedTaskBackend started")

    async def shutdown(self, wait: bool = True) -> None:
        """백엔드 종료"""
        self._running = False

        # 워커 태스크 취소
        for task in self._worker_tasks:
            task.cancel()
            if wait:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._worker_tasks.clear()

        # 스케줄러 태스크 취소
        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        # 브로커 연결 해제
        if self._broker.is_connected:
            await self._broker.disconnect()

        logger.info("DistributedTaskBackend shutdown")

    def submit(
        self,
        fn: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> DistributedTaskResult[T]:
        """
        태스크를 큐에 추가 (동기 API)

        Note:
            분산 백엔드에서는 함수 자체가 아닌 "태스크 이름"으로 전달됩니다.
            따라서 fn은 @Task로 등록된 메서드여야 합니다.
        """
        # 태스크 이름 추출
        task_name = self._get_task_name(fn)

        # 메시지 생성
        message = TaskMessage(
            task_name=task_name,
            args=args,
            kwargs=kwargs,
        )

        # 동기 컨텍스트에서 비동기 enqueue 호출
        try:
            loop = asyncio.get_running_loop()
            # 이벤트 루프가 실행 중이면 run_coroutine_threadsafe로 완료 대기
            future = asyncio.run_coroutine_threadsafe(
                self._enqueue_message(message), loop
            )
            future.result(timeout=5.0)  # 완료 대기 (최대 5초)
        except RuntimeError:
            # 이벤트 루프가 없으면 새로 생성
            asyncio.run(self._enqueue_message(message))

        return DistributedTaskResult(
            task_id=message.task_id,
            broker=self._broker,
            poll_interval=self._poll_interval,
        )

    async def submit_async(
        self,
        fn: Callable[P, T],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> DistributedTaskResult[T]:
        """태스크를 큐에 추가 (비동기 API)"""
        task_name = self._get_task_name(fn)

        message = TaskMessage(
            task_name=task_name,
            args=args,
            kwargs=kwargs,
        )

        await self._enqueue_message(message)

        return DistributedTaskResult(
            task_id=message.task_id,
            broker=self._broker,
            poll_interval=self._poll_interval,
        )

    def submit_by_name(
        self,
        task_name: str,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> DistributedTaskResult[T]:
        """
        태스크 이름으로 큐에 추가 (동기 API)

        BoundTask.delay()에서 사용됩니다.
        """
        message = TaskMessage(
            task_name=task_name,
            args=args,
            kwargs=kwargs or {},
        )

        # 동기 컨텍스트에서 비동기 enqueue 호출
        try:
            loop = asyncio.get_running_loop()
            # 이벤트 루프가 실행 중이면 run_coroutine_threadsafe로 완료 대기
            future = asyncio.run_coroutine_threadsafe(
                self._enqueue_message(message), loop
            )
            future.result(timeout=5.0)  # 완료 대기 (최대 5초)
        except RuntimeError:
            # 이벤트 루프가 없으면 새로 생성
            asyncio.run(self._enqueue_message(message))

        return DistributedTaskResult(
            task_id=message.task_id,
            broker=self._broker,
            poll_interval=self._poll_interval,
        )

    async def submit_by_name_async(
        self,
        task_name: str,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> DistributedTaskResult[T]:
        """
        태스크 이름으로 큐에 추가 (비동기 API)

        BoundTask.delay_async()에서 사용됩니다.
        """
        message = TaskMessage(
            task_name=task_name,
            args=args,
            kwargs=kwargs or {},
        )

        await self._enqueue_message(message)

        return DistributedTaskResult(
            task_id=message.task_id,
            broker=self._broker,
            poll_interval=self._poll_interval,
        )

    async def _enqueue_message(self, message: TaskMessage) -> None:
        """메시지를 큐에 추가"""
        # PENDING 상태 저장
        result = TaskResultMessage(task_id=message.task_id, state=TaskState.PENDING)
        await self._broker.set_result(result)

        # 큐에 추가
        await self._broker.enqueue(message, queue=self._queue)
        logger.info(
            f"[Task SUBMITTED] {message.task_name} | "
            f"task_id={message.task_id[:8]}..."
        )

    def _get_task_name(self, fn: Callable) -> str:
        """함수에서 태스크 이름 추출"""
        # BoundTask나 프록시에서 원본 핸들러 추출
        if hasattr(fn, "_handler"):
            fn = fn._handler

        # 클래스.메서드 형태로 이름 생성
        if hasattr(fn, "__self__"):
            # 바운드 메서드
            cls_name = fn.__self__.__class__.__name__
            return f"{cls_name}.{fn.__name__}"
        elif hasattr(fn, "__qualname__"):
            # 언바운드 메서드
            parts = fn.__qualname__.split(".")
            if len(parts) >= 2:
                return f"{parts[-2]}.{parts[-1]}"

        return fn.__name__

    def schedule(self, task: ScheduledTask) -> ScheduledTask:
        """태스크를 스케줄에 등록"""
        self._scheduled_tasks[task.name] = task
        return task

    def unschedule(self, task: ScheduledTask) -> bool:
        """스케줄에서 태스크 제거"""
        if task.name in self._scheduled_tasks:
            del self._scheduled_tasks[task.name]
            task.cancel()
            return True
        return False

    # =========================================================================
    # 워커 관련 메서드
    # =========================================================================

    async def start_worker(
        self,
        manager: ContainerManager,
        worker_count: int | None = None,
    ) -> None:
        """
        워커 시작 (태스크 처리)

        Args:
            manager: ContainerManager (DI용)
            worker_count: 워커 수 (None이면 기본값)
        """
        if self._running:
            return

        self._running = True
        count = worker_count or self._worker_count

        # 태스크 레지스트리 스캔
        self._registry = TaskRegistry()
        self._registry.scan(manager)

        # 브로커 연결
        if not self._broker.is_connected:
            await self._broker.connect()

        # 워커 태스크 시작
        for i in range(count):
            task = asyncio.create_task(self._worker_loop(i), name=f"task-worker-{i}")
            self._worker_tasks.append(task)

        # 스케줄러 시작
        self._scheduler_task = asyncio.create_task(
            self._scheduler_loop(), name="task-scheduler"
        )

        logger.info(f"Started {count} workers")

    async def _worker_loop(self, worker_id: int) -> None:
        """워커 메인 루프"""
        logger.info(f"Worker {worker_id} started")

        while self._running:
            try:
                # 큐에서 메시지 가져오기 (블로킹)
                message = await self._broker.dequeue(queue=self._queue, timeout=1.0)

                if message is None:
                    continue

                # 태스크 실행
                await self._execute_task(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(1)

        logger.info(f"Worker {worker_id} stopped")

    async def _execute_task(self, message: TaskMessage) -> None:
        """태스크 실행"""
        task_id = message.task_id
        task_name = message.task_name

        logger.info(
            f"[Task STARTED] {task_name} | "
            f"task_id={task_id[:8]}... | "
            f"args={message.args} kwargs={message.kwargs}"
        )

        # STARTED 상태 저장
        result = TaskResultMessage(
            task_id=task_id,
            state=TaskState.STARTED,
            started_at=datetime.now(),
        )
        await self._broker.set_result(result)

        try:
            # 레지스트리에서 핸들러 조회
            if self._registry is None:
                raise RuntimeError("TaskRegistry is not initialized")

            task_info = self._registry.get(task_name)
            if task_info is None:
                raise RuntimeError(f"Unknown task: {task_name}")

            # 태스크 실행
            start_time = datetime.now()
            value = await task_info.execute_async(*message.args, **message.kwargs)
            elapsed = (datetime.now() - start_time).total_seconds()

            # SUCCESS 상태 저장
            result = TaskResultMessage(
                task_id=task_id,
                state=TaskState.SUCCESS,
                result=value,
                started_at=result.started_at,
                completed_at=datetime.now(),
            )
            await self._broker.set_result(result)
            logger.info(
                f"[Task SUCCESS] {task_name} | "
                f"task_id={task_id[:8]}... | "
                f"elapsed={elapsed:.3f}s"
            )

        except Exception as e:
            import traceback

            # 재시도 처리
            if message.retries < message.max_retries:
                message.retries += 1
                await asyncio.sleep(message.retry_delay)
                await self._broker.enqueue(message, queue=self._queue)
                logger.warning(
                    f"[Task RETRY] {task_name} | "
                    f"task_id={task_id[:8]}... | "
                    f"attempt={message.retries}/{message.max_retries} | "
                    f"error={e}"
                )
                return

            # FAILURE 상태 저장
            result = TaskResultMessage(
                task_id=task_id,
                state=TaskState.FAILURE,
                error=str(e),
                traceback=traceback.format_exc(),
                started_at=result.started_at,
                completed_at=datetime.now(),
            )
            await self._broker.set_result(result)
            logger.error(
                f"[Task FAILED] {task_name} | "
                f"task_id={task_id[:8]}... | "
                f"error={e}"
            )

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
                    # 태스크를 큐에 추가
                    task_name = self._get_task_name(task.handler)
                    message = TaskMessage(
                        task_name=task_name,
                        args=task.args,
                        kwargs=task.kwargs,
                    )
                    await self._broker.enqueue(message, queue=self._queue)
                    task._last_execution = now

            await asyncio.sleep(0.1)

    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        workers = len(self._worker_tasks)
        return f"<DistributedTaskBackend {status} workers={workers}>"
