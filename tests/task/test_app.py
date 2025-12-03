"""bloom.core.task.app 테스트"""

import pytest
import asyncio

from bloom.core.task.app import TaskApp, TaskRegistry, AsyncResult, BoundTask
from bloom.core.task.backends.local import LocalBroker, LocalBackend
from bloom.core.task.models import TaskStatus, TaskPriority


class TestTaskRegistry:
    """TaskRegistry 테스트"""

    def test_register_task(self):
        """태스크 등록"""
        from bloom.core.task.models import Task

        registry = TaskRegistry()
        task = Task(name="test.task")

        registry.register(task)
        assert "test.task" in registry
        assert len(registry) == 1

    def test_get_task(self):
        """태스크 조회"""
        from bloom.core.task.models import Task

        registry = TaskRegistry()
        task = Task(name="test.task")
        registry.register(task)

        retrieved = registry.get("test.task")
        assert retrieved is task

    def test_get_nonexistent_task(self):
        """존재하지 않는 태스크 조회"""
        registry = TaskRegistry()
        assert registry.get("nonexistent") is None

    def test_unregister_task(self):
        """태스크 등록 해제"""
        from bloom.core.task.models import Task

        registry = TaskRegistry()
        task = Task(name="test.task")
        registry.register(task)

        result = registry.unregister("test.task")
        assert result is True
        assert "test.task" not in registry

    def test_get_all_tasks(self):
        """모든 태스크 조회"""
        from bloom.core.task.models import Task

        registry = TaskRegistry()
        task1 = Task(name="task1")
        task2 = Task(name="task2")

        registry.register(task1)
        registry.register(task2)

        all_tasks = registry.get_all()
        assert len(all_tasks) == 2
        assert "task1" in all_tasks
        assert "task2" in all_tasks


class TestTaskApp:
    """TaskApp 테스트"""

    def test_app_creation(self):
        """앱 생성"""
        app = TaskApp("test_app")
        assert app.name == "test_app"
        assert app.broker is None
        assert app.backend is None

    def test_app_with_broker_backend(self):
        """브로커/백엔드와 함께 생성"""
        broker = LocalBroker()
        backend = LocalBackend()

        app = TaskApp("test_app", broker=broker, backend=backend)
        assert app.broker is broker
        assert app.backend is backend

    def test_task_decorator(self):
        """@task 데코레이터"""
        app = TaskApp("test_app")

        @app.task
        async def my_task(x: int) -> int:
            return x * 2

        assert isinstance(my_task, BoundTask)
        assert my_task.name.endswith("my_task")
        assert "my_task" in my_task.name

    def test_task_decorator_with_options(self):
        """@task 데코레이터 옵션"""
        app = TaskApp("test_app")

        @app.task(
            name="custom.task.name",
            queue="high",
            retry=3,
            timeout=60,
            priority=TaskPriority.HIGH,
        )
        async def my_task():
            pass

        assert my_task.name == "custom.task.name"
        assert my_task.task.queue == "high"
        assert my_task.task.retry == 3
        assert my_task.task.timeout == 60
        assert my_task.task.priority == TaskPriority.HIGH

    def test_task_registration(self):
        """태스크가 레지스트리에 등록됨"""
        app = TaskApp("test_app")

        @app.task
        async def task1():
            pass

        @app.task
        async def task2():
            pass

        assert len(app.registry) == 2

    async def test_task_direct_call(self):
        """태스크 직접 호출"""
        app = TaskApp("test_app")

        @app.task
        async def add(x: int, y: int) -> int:
            return x + y

        result = await add(2, 3)
        assert result == 5

    def test_get_task(self):
        """이름으로 태스크 조회"""
        app = TaskApp("test_app")

        @app.task(name="my.task")
        async def my_task():
            pass

        retrieved = app.get_task("my.task")
        assert retrieved is not None
        assert retrieved.name == "my.task"

    def test_get_nonexistent_task(self):
        """존재하지 않는 태스크 조회"""
        app = TaskApp("test_app")
        assert app.get_task("nonexistent") is None


