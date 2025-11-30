"""분산 태스크 백엔드 테스트

InMemoryBroker와 RedisBroker 기반의 DistributedTaskBackend 테스트입니다.
"""

import asyncio
from datetime import datetime

import pytest

from bloom import Application, Component
from bloom.task import (
    Task,
    TaskMessage,
    TaskState,
    TaskRegistry,
    DistributedTaskBackend,
    DistributedTaskResult,
)
from bloom.task.broker import InMemoryBroker, RedisBroker
from bloom.task.message import TaskResult as TaskResultMessage


# =============================================================================
# TaskMessage 테스트
# =============================================================================


class TestTaskMessage:
    """TaskMessage 직렬화/역직렬화 테스트"""

    def test_create_message(self):
        """메시지 생성 테스트"""
        message = TaskMessage(
            task_name="EmailService.send_email",
            args=("user@example.com", "Hello"),
            kwargs={"priority": "high"},
        )

        assert message.task_name == "EmailService.send_email"
        assert message.args == ("user@example.com", "Hello")
        assert message.kwargs == {"priority": "high"}
        assert message.task_id is not None
        assert message.retries == 0

    def test_serialize_deserialize(self):
        """JSON 직렬화/역직렬화 테스트"""
        original = TaskMessage(
            task_name="TestTask.run",
            args=(1, 2, 3),
            kwargs={"key": "value"},
            max_retries=3,
            retry_delay=2.0,
        )

        json_str = original.to_json()
        restored = TaskMessage.from_json(json_str)

        assert restored.task_id == original.task_id
        assert restored.task_name == original.task_name
        assert restored.args == original.args
        assert restored.kwargs == original.kwargs
        assert restored.max_retries == original.max_retries
        assert restored.retry_delay == original.retry_delay

    def test_with_eta(self):
        """예약 실행 시간 테스트"""
        eta = datetime(2025, 12, 1, 12, 0, 0)
        message = TaskMessage(
            task_name="ScheduledTask.run",
            eta=eta,
        )

        json_str = message.to_json()
        restored = TaskMessage.from_json(json_str)

        assert restored.eta == eta


class TestTaskResultMessage:
    """TaskResult 메시지 테스트"""

    def test_success_result(self):
        """성공 결과 테스트"""
        result = TaskResultMessage(
            task_id="test-123",
            state=TaskState.SUCCESS,
            result={"data": "value"},
        )

        assert result.is_ready
        assert result.is_successful
        assert not result.is_failed

    def test_failure_result(self):
        """실패 결과 테스트"""
        result = TaskResultMessage(
            task_id="test-456",
            state=TaskState.FAILURE,
            error="Something went wrong",
            traceback="Traceback...",
        )

        assert result.is_ready
        assert not result.is_successful
        assert result.is_failed

    def test_serialize_deserialize(self):
        """직렬화/역직렬화 테스트"""
        original = TaskResultMessage(
            task_id="test-789",
            state=TaskState.SUCCESS,
            result=42,
            started_at=datetime.now(),
            completed_at=datetime.now(),
        )

        json_str = original.to_json()
        restored = TaskResultMessage.from_json(json_str)

        assert restored.task_id == original.task_id
        assert restored.state == original.state
        assert restored.result == original.result


# =============================================================================
# InMemoryBroker 테스트
# =============================================================================


