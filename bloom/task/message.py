"""TaskMessage - 직렬화 가능한 태스크 메시지

Redis를 통해 전달되는 태스크 정보를 담는 데이터 클래스입니다.
JSON으로 직렬화되어 브로커를 통해 전송됩니다.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    """태스크 상태"""

    PENDING = "PENDING"  # 대기 중
    STARTED = "STARTED"  # 실행 중
    SUCCESS = "SUCCESS"  # 성공
    FAILURE = "FAILURE"  # 실패
    REVOKED = "REVOKED"  # 취소됨
    RETRY = "RETRY"  # 재시도 중


@dataclass
class TaskMessage:
    """
    태스크 메시지

    브로커를 통해 전달되는 태스크 정보입니다.
    함수 자체가 아닌 "태스크 이름"을 전달하여 직렬화 문제를 해결합니다.

    Attributes:
        task_id: 고유 태스크 ID
        task_name: 태스크 이름 (TaskRegistry에서 조회용)
        args: 위치 인자 (JSON 직렬화 가능해야 함)
        kwargs: 키워드 인자 (JSON 직렬화 가능해야 함)
        created_at: 생성 시간
        eta: 예약 실행 시간 (None이면 즉시 실행)
        retries: 현재 재시도 횟수
        max_retries: 최대 재시도 횟수
    """

    task_name: str
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    eta: datetime | None = None
    retries: int = 0
    max_retries: int = 0
    retry_delay: float = 1.0

    def to_json(self) -> str:
        """JSON 문자열로 직렬화"""
        return json.dumps(
            {
                "task_id": self.task_id,
                "task_name": self.task_name,
                "args": list(self.args),
                "kwargs": self.kwargs,
                "created_at": self.created_at.isoformat(),
                "eta": self.eta.isoformat() if self.eta else None,
                "retries": self.retries,
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> TaskMessage:
        """JSON 문자열에서 역직렬화"""
        obj = json.loads(data)
        return cls(
            task_id=obj["task_id"],
            task_name=obj["task_name"],
            args=tuple(obj["args"]),
            kwargs=obj["kwargs"],
            created_at=datetime.fromisoformat(obj["created_at"]),
            eta=datetime.fromisoformat(obj["eta"]) if obj["eta"] else None,
            retries=obj["retries"],
            max_retries=obj["max_retries"],
            retry_delay=obj["retry_delay"],
        )

    def __repr__(self) -> str:
        return f"<TaskMessage {self.task_id[:8]}... {self.task_name}>"


@dataclass
class TaskResult:
    """
    태스크 실행 결과

    Redis에 저장되는 태스크 결과 정보입니다.

    Attributes:
        task_id: 태스크 ID
        state: 태스크 상태
        result: 실행 결과 (성공 시)
        error: 에러 메시지 (실패 시)
        traceback: 스택 트레이스 (실패 시)
        started_at: 실행 시작 시간
        completed_at: 완료 시간
    """

    task_id: str
    state: TaskState = TaskState.PENDING
    result: Any = None
    error: str | None = None
    traceback: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_json(self) -> str:
        """JSON 문자열로 직렬화"""
        return json.dumps(
            {
                "task_id": self.task_id,
                "state": self.state.value,
                "result": self.result,
                "error": self.error,
                "traceback": self.traceback,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "completed_at": (
                    self.completed_at.isoformat() if self.completed_at else None
                ),
            }
        )

    @classmethod
    def from_json(cls, data: str) -> TaskResult:
        """JSON 문자열에서 역직렬화"""
        obj = json.loads(data)
        return cls(
            task_id=obj["task_id"],
            state=TaskState(obj["state"]),
            result=obj["result"],
            error=obj["error"],
            traceback=obj["traceback"],
            started_at=(
                datetime.fromisoformat(obj["started_at"]) if obj["started_at"] else None
            ),
            completed_at=(
                datetime.fromisoformat(obj["completed_at"])
                if obj["completed_at"]
                else None
            ),
        )

    @property
    def is_ready(self) -> bool:
        """완료 여부 (성공/실패/취소)"""
        return self.state in (TaskState.SUCCESS, TaskState.FAILURE, TaskState.REVOKED)

    @property
    def is_successful(self) -> bool:
        """성공 여부"""
        return self.state == TaskState.SUCCESS

    @property
    def is_failed(self) -> bool:
        """실패 여부"""
        return self.state == TaskState.FAILURE

    def __repr__(self) -> str:
        return f"<TaskResult {self.task_id[:8]}... ({self.state.value})>"
