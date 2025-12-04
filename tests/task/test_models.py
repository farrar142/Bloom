"""bloom.task.models 테스트"""

import pytest
from datetime import datetime, timedelta

from bloom.task.models import (
    Task,
    TaskMessage,
    TaskResult,
    TaskStatus,
    TaskPriority,
    TaskState,
    TaskError,
    TaskRetryError,
    create_task_message,
)


class TestTaskStatus:
    """TaskStatus 테스트"""

    def test_status_values(self):
        """상태 값 확인"""
        assert TaskStatus.PENDING.value == "PENDING"
        assert TaskStatus.SUCCESS.value == "SUCCESS"
        assert TaskStatus.FAILURE.value == "FAILURE"
        assert TaskStatus.RETRY.value == "RETRY"
        assert TaskStatus.REVOKED.value == "REVOKED"


class TestTaskPriority:
    """TaskPriority 테스트"""

    def test_priority_ordering(self):
        """우선순위 순서 확인"""
        assert TaskPriority.CRITICAL < TaskPriority.HIGH
        assert TaskPriority.HIGH < TaskPriority.NORMAL
        assert TaskPriority.NORMAL < TaskPriority.LOW
        assert TaskPriority.LOW < TaskPriority.BACKGROUND

    def test_priority_values(self):
        """우선순위 값 확인"""
        assert TaskPriority.CRITICAL == 0
        assert TaskPriority.NORMAL == 5
        assert TaskPriority.BACKGROUND == 9


class TestTaskState:
    """TaskState 테스트"""

    def test_from_status(self):
        """상태 그룹 변환"""
        assert TaskState.from_status(TaskStatus.PENDING) == TaskState.PENDING
        assert TaskState.from_status(TaskStatus.RECEIVED) == TaskState.ACTIVE
        assert TaskState.from_status(TaskStatus.STARTED) == TaskState.ACTIVE
        assert TaskState.from_status(TaskStatus.SUCCESS) == TaskState.COMPLETED
        assert TaskState.from_status(TaskStatus.FAILURE) == TaskState.FAILED
        assert TaskState.from_status(TaskStatus.RETRY) == TaskState.PENDING
        assert TaskState.from_status(TaskStatus.REVOKED) == TaskState.CANCELLED


class TestTask:
    """Task 모델 테스트"""

    def test_task_creation(self):
        """태스크 생성"""

        async def my_task():
            return "result"

        task = Task(name="test.task", func=my_task)
        assert task.name == "test.task"
        assert task.func is my_task
        assert task.queue == "default"
        assert task.retry == 0
        assert task.priority == TaskPriority.NORMAL

    def test_task_auto_name(self):
        """자동 이름 생성"""

        async def another_task():
            pass

        task = Task(name="", func=another_task)
        # name이 빈 문자열이면 __post_init__에서 자동 설정
        # (func가 있고 name이 없을 때만)

    def test_task_options(self):
        """태스크 옵션"""
        task = Task(
            name="test.task",
            queue="high",
            retry=3,
            retry_delay=5.0,
            timeout=60.0,
            priority=TaskPriority.HIGH,
            bind=True,
            ignore_result=True,
        )

        assert task.queue == "high"
        assert task.retry == 3
        assert task.retry_delay == 5.0
        assert task.timeout == 60.0
        assert task.priority == TaskPriority.HIGH
        assert task.bind is True
        assert task.ignore_result is True

    def test_get_retry_delay_no_backoff(self):
        """재시도 지연 계산 (백오프 없음)"""
        task = Task(
            name="test.task",
            retry_delay=2.0,
            retry_backoff=False,
        )

        assert task.get_retry_delay(0) == 2.0
        assert task.get_retry_delay(1) == 2.0
        assert task.get_retry_delay(5) == 2.0

    def test_get_retry_delay_with_backoff(self):
        """재시도 지연 계산 (지수 백오프)"""
        task = Task(
            name="test.task",
            retry_delay=1.0,
            retry_backoff=True,
            retry_backoff_max=100.0,
        )

        assert task.get_retry_delay(0) == 1.0  # 1 * 2^0 = 1
        assert task.get_retry_delay(1) == 2.0  # 1 * 2^1 = 2
        assert task.get_retry_delay(2) == 4.0  # 1 * 2^2 = 4
        assert task.get_retry_delay(3) == 8.0  # 1 * 2^3 = 8
        assert task.get_retry_delay(10) == 100.0  # max로 제한


