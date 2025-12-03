"""bloom.core.task.models - 태스크 모델 정의

태스크 메시지, 결과, 상태 등의 데이터 모델을 정의합니다.
"""

from __future__ import annotations

import uuid
import json
import pickle
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum, auto, IntEnum
from typing import Any, Generic, TypeVar, Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


# =============================================================================
# Type Variables
# =============================================================================

T = TypeVar("T")
TaskReturn = TypeVar("TaskReturn")


# =============================================================================
# Enums
# =============================================================================


class TaskStatus(str, Enum):
    """태스크 실행 상태"""

    PENDING = "PENDING"  # 대기 중
    RECEIVED = "RECEIVED"  # 워커가 수신함
    STARTED = "STARTED"  # 실행 시작
    SUCCESS = "SUCCESS"  # 성공적으로 완료
    FAILURE = "FAILURE"  # 실패
    RETRY = "RETRY"  # 재시도 예정
    REVOKED = "REVOKED"  # 취소됨
    REJECTED = "REJECTED"  # 거부됨 (재시도 없음)


class TaskPriority(IntEnum):
    """태스크 우선순위"""

    CRITICAL = 0  # 가장 높은 우선순위
    HIGH = 3
    NORMAL = 5
    LOW = 7
    BACKGROUND = 9  # 가장 낮은 우선순위


class TaskState(str, Enum):
    """태스크 상태 그룹"""

    PENDING = "PENDING"  # 대기 상태
    ACTIVE = "ACTIVE"  # 활성 상태 (RECEIVED, STARTED)
    COMPLETED = "COMPLETED"  # 완료 상태 (SUCCESS)
    FAILED = "FAILED"  # 실패 상태 (FAILURE, REJECTED)
    CANCELLED = "CANCELLED"  # 취소 상태 (REVOKED)

    @classmethod
    def from_status(cls, status: TaskStatus) -> "TaskState":
        """TaskStatus를 TaskState로 변환"""
        mapping = {
            TaskStatus.PENDING: cls.PENDING,
            TaskStatus.RECEIVED: cls.ACTIVE,
            TaskStatus.STARTED: cls.ACTIVE,
            TaskStatus.SUCCESS: cls.COMPLETED,
            TaskStatus.FAILURE: cls.FAILED,
            TaskStatus.RETRY: cls.PENDING,
            TaskStatus.REVOKED: cls.CANCELLED,
            TaskStatus.REJECTED: cls.FAILED,
        }
        return mapping.get(status, cls.PENDING)


# =============================================================================
# Task Definition
# =============================================================================


@dataclass
class Task:
    """태스크 정의

    태스크의 메타데이터와 실행 옵션을 정의합니다.

    Attributes:
        name: 태스크 고유 이름 (예: "myapp.tasks.send_email")
        func: 실행할 함수
        queue: 사용할 큐 이름 (기본: "default")
        retry: 최대 재시도 횟수
        retry_delay: 재시도 간격 (초)
        retry_backoff: 지수 백오프 사용 여부
        timeout: 실행 제한 시간 (초)
        priority: 우선순위
        bind: 첫 번째 인자로 self(태스크 인스턴스) 바인딩
        autoretry_for: 자동 재시도할 예외 타입들
        ignore_result: 결과 저장 안함
        track_started: STARTED 상태 추적
        acks_late: 태스크 완료 후 ACK 전송
        rate_limit: 초당 최대 실행 횟수 (예: "10/s", "100/m")
    """

    name: str
    func: Callable[..., Any] | None = None
    queue: str = "default"
    retry: int = 0
    retry_delay: float = 1.0
    retry_backoff: bool = True
    retry_backoff_max: float = 600.0
    timeout: float | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    bind: bool = False
    autoretry_for: tuple[type[Exception], ...] = field(default_factory=tuple)
    ignore_result: bool = False
    track_started: bool = True
    acks_late: bool = False
    rate_limit: str | None = None

    def __post_init__(self):
        if self.func and not self.name:
            # 자동으로 이름 생성
            module = getattr(self.func, "__module__", "__main__")
            qualname = getattr(self.func, "__qualname__", self.func.__name__)
            self.name = f"{module}.{qualname}"

    def get_retry_delay(self, retry_count: int) -> float:
        """현재 재시도 횟수에 따른 지연 시간 계산"""
        if not self.retry_backoff:
            return self.retry_delay

        # 지수 백오프: delay * 2^retry_count
        delay = self.retry_delay * (2**retry_count)
        return min(delay, self.retry_backoff_max)