class TestInMemoryBroker:
    """InMemoryBroker 테스트"""

    @pytest.fixture
    def broker(self):
        return InMemoryBroker()

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, broker):
        """연결/해제 테스트"""
        assert not broker.is_connected

        await broker.connect()
        assert broker.is_connected

        await broker.disconnect()
        assert not broker.is_connected

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, broker):
        """큐 추가/제거 테스트"""
        await broker.connect()

        message = TaskMessage(task_name="TestTask.run", args=(1, 2))

        await broker.enqueue(message)
        assert await broker.queue_length() == 1

        dequeued = await broker.dequeue()
        assert dequeued is not None
        assert dequeued.task_id == message.task_id
        assert await broker.queue_length() == 0

    @pytest.mark.asyncio
    async def test_dequeue_empty(self, broker):
        """빈 큐에서 dequeue 테스트"""
        await broker.connect()

        result = await broker.dequeue()
        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_with_timeout(self, broker):
        """타임아웃 dequeue 테스트"""
        await broker.connect()

        # 빈 큐에서 타임아웃
        start = datetime.now()
        result = await broker.dequeue(timeout=0.1)
        elapsed = (datetime.now() - start).total_seconds()

        assert result is None
        assert elapsed >= 0.1

    @pytest.mark.asyncio
    async def test_multiple_queues(self, broker):
        """다중 큐 테스트"""
        await broker.connect()

        message1 = TaskMessage(task_name="Task1.run")
        message2 = TaskMessage(task_name="Task2.run")

        await broker.enqueue(message1, queue="queue1")
        await broker.enqueue(message2, queue="queue2")

        assert await broker.queue_length("queue1") == 1
        assert await broker.queue_length("queue2") == 1

        result1 = await broker.dequeue(queue="queue1")
        result2 = await broker.dequeue(queue="queue2")

        assert result1.task_name == "Task1.run"
        assert result2.task_name == "Task2.run"

    @pytest.mark.asyncio
    async def test_result_storage(self, broker):
        """결과 저장/조회 테스트"""
        await broker.connect()

        result = TaskResultMessage(
            task_id="result-test",
            state=TaskState.SUCCESS,
            result="done",
        )

        await broker.set_result(result)
        retrieved = await broker.get_result("result-test")

        assert retrieved is not None
        assert retrieved.task_id == "result-test"
        assert retrieved.result == "done"

    @pytest.mark.asyncio
    async def test_result_delete(self, broker):
        """결과 삭제 테스트"""
        await broker.connect()

        result = TaskResultMessage(task_id="delete-test", state=TaskState.SUCCESS)
        await broker.set_result(result)

        assert await broker.delete_result("delete-test") is True
        assert await broker.get_result("delete-test") is None
        assert await broker.delete_result("delete-test") is False


# =============================================================================
# TaskRegistry 테스트
# =============================================================================


class TestTaskRegistry:
    """TaskRegistry 테스트"""

    def test_register_and_get(self):
        """등록 및 조회 테스트"""
        registry = TaskRegistry()

        def handler(self, x: int) -> int:
            return x * 2

        class TestComponent:
            pass

        registry.register(
            name="TestComponent.handler",
            handler=handler,
            component_type=TestComponent,
        )

        assert registry.has("TestComponent.handler")
        assert not registry.has("NonExistent.handler")

        info = registry.get("TestComponent.handler")
        assert info is not None
        assert info.name == "TestComponent.handler"
        assert info.handler is handler

    def test_duplicate_name_raises_error(self):
        """같은 이름으로 등록 시 에러 발생"""
        registry = TaskRegistry()

        class ServiceA:
            def send(self):
                pass

        class ServiceB:
            def send(self):
                pass

        # 첫 번째 등록: 성공
        registry.register(
            name="send",
            handler=ServiceA.send,
            component_type=ServiceA,
        )

        # 두 번째 등록: 같은 이름으로 충돌 → ValueError
        with pytest.raises(ValueError, match="Task name conflict"):
            registry.register(
                name="send",
                handler=ServiceB.send,
                component_type=ServiceB,
            )

    def test_scan_from_container_manager(self):
        """ContainerManager에서 스캔 테스트"""

        @Component
        class TaskService:
            @Task
            def process(self, data: str) -> str:
                return f"processed: {data}"

            @Task(name="custom-task")
            def custom(self) -> str:
                return "custom"

        app = Application("test-registry").scan(TaskService).ready()

        registry = TaskRegistry()
        registry.scan(app.manager)

        assert len(registry) == 2
        assert registry.has(
            "TaskService.process"
        )  # 커스텀 이름 없음 → ClassName.method_name
        assert registry.has("custom-task")  # 커스텀 이름 지정 → 해당 이름으로 등록

    def test_execute_task(self):
        """태스크 실행 테스트"""

        class Calculator:
            def add(self, a: int, b: int) -> int:
                return a + b

        registry = TaskRegistry()
        instance = Calculator()

        registry.register(
            name="Calculator.add",
            handler=Calculator.add,
            component_type=Calculator,
            instance=instance,
        )

        info = registry.get("Calculator.add")
        result = info.execute(3, 5)

        assert result == 8


# =============================================================================
# DistributedTaskBackend 테스트 (InMemoryBroker)
# =============================================================================