class TestTaskMessage:
    """TaskMessage 테스트"""

    def test_message_creation(self):
        """메시지 생성"""
        msg = TaskMessage(
            task_name="test.task",
            args=("arg1", "arg2"),
            kwargs={"key": "value"},
        )

        assert msg.task_name == "test.task"
        assert msg.args == ("arg1", "arg2")
        assert msg.kwargs == {"key": "value"}
        assert msg.task_id is not None
        assert msg.queue == "default"
        assert msg.priority == TaskPriority.NORMAL

    def test_message_countdown(self):
        """countdown → eta 변환"""
        before = datetime.now()
        msg = TaskMessage(
            task_name="test.task",
            countdown=60,
        )
        after = datetime.now()

        assert msg.eta is not None
        assert (
            before + timedelta(seconds=60) <= msg.eta <= after + timedelta(seconds=60)
        )

    def test_message_eta(self):
        """eta 직접 지정"""
        eta = datetime.now() + timedelta(hours=1)
        msg = TaskMessage(
            task_name="test.task",
            eta=eta,
        )

        assert msg.eta == eta

    def test_is_delayed(self):
        """지연 실행 여부"""
        # 즉시 실행
        msg1 = TaskMessage(task_name="test.task")
        assert msg1.is_delayed() is False

        # 지연 실행 (미래)
        msg2 = TaskMessage(
            task_name="test.task",
            eta=datetime.now() + timedelta(hours=1),
        )
        assert msg2.is_delayed() is True

        # 지연 실행 (과거)
        msg3 = TaskMessage(
            task_name="test.task",
            eta=datetime.now() - timedelta(hours=1),
        )
        assert msg3.is_delayed() is False

    def test_is_expired(self):
        """만료 여부"""
        # 만료 시간 없음
        msg1 = TaskMessage(task_name="test.task")
        assert msg1.is_expired() is False

        # 미래 만료
        msg2 = TaskMessage(
            task_name="test.task",
            expires=datetime.now() + timedelta(hours=1),
        )
        assert msg2.is_expired() is False

        # 과거 만료
        msg3 = TaskMessage(
            task_name="test.task",
            expires=datetime.now() - timedelta(hours=1),
        )
        assert msg3.is_expired() is True

    def test_can_retry(self):
        """재시도 가능 여부"""
        msg = TaskMessage(
            task_name="test.task",
            retries=1,
            max_retries=3,
        )
        assert msg.can_retry() is True

        msg.retries = 3
        assert msg.can_retry() is False

    def test_serialization(self):
        """직렬화/역직렬화"""
        msg = TaskMessage(
            task_name="test.task",
            args=("arg1",),
            kwargs={"key": "value"},
            queue="high",
            priority=TaskPriority.HIGH,
        )

        # dict 변환
        data = msg.to_dict()
        restored = TaskMessage.from_dict(data)

        assert restored.task_name == msg.task_name
        assert restored.args == msg.args
        assert restored.kwargs == msg.kwargs
        assert restored.queue == msg.queue
        assert restored.priority == msg.priority

    def test_json_serialization(self):
        """JSON 직렬화"""
        msg = TaskMessage(
            task_name="test.task",
            args=(1, 2, 3),
        )

        json_str = msg.to_json()
        restored = TaskMessage.from_json(json_str)

        assert restored.task_name == msg.task_name
        assert restored.task_id == msg.task_id