# =============================================================================
# Task Message
# =============================================================================


@dataclass
class TaskMessage:
    """태스크 메시지

    브로커를 통해 전달되는 태스크 실행 요청 메시지입니다.

    Attributes:
        task_id: 고유 태스크 ID (UUID)
        task_name: 태스크 이름
        args: 위치 인자
        kwargs: 키워드 인자
        queue: 대상 큐
        priority: 우선순위
        eta: 실행 예정 시간 (None이면 즉시)
        expires: 만료 시간 (이후로는 실행 안함)
        retries: 현재까지 재시도 횟수
        max_retries: 최대 재시도 횟수
        correlation_id: 관련 요청 ID (추적용)
        reply_to: 결과 전송 큐
        created_at: 메시지 생성 시간
        root_id: 체인의 루트 태스크 ID
        parent_id: 부모 태스크 ID (체인에서)
        group_id: 그룹 ID (그룹 실행 시)
        chord_callback: chord 콜백 태스크 정보
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_name: str = ""
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    queue: str = "default"
    priority: TaskPriority = TaskPriority.NORMAL

    # Scheduling
    eta: datetime | None = None
    countdown: float | None = None  # eta 대신 사용 (초 단위)
    expires: datetime | None = None

    # Retry
    retries: int = 0
    max_retries: int = 0

    # Correlation
    correlation_id: str | None = None
    reply_to: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)

    # Chain/Chord support
    root_id: str | None = None
    parent_id: str | None = None
    group_id: str | None = None
    chord_callback: dict[str, Any] | None = None

    def __post_init__(self):
        # countdown을 eta로 변환
        if self.countdown is not None and self.eta is None:
            self.eta = datetime.now() + timedelta(seconds=self.countdown)

        # root_id 기본값
        if self.root_id is None:
            self.root_id = self.task_id

    def is_delayed(self) -> bool:
        """지연 실행 여부"""
        if self.eta is None:
            return False
        return datetime.now() < self.eta

    def is_expired(self) -> bool:
        """만료 여부"""
        if self.expires is None:
            return False
        return datetime.now() > self.expires

    def can_retry(self) -> bool:
        """재시도 가능 여부"""
        return self.retries < self.max_retries

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (직렬화용)"""
        data = asdict(self)
        # datetime을 ISO 문자열로 변환
        for key in ("eta", "expires", "created_at"):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskMessage":
        """딕셔너리에서 생성"""
        # ISO 문자열을 datetime으로 변환
        for key in ("eta", "expires", "created_at"):
            if data.get(key) is not None and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        # priority를 enum으로 변환
        if isinstance(data.get("priority"), int):
            data["priority"] = TaskPriority(data["priority"])
        return cls(**data)

    def to_json(self) -> str:
        """JSON 문자열로 직렬화"""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "TaskMessage":
        """JSON 문자열에서 역직렬화"""
        return cls.from_dict(json.loads(json_str))


# =============================================================================
# Task Result
# =============================================================================