class TestBoundTask:
    """BoundTask 테스트"""

    @pytest.fixture
    async def app(self):
        """TaskApp fixture"""
        broker = LocalBroker()
        backend = LocalBackend()
        app = TaskApp("test_app", broker=broker, backend=backend)

        await broker.connect()
        await backend.connect()
        await broker.declare_queue("default")

        yield app

        await broker.disconnect()
        await backend.disconnect()

    async def test_delay(self, app):
        """delay() 메서드"""

        @app.task
        async def my_task(x: int) -> int:
            return x * 2

        # delay는 동기 메서드이므로 현재 이벤트 루프와 충돌
        # apply_async를 직접 테스트
        result = await my_task.apply_async(args=(5,))

        assert isinstance(result, AsyncResult)
        assert result.task_id is not None

    async def test_apply_async(self, app):
        """apply_async() 메서드"""

        @app.task
        async def process_data(data: str) -> str:
            return f"processed: {data}"

        result = await process_data.apply_async(
            args=("test_data",),
            queue="default",
        )

        assert isinstance(result, AsyncResult)

    async def test_apply_async_with_options(self, app):
        """apply_async() 옵션"""
        from datetime import datetime, timedelta

        @app.task
        async def scheduled_task():
            pass

        eta = datetime.now() + timedelta(hours=1)
        result = await scheduled_task.apply_async(
            countdown=60,
            priority=TaskPriority.HIGH,
        )

        assert isinstance(result, AsyncResult)


class TestAsyncResult:
    """AsyncResult 테스트"""

    @pytest.fixture
    async def app(self):
        """TaskApp fixture"""
        broker = LocalBroker()
        backend = LocalBackend()
        app = TaskApp("test_app", broker=broker, backend=backend)

        await broker.connect()
        await backend.connect()

        yield app

        await broker.disconnect()
        await backend.disconnect()

    async def test_status(self, app):
        """상태 조회"""
        from bloom.core.task.models import TaskResult

        # 결과 저장
        task_result = TaskResult(
            task_id="test-123",
            status=TaskStatus.SUCCESS,
        )
        await app.backend.store_result("test-123", task_result)

        # AsyncResult로 조회
        result = AsyncResult("test-123", app=app)
        status = await result.status_async()

        assert status == TaskStatus.SUCCESS

    async def test_ready(self, app):
        """완료 여부"""
        from bloom.core.task.models import TaskResult

        # PENDING
        pending = TaskResult(task_id="pending", status=TaskStatus.PENDING)
        await app.backend.store_result("pending", pending)

        result1 = AsyncResult("pending", app=app)
        assert await result1.ready_async() is False

        # SUCCESS
        success = TaskResult(task_id="success", status=TaskStatus.SUCCESS)
        await app.backend.store_result("success", success)

        result2 = AsyncResult("success", app=app)
        assert await result2.ready_async() is True

    async def test_successful(self, app):
        """성공 여부"""
        from bloom.core.task.models import TaskResult

        success = TaskResult(
            task_id="success",
            status=TaskStatus.SUCCESS,
            result="done",
        )
        await app.backend.store_result("success", success)

        result = AsyncResult("success", app=app)
        assert await result.successful_async() is True

    async def test_failed(self, app):
        """실패 여부"""
        from bloom.core.task.models import TaskResult

        failure = TaskResult(
            task_id="failure",
            status=TaskStatus.FAILURE,
            error="Something went wrong",
        )
        await app.backend.store_result("failure", failure)

        result = AsyncResult("failure", app=app)
        assert await result.failed_async() is True

    async def test_get_success(self, app):
        """성공 결과 가져오기"""
        from bloom.core.task.models import TaskResult

        task_result = TaskResult(
            task_id="test-123",
            status=TaskStatus.SUCCESS,
            result={"data": "value"},
        )
        await app.backend.store_result("test-123", task_result)

        result = AsyncResult("test-123", app=app)
        value = await result.get_async(timeout=1.0)

        assert value == {"data": "value"}

    async def test_get_timeout(self, app):
        """결과 대기 타임아웃"""
        result = AsyncResult("nonexistent", app=app)

        with pytest.raises(TimeoutError):
            await result.get_async(timeout=0.1)


class TestSendTask:
    """send_task() 테스트"""

    @pytest.fixture
    async def app(self):
        """TaskApp fixture"""
        broker = LocalBroker()
        backend = LocalBackend()
        app = TaskApp("test_app", broker=broker, backend=backend)

        await broker.connect()
        await backend.connect()
        await broker.declare_queue("default")

        yield app

        await broker.disconnect()
        await backend.disconnect()

    async def test_send_registered_task(self, app):
        """등록된 태스크 전송"""

        @app.task(name="registered.task")
        async def my_task():
            pass

        result = await app.send_task(
            "registered.task",
            args=(1, 2),
        )

        assert isinstance(result, AsyncResult)

    async def test_send_unregistered_task(self, app):
        """미등록 태스크 전송 (원격 태스크 시뮬레이션)"""
        result = await app.send_task(
            "remote.task",
            args=("data",),
            kwargs={"option": True},
        )

        assert isinstance(result, AsyncResult)

        # 메시지가 큐에 추가됨
        length = await app.broker.queue_length("default")
        assert length >= 1
