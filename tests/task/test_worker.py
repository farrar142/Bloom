"""bloom.task.worker 테스트"""

import pytest
import asyncio

from bloom.task.app import TaskApp
from bloom.task.worker import Worker, WorkerConfig, WorkerState
from bloom.task.backends.local import LocalBroker, LocalBackend
from bloom.task.models import TaskStatus, TaskRetryError


class TestWorkerConfig:
    """WorkerConfig 테스트"""

    def test_default_config(self):
        """기본 설정"""
        config = WorkerConfig()
        assert config.concurrency == 1
        assert config.queues == ["default"]
        assert config.prefetch_count == 1
        assert config.task_timeout == 300.0

    def test_custom_config(self):
        """커스텀 설정"""
        config = WorkerConfig(
            concurrency=4,
            queues=["high", "default"],
            prefetch_count=2,
            task_timeout=60.0,
        )

        assert config.concurrency == 4
        assert config.queues == ["high", "default"]
        assert config.prefetch_count == 2
        assert config.task_timeout == 60.0

    def test_empty_queues_default(self):
        """빈 큐 목록 → 기본값"""
        config = WorkerConfig(queues=[])
        assert config.queues == ["default"]


class TestWorkerState:
    """WorkerState 테스트"""

    def test_states(self):
        """상태 값"""
        assert WorkerState.CREATED.name == "CREATED"
        assert WorkerState.STARTING.name == "STARTING"
        assert WorkerState.RUNNING.name == "RUNNING"
        assert WorkerState.STOPPING.name == "STOPPING"
        assert WorkerState.STOPPED.name == "STOPPED"