@dataclass
class TaskResult(Generic[T]):
    """태스크 실행 결과

    태스크 실행의 결과를 저장합니다.

    Attributes:
        task_id: 태스크 ID
        status: 실행 상태
        result: 반환값 (성공 시)
        error: 예외 정보 (실패 시)
        traceback: 스택 트레이스 (실패 시)
        started_at: 실행 시작 시간
        completed_at: 완료 시간
        retries: 재시도 횟수
        worker_id: 실행한 워커 ID
        runtime: 실행 시간 (초)
    """

    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    result: T | None = None
    error: str | None = None
    error_type: str | None = None
    traceback: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Metadata
    retries: int = 0
    worker_id: str | None = None

    @property
    def runtime(self) -> float | None:
        """실행 시간 (초)"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def state(self) -> TaskState:
        """현재 상태 그룹"""
        return TaskState.from_status(self.status)

    def is_ready(self) -> bool:
        """완료 여부 (성공 또는 실패)"""
        return self.status in (
            TaskStatus.SUCCESS,
            TaskStatus.FAILURE,
            TaskStatus.REVOKED,
            TaskStatus.REJECTED,
        )

    def is_successful(self) -> bool:
        """성공 여부"""
        return self.status == TaskStatus.SUCCESS

    def is_failed(self) -> bool:
        """실패 여부"""
        return self.status in (TaskStatus.FAILURE, TaskStatus.REJECTED)

    def get(self, timeout: float | None = None) -> T:
        """결과 반환 (실패 시 예외 발생)"""
        if not self.is_ready():
            raise RuntimeError(f"Task {self.task_id} is not ready yet")

        if self.is_failed():
            raise TaskError(
                f"Task {self.task_id} failed: {self.error}",
                task_id=self.task_id,
                error=self.error,
                traceback=self.traceback,
            )

        return self.result  # type: ignore

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        data = asdict(self)
        data["status"] = self.status.value
        for key in ("created_at", "started_at", "completed_at"):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskResult[Any]":
        """딕셔너리에서 생성"""
        if isinstance(data.get("status"), str):
            data["status"] = TaskStatus(data["status"])
        for key in ("created_at", "started_at", "completed_at"):
            if data.get(key) is not None and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        return cls(**data)


# =============================================================================
# Exceptions
# =============================================================================


class TaskError(Exception):
    """태스크 실행 오류"""

    def __init__(
        self,
        message: str,
        task_id: str | None = None,
        error: str | None = None,
        traceback: str | None = None,
    ):
        super().__init__(message)
        self.task_id = task_id
        self.error = error
        self.traceback = traceback


class TaskRetryError(TaskError):
    """재시도 요청 예외"""

    def __init__(
        self,
        message: str = "Task retry requested",
        countdown: float | None = None,
        eta: datetime | None = None,
        max_retries: int | None = None,
    ):
        super().__init__(message)
        self.countdown = countdown
        self.eta = eta
        self.max_retries = max_retries


class TaskRejectError(TaskError):
    """태스크 거부 예외 (재시도 없이 실패)"""

    pass


class TaskTimeoutError(TaskError):
    """태스크 타임아웃 예외"""

    pass


class TaskRevokedError(TaskError):
    """태스크 취소 예외"""

    pass


# =============================================================================
# Helper Functions
# =============================================================================


def create_task_message(
    task_name: str,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    *,
    task_id: str | None = None,
    queue: str = "default",
    priority: TaskPriority = TaskPriority.NORMAL,
    countdown: float | None = None,
    eta: datetime | None = None,
    expires: datetime | None = None,
    correlation_id: str | None = None,
    max_retries: int = 0,
) -> TaskMessage:
    """태스크 메시지 생성 헬퍼"""
    return TaskMessage(
        task_id=task_id or str(uuid.uuid4()),
        task_name=task_name,
        args=args,
        kwargs=kwargs or {},
        queue=queue,
        priority=priority,
        countdown=countdown,
        eta=eta,
        expires=expires,
        correlation_id=correlation_id,
        max_retries=max_retries,
    )


# =============================================================================
# Serializers
# =============================================================================


class Serializer(ABC):
    """메시지 직렬화기 인터페이스"""

    @abstractmethod
    def serialize(self, data: Any) -> bytes:
        """데이터 직렬화"""
        pass

    @abstractmethod
    def deserialize(self, data: bytes) -> Any:
        """데이터 역직렬화"""
        pass


class JSONSerializer(Serializer):
    """JSON 직렬화기"""

    def serialize(self, data: Any) -> bytes:
        return json.dumps(data, default=str).encode("utf-8")

    def deserialize(self, data: bytes) -> Any:
        return json.loads(data.decode("utf-8"))


class PickleSerializer(Serializer):
    """Pickle 직렬화기 (복잡한 객체용)"""

    def serialize(self, data: Any) -> bytes:
        return pickle.dumps(data)

    def deserialize(self, data: bytes) -> Any:
        return pickle.loads(data)


# 기본 직렬화기
DEFAULT_SERIALIZER = JSONSerializer()