class TestDistributedTaskBackendWithMemory:
    """InMemoryBroker 기반 DistributedTaskBackend 테스트"""

    @pytest.fixture
    def backend(self):
        broker = InMemoryBroker()
        return DistributedTaskBackend(broker=broker)

    @pytest.mark.asyncio
    async def test_start_and_shutdown(self, backend):
        """시작/종료 테스트"""
        await backend.start()
        assert backend.broker.is_connected

        await backend.shutdown()
        assert not backend.broker.is_connected

    @pytest.mark.asyncio
    async def test_submit_and_execute(self, backend):
        """태스크 제출 및 실행 테스트"""

        @Component
        class MathService:
            @Task
            def multiply(self, a: int, b: int) -> int:
                return a * b

        app = Application("test-submit").scan(MathService).ready()

        await backend.start()

        # 워커 시작 (백그라운드)
        worker_task = asyncio.create_task(backend.start_worker(app.manager))

        # 잠시 대기 (워커가 시작될 때까지)
        await asyncio.sleep(0.1)

        # 태스크 제출
        service = app.manager.get_instance(MathService)
        # 직접 메시지 생성하여 제출
        message = TaskMessage(
            task_name="MathService.multiply",
            args=(4, 5),
        )
        await backend._enqueue_message(message)

        # 결과 대기
        result = DistributedTaskResult(
            task_id=message.task_id,
            broker=backend.broker,
        )
        value = await result.get(timeout=5)

        assert value == 20

        # 정리
        await backend.shutdown()
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_task_failure_and_retry(self, backend):
        """태스크 실패 및 재시도 테스트"""
        attempt_count = 0

        @Component
        class FailingService:
            @Task(max_retries=2)
            def fail_twice(self) -> str:
                nonlocal attempt_count
                attempt_count += 1
                if attempt_count < 3:
                    raise ValueError(f"Attempt {attempt_count} failed")
                return "success"

        app = Application("test-retry").scan(FailingService).ready()

        await backend.start()
        worker_task = asyncio.create_task(backend.start_worker(app.manager))
        await asyncio.sleep(0.1)

        # 태스크 제출
        message = TaskMessage(
            task_name="FailingService.fail_twice",
            max_retries=2,
            retry_delay=0.1,
        )
        await backend._enqueue_message(message)

        # 결과 대기
        result = DistributedTaskResult(
            task_id=message.task_id,
            broker=backend.broker,
        )
        value = await result.get(timeout=5)

        assert value == "success"
        assert attempt_count == 3

        await backend.shutdown()
        worker_task.cancel()


# =============================================================================
# RedisBroker 테스트 (Redis 연결 필요)
# =============================================================================

REDIS_URL = "redis://192.168.0.17:6379/0"


def redis_available() -> bool:
    """Redis 연결 가능 여부 확인"""
    try:
        import redis

        r = redis.from_url(REDIS_URL, socket_timeout=1)
        r.ping()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not redis_available(), reason="Redis not available")
class TestRedisBroker:
    """RedisBroker 테스트 (실제 Redis 필요)"""

    @pytest.fixture
    async def broker(self):
        broker = RedisBroker(REDIS_URL)
        await broker.connect()
        yield broker
        await broker.disconnect()

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, broker):
        """연결 상태 테스트"""
        assert broker.is_connected

    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self, broker):
        """큐 추가/제거 테스트"""
        message = TaskMessage(task_name="RedisTest.run", args=(1, 2, 3))

        await broker.enqueue(message, queue="test-queue")
        length = await broker.queue_length("test-queue")
        assert length >= 1

        dequeued = await broker.dequeue(queue="test-queue")
        assert dequeued is not None
        assert dequeued.task_id == message.task_id

    @pytest.mark.asyncio
    async def test_result_storage(self, broker):
        """결과 저장/조회 테스트"""
        result = TaskResultMessage(
            task_id="redis-result-test",
            state=TaskState.SUCCESS,
            result={"key": "value"},
        )

        await broker.set_result(result)
        retrieved = await broker.get_result("redis-result-test")

        assert retrieved is not None
        assert retrieved.state == TaskState.SUCCESS
        assert retrieved.result == {"key": "value"}

        # 정리
        await broker.delete_result("redis-result-test")


@pytest.mark.skipif(not redis_available(), reason="Redis not available")
class TestDistributedTaskBackendWithRedis:
    """Redis 기반 DistributedTaskBackend 테스트"""

    @pytest.fixture
    async def backend(self):
        broker = RedisBroker(REDIS_URL)
        backend = DistributedTaskBackend(broker=broker, queue="test-distributed")
        await backend.start()
        yield backend
        await backend.shutdown()

    @pytest.mark.asyncio
    async def test_distributed_task_execution(self, backend):
        """분산 태스크 실행 테스트"""

        @Component
        class DistributedService:
            @Task
            def compute(self, x: int, y: int) -> int:
                return x + y

        app = Application("test-distributed").scan(DistributedService).ready()

        # 워커 시작
        worker_task = asyncio.create_task(backend.start_worker(app.manager))
        await asyncio.sleep(0.2)

        # 태스크 제출
        message = TaskMessage(
            task_name="DistributedService.compute",
            args=(10, 20),
        )
        await backend._enqueue_message(message)

        # 결과 대기
        result = DistributedTaskResult(
            task_id=message.task_id,
            broker=backend.broker,
        )
        value = await result.get(timeout=5)

        assert value == 30

        # 정리
        backend._running = False
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
