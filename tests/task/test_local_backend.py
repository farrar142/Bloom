"""bloom.task.backends.local 테스트"""

import pytest
import asyncio
from datetime import datetime, timedelta

from bloom.task.backends.local import LocalBroker, LocalBackend
from bloom.task.models import (
    TaskMessage,
    TaskResult,
    TaskStatus,
    TaskPriority,
)


class TestLocalBroker:
    """LocalBroker 테스트"""

    @pytest.fixture
    async def broker(self):
        """브로커 fixture"""
        broker = LocalBroker()
        await broker.connect()
        yield broker
        await broker.disconnect()

    async def test_connect_disconnect(self):
        """연결/해제"""
        broker = LocalBroker()
        assert broker._connected is False

        await broker.connect()
        assert broker._connected is True

        await broker.disconnect()
        assert broker._connected is False

    async def test_declare_queue(self, broker):
        """큐 선언"""
        await broker.declare_queue("test_queue")
        assert "test_queue" in broker._queues

    async def test_delete_queue(self, broker):
        """큐 삭제"""
        await broker.declare_queue("test_queue")
        await broker.delete_queue("test_queue")
        assert "test_queue" not in broker._queues

    async def test_publish_and_queue_length(self, broker):
        """메시지 발행 및 큐 길이"""
        await broker.declare_queue("test_queue")

        msg = TaskMessage(task_name="test.task", queue="test_queue")
        await broker.publish(msg)

        length = await broker.queue_length("test_queue")
        assert length == 1

    async def test_publish_multiple(self, broker):
        """여러 메시지 발행"""
        await broker.declare_queue("test_queue")

        for i in range(5):
            msg = TaskMessage(task_name=f"test.task.{i}", queue="test_queue")
            await broker.publish(msg)

        length = await broker.queue_length("test_queue")
        assert length == 5

    async def test_purge_queue(self, broker):
        """큐 비우기"""
        await broker.declare_queue("test_queue")

        for i in range(3):
            msg = TaskMessage(task_name=f"test.task.{i}", queue="test_queue")
            await broker.publish(msg)

        count = await broker.purge_queue("test_queue")
        assert count == 3

        length = await broker.queue_length("test_queue")
        assert length == 0

    async def test_consume_single_message(self, broker):
        """단일 메시지 소비"""
        await broker.declare_queue("test_queue")

        msg = TaskMessage(task_name="test.task", queue="test_queue")
        await broker.publish(msg)

        consumed = []
        consumer = broker.consume(["test_queue"])
        try:
            async for message, delivery_tag in consumer:
                consumed.append((message, delivery_tag))
                await broker.ack(delivery_tag)
                break  # 하나만 소비
        finally:
            await consumer.aclose()  # 명시적으로 generator 닫기

        assert len(consumed) == 1
        assert consumed[0][0].task_name == "test.task"

    async def test_consume_priority_order(self, broker):
        """우선순위 순서로 소비"""
        await broker.declare_queue("test_queue")

        # 낮은 우선순위 먼저 발행
        low = TaskMessage(
            task_name="low",
            queue="test_queue",
            priority=TaskPriority.LOW,
        )
        await broker.publish(low)

        # 높은 우선순위 나중에 발행
        high = TaskMessage(
            task_name="high",
            queue="test_queue",
            priority=TaskPriority.HIGH,
        )
        await broker.publish(high)

        # 높은 우선순위가 먼저 나와야 함
        consumed = []
        count = 0
        consumer = broker.consume(["test_queue"])
        try:
            async for message, delivery_tag in consumer:
                consumed.append(message.task_name)
                await broker.ack(delivery_tag)
                count += 1
                if count >= 2:
                    break
        finally:
            await consumer.aclose()

        assert consumed == ["high", "low"]

    async def test_nack_requeue(self, broker):
        """메시지 거부 후 재큐잉"""
        await broker.declare_queue("test_queue")

        msg = TaskMessage(task_name="test.task", queue="test_queue")
        await broker.publish(msg)

        # 첫 번째 소비 - nack with requeue
        consumer = broker.consume(["test_queue"])
        try:
            async for message, delivery_tag in consumer:
                await broker.nack(delivery_tag, requeue=True)
                break
        finally:
            await consumer.aclose()

        # 큐에 다시 있어야 함
        length = await broker.queue_length("test_queue")
        assert length == 1

    async def test_nack_no_requeue(self, broker):
        """메시지 거부 (재큐잉 없음)"""
        await broker.declare_queue("test_queue")

        msg = TaskMessage(task_name="test.task", queue="test_queue")
        await broker.publish(msg)

        consumer = broker.consume(["test_queue"])
        try:
            async for message, delivery_tag in consumer:
                await broker.nack(delivery_tag, requeue=False)
                break
        finally:
            await consumer.aclose()

        # 큐가 비어있어야 함
        length = await broker.queue_length("test_queue")
        assert length == 0

    async def test_context_manager(self):
        """컨텍스트 매니저"""
        async with LocalBroker() as broker:
            assert broker._connected is True
            await broker.declare_queue("test_queue")