class TestTaskResult:
    """TaskResult 테스트"""

    def test_result_creation(self):
        """결과 생성"""
        result = TaskResult(
            task_id="test-123",
            status=TaskStatus.SUCCESS,
            result={"data": "value"},
        )

        assert result.task_id == "test-123"
        assert result.status == TaskStatus.SUCCESS
        assert result.result == {"data": "value"}

    def test_is_ready(self):
        """완료 여부"""
        # 대기 중
        result1 = TaskResult(task_id="1", status=TaskStatus.PENDING)
        assert result1.is_ready() is False

        # 실행 중
        result2 = TaskResult(task_id="2", status=TaskStatus.STARTED)
        assert result2.is_ready() is False

        # 성공
        result3 = TaskResult(task_id="3", status=TaskStatus.SUCCESS)
        assert result3.is_ready() is True

        # 실패
        result4 = TaskResult(task_id="4", status=TaskStatus.FAILURE)
        assert result4.is_ready() is True

        # 취소
        result5 = TaskResult(task_id="5", status=TaskStatus.REVOKED)
        assert result5.is_ready() is True

    def test_is_successful(self):
        """성공 여부"""
        success = TaskResult(task_id="1", status=TaskStatus.SUCCESS)
        failure = TaskResult(task_id="2", status=TaskStatus.FAILURE)

        assert success.is_successful() is True
        assert failure.is_successful() is False

    def test_is_failed(self):
        """실패 여부"""
        success = TaskResult(task_id="1", status=TaskStatus.SUCCESS)
        failure = TaskResult(task_id="2", status=TaskStatus.FAILURE)
        rejected = TaskResult(task_id="3", status=TaskStatus.REJECTED)

        assert success.is_failed() is False
        assert failure.is_failed() is True
        assert rejected.is_failed() is True

    def test_get_success(self):
        """성공 결과 가져오기"""
        result = TaskResult(
            task_id="test-123",
            status=TaskStatus.SUCCESS,
            result={"key": "value"},
        )

        assert result.get() == {"key": "value"}

    def test_get_failure(self):
        """실패 결과 가져오기 → 예외"""
        result = TaskResult(
            task_id="test-123",
            status=TaskStatus.FAILURE,
            error="Something went wrong",
        )

        with pytest.raises(TaskError) as exc_info:
            result.get()

        assert "test-123" in str(exc_info.value)
        assert "Something went wrong" in str(exc_info.value)

    def test_get_not_ready(self):
        """미완료 결과 가져오기 → 예외"""
        result = TaskResult(task_id="test-123", status=TaskStatus.PENDING)

        with pytest.raises(RuntimeError) as exc_info:
            result.get()

        assert "not ready" in str(exc_info.value)

    def test_runtime(self):
        """실행 시간 계산"""
        start = datetime.now()
        end = start + timedelta(seconds=5)

        result = TaskResult(
            task_id="test-123",
            status=TaskStatus.SUCCESS,
            started_at=start,
            completed_at=end,
        )

        assert result.runtime == pytest.approx(5.0, abs=0.1)

    def test_runtime_not_completed(self):
        """미완료 시 실행 시간"""
        result = TaskResult(
            task_id="test-123",
            status=TaskStatus.STARTED,
            started_at=datetime.now(),
        )

        assert result.runtime is None

    def test_serialization(self):
        """직렬화"""
        result = TaskResult(
            task_id="test-123",
            status=TaskStatus.SUCCESS,
            result={"data": "value"},
        )

        data = result.to_dict()
        restored = TaskResult.from_dict(data)

        assert restored.task_id == result.task_id
        assert restored.status == result.status
        assert restored.result == result.result


class TestCreateTaskMessage:
    """create_task_message 헬퍼 테스트"""

    def test_basic_creation(self):
        """기본 메시지 생성"""
        msg = create_task_message(
            "test.task",
            args=("arg1",),
            kwargs={"key": "value"},
        )

        assert msg.task_name == "test.task"
        assert msg.args == ("arg1",)
        assert msg.kwargs == {"key": "value"}

    def test_with_options(self):
        """옵션과 함께 생성"""
        msg = create_task_message(
            "test.task",
            task_id="custom-id",
            queue="high",
            priority=TaskPriority.HIGH,
            countdown=60,
            max_retries=3,
        )

        assert msg.task_id == "custom-id"
        assert msg.queue == "high"
        assert msg.priority == TaskPriority.HIGH
        assert msg.max_retries == 3
        assert msg.eta is not None


class TestTaskErrors:
    """태스크 에러 테스트"""

    def test_task_error(self):
        """기본 태스크 에러"""
        error = TaskError(
            "Task failed",
            task_id="test-123",
            error="details",
        )

        assert str(error) == "Task failed"
        assert error.task_id == "test-123"
        assert error.error == "details"

    def test_task_retry_error(self):
        """재시도 요청 에러"""
        error = TaskRetryError(
            countdown=60,
            max_retries=5,
        )

        assert error.countdown == 60
        assert error.max_retries == 5

    def test_task_retry_error_with_eta(self):
        """ETA로 재시도"""
        eta = datetime.now() + timedelta(hours=1)
        error = TaskRetryError(eta=eta)

        assert error.eta == eta