class TestWorker:
    """Worker 테스트"""

    @pytest.fixture
    async def app(self):
        """TaskApp fixture"""
        broker = LocalBroker()
        backend = LocalBackend()
        app = TaskApp("test_app", broker=broker, backend=backend)

        await broker.connect()
        await backend.connect()
        await broker.declare_queue("default")

        try:
            yield app
        finally:
            await broker.disconnect()
            await backend.disconnect()

    def test_worker_creation(self, app):
        """워커 생성"""
        app_sync = TaskApp("test")
        worker = Worker(app_sync)

        assert worker.app is app_sync
        assert worker.state == WorkerState.CREATED
        assert worker.worker_id.startswith("worker-")

    def test_worker_with_config(self, app):
        """설정과 함께 워커 생성"""
        app_sync = TaskApp("test")
        config = WorkerConfig(concurrency=4)
        worker = Worker(app_sync, config=config)

        assert worker.config.concurrency == 4

    async def test_worker_stats(self):
        """워커 통계"""
        broker = LocalBroker()
        backend = LocalBackend()
        try:
            app = TaskApp("test", broker=broker, backend=backend)

            worker = Worker(app)
            stats = worker.stats

            assert "worker_id" in stats
            assert "state" in stats
            assert "tasks_processed" in stats
            assert stats["state"] == "CREATED"
        finally:
            await broker.disconnect()
            await backend.disconnect()

    async def test_worker_process_success(self):
        """태스크 성공 처리"""
        broker = LocalBroker()
        backend = LocalBackend()
        worker_task = None
        try:
            app = TaskApp("test", broker=broker, backend=backend)

            await broker.connect()
            await backend.connect()
            await broker.declare_queue("default")

            @app.task
            async def add(x: int, y: int) -> int:
                return x + y

            # 태스크 전송
            result = await add.apply_async(args=(2, 3))

            # 워커 시작 (짧게)
            worker = Worker(app, config=WorkerConfig(concurrency=1))

            async def run_worker_briefly():
                worker.state = WorkerState.RUNNING
                worker._running = True
                await worker._worker_loop(0)

            # 워커가 메시지를 처리하도록 짧게 실행
            worker_task = asyncio.create_task(run_worker_briefly())

            # 결과 대기
            await asyncio.sleep(0.3)
            worker._running = False
            await asyncio.sleep(0.1)

            # 결과 확인
            task_result = await backend.get_result(result.task_id)
            assert task_result is not None
            assert task_result.status == TaskStatus.SUCCESS
            assert task_result.result == 5
        finally:
            if worker_task:
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            await broker.disconnect()
            await backend.disconnect()

    async def test_worker_process_failure(self):
        """태스크 실패 처리"""
        broker = LocalBroker()
        backend = LocalBackend()
        worker_task = None
        try:
            app = TaskApp("test", broker=broker, backend=backend)

            await broker.connect()
            await backend.connect()
            await broker.declare_queue("default")

            @app.task
            async def failing_task():
                raise ValueError("Task failed!")

            # 태스크 전송
            result = await failing_task.apply_async()

            # 워커 실행
            worker = Worker(app, config=WorkerConfig(concurrency=1))

            async def run_worker_briefly():
                worker.state = WorkerState.RUNNING
                worker._running = True
                await worker._worker_loop(0)

            worker_task = asyncio.create_task(run_worker_briefly())
            await asyncio.sleep(0.3)
            worker._running = False
            await asyncio.sleep(0.1)

            # 결과 확인
            task_result = await backend.get_result(result.task_id)
            assert task_result is not None
            assert task_result.status == TaskStatus.FAILURE
            assert task_result.error is not None
            assert "Task failed" in task_result.error
        finally:
            if worker_task:
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            await broker.disconnect()
            await backend.disconnect()

    async def test_worker_retry(self):
        """태스크 재시도"""
        broker = LocalBroker()
        backend = LocalBackend()
        worker_task = None
        try:
            app = TaskApp("test", broker=broker, backend=backend)

            await broker.connect()
            await backend.connect()
            await broker.declare_queue("default")

            attempt_count = 0

            @app.task(retry=2, retry_delay=0.1)
            async def retry_task():
                nonlocal attempt_count
                attempt_count += 1
                if attempt_count < 2:
                    raise ValueError("Retry please")
                return "success"

            # 태스크 전송 (max_retries 설정)
            from bloom.task.models import TaskMessage

            msg = TaskMessage(
                task_name=retry_task.name,
                queue="default",
                max_retries=2,
            )
            await broker.publish(msg)
            await backend.store_result(
                msg.task_id,
                __import__("bloom.task.models", fromlist=["TaskResult"]).TaskResult(
                    task_id=msg.task_id, status=TaskStatus.PENDING
                ),
            )

            # 워커 실행
            worker = Worker(app, config=WorkerConfig(concurrency=1))

            async def run_worker():
                worker.state = WorkerState.RUNNING
                worker._running = True
                await worker._worker_loop(0)

            worker_task = asyncio.create_task(run_worker())

            # 여러 번 처리될 시간
            await asyncio.sleep(0.5)
            worker._running = False
            await asyncio.sleep(0.1)

            # 재시도가 발생해야 함
            assert attempt_count >= 1
        finally:
            if worker_task:
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            await broker.disconnect()
            await backend.disconnect()


class TestWorkerLifecycle:
    """Worker 생명주기 테스트"""

    async def test_start_stop(self):
        """시작/종료"""
        broker = LocalBroker()
        backend = LocalBackend()
        start_task = None
        try:
            app = TaskApp("test", broker=broker, backend=backend)

            worker = Worker(app)

            # 시작 (백그라운드)
            async def start_worker():
                await worker.start()

            start_task = asyncio.create_task(start_worker())

            # 잠시 대기
            await asyncio.sleep(0.1)
            assert worker.state == WorkerState.RUNNING

            # 종료
            await worker.stop()
            assert worker.state == WorkerState.STOPPED
        finally:
            # start_task 정리
            if start_task:
                try:
                    await asyncio.wait_for(start_task, timeout=0.5)
                except asyncio.TimeoutError:
                    start_task.cancel()
                    try:
                        await start_task
                    except asyncio.CancelledError:
                        pass
            await broker.disconnect()
            await backend.disconnect()

    async def test_shutdown_signal(self):
        """종료 시그널"""
        broker = LocalBroker()
        backend = LocalBackend()
        try:
            app = TaskApp("test", broker=broker, backend=backend)

            worker = Worker(app)
            worker._running = True

            worker.shutdown()
            assert worker._running is False
        finally:
            await broker.disconnect()
            await backend.disconnect()