class TestLocalBrokerDelayed:
    """LocalBroker 지연 실행 테스트"""

    @pytest.fixture
    async def broker(self):
        """브로커 fixture"""
        broker = LocalBroker()
        await broker.connect()
        yield broker
        await broker.disconnect()

    async def test_delayed_message(self, broker):
        """지연 메시지 (eta가 미래)"""
        await broker.declare_queue("test_queue")

        # 1초 후 실행 예정
        eta = datetime.now() + timedelta(seconds=0.2)
        msg = TaskMessage(
            task_name="delayed.task",
            queue="test_queue",
            eta=eta,
        )
        await broker.publish(msg)

        # 즉시 소비 시도 - 아직 없어야 함
        length = await broker.queue_length("test_queue")
        assert length == 1

        # 약간 대기 후 소비
        await asyncio.sleep(0.3)

        consumer = broker.consume(["test_queue"])
        try:
            async for message, delivery_tag in consumer:
                assert message.task_name == "delayed.task"
                await broker.ack(delivery_tag)
                break
        finally:
            await consumer.aclose()

    async def test_expired_message(self, broker):
        """만료된 메시지 스킵"""
        await broker.declare_queue("test_queue")

        # 이미 만료됨
        msg = TaskMessage(
            task_name="expired.task",
            queue="test_queue",
            expires=datetime.now() - timedelta(hours=1),
        )
        await broker.publish(msg)

        # 유효한 메시지
        valid_msg = TaskMessage(
            task_name="valid.task",
            queue="test_queue",
        )
        await broker.publish(valid_msg)

        # 소비 - 만료된 건 스킵되고 유효한 것만 나와야 함
        consumer = broker.consume(["test_queue"])
        try:
            async for message, delivery_tag in consumer:
                assert message.task_name == "valid.task"
                await broker.ack(delivery_tag)
                break
        finally:
            await consumer.aclose()


class TestLocalBackend:
    """LocalBackend 테스트"""

    @pytest.fixture
    async def backend(self):
        """백엔드 fixture"""
        backend = LocalBackend()
        await backend.connect()
        yield backend
        await backend.disconnect()

    async def test_connect_disconnect(self):
        """연결/해제"""
        backend = LocalBackend()
        assert backend._connected is False

        await backend.connect()
        assert backend._connected is True

        await backend.disconnect()
        assert backend._connected is False

    async def test_store_and_get_result(self, backend):
        """결과 저장 및 조회"""
        result = TaskResult(
            task_id="test-123",
            status=TaskStatus.SUCCESS,
            result={"data": "value"},
        )

        await backend.store_result("test-123", result)
        retrieved = await backend.get_result("test-123")

        assert retrieved is not None
        assert retrieved.task_id == "test-123"
        assert retrieved.status == TaskStatus.SUCCESS
        assert retrieved.result == {"data": "value"}

    async def test_get_nonexistent_result(self, backend):
        """존재하지 않는 결과 조회"""
        result = await backend.get_result("nonexistent")
        assert result is None

    async def test_delete_result(self, backend):
        """결과 삭제"""
        result = TaskResult(task_id="test-123", status=TaskStatus.SUCCESS)
        await backend.store_result("test-123", result)

        deleted = await backend.delete_result("test-123")
        assert deleted is True

        retrieved = await backend.get_result("test-123")
        assert retrieved is None

    async def test_delete_nonexistent_result(self, backend):
        """존재하지 않는 결과 삭제"""
        deleted = await backend.delete_result("nonexistent")
        assert deleted is False

    async def test_update_status(self, backend):
        """상태 업데이트"""
        result = TaskResult(task_id="test-123", status=TaskStatus.PENDING)
        await backend.store_result("test-123", result)

        await backend.update_status("test-123", TaskStatus.STARTED)
        retrieved = await backend.get_result("test-123")
        assert retrieved is not None
        assert retrieved.status == TaskStatus.STARTED

    async def test_update_status_with_result(self, backend):
        """결과와 함께 상태 업데이트"""
        result = TaskResult(task_id="test-123", status=TaskStatus.STARTED)
        await backend.store_result("test-123", result)

        await backend.update_status(
            "test-123",
            TaskStatus.SUCCESS,
            result={"completed": True},
        )

        retrieved = await backend.get_result("test-123")
        assert retrieved is not None
        assert retrieved.status == TaskStatus.SUCCESS
        assert retrieved.result == {"completed": True}

    async def test_update_status_new_result(self, backend):
        """존재하지 않는 태스크 상태 업데이트"""
        await backend.update_status("new-task", TaskStatus.SUCCESS, result="done")

        retrieved = await backend.get_result("new-task")
        assert retrieved is not None
        assert retrieved.status == TaskStatus.SUCCESS
        assert retrieved.result == "done"

    async def test_exists(self, backend):
        """존재 여부 확인"""
        assert await backend.exists("test-123") is False

        result = TaskResult(task_id="test-123", status=TaskStatus.PENDING)
        await backend.store_result("test-123", result)

        assert await backend.exists("test-123") is True

    async def test_wait_for_result(self, backend):
        """결과 대기"""

        async def store_later():
            await asyncio.sleep(0.1)
            result = TaskResult(
                task_id="test-123",
                status=TaskStatus.SUCCESS,
                result="done",
            )
            await backend.store_result("test-123", result)

        # 백그라운드에서 저장
        asyncio.create_task(store_later())

        # 대기
        result = await backend.wait_for_result("test-123", timeout=1.0)
        assert result is not None
        assert result.status == TaskStatus.SUCCESS
        assert result.result == "done"

    async def test_wait_for_result_timeout(self, backend):
        """결과 대기 타임아웃"""
        result = await backend.wait_for_result(
            "nonexistent",
            timeout=0.1,
        )
        assert result is None

    async def test_context_manager(self):
        """컨텍스트 매니저"""
        async with LocalBackend() as backend:
            assert backend._connected is True

            result = TaskResult(task_id="test-123", status=TaskStatus.SUCCESS)
            await backend.store_result("test-123", result)
