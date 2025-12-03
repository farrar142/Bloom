"""bloom.core.event.models - 이벤트 모델 정의

이벤트 시스템의 핵심 데이터 클래스를 정의합니다.
"""

from __future__ import annotations

import uuid
from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, TypeVar, Generic, get_type_hints, TYPE_CHECKING


# =============================================================================
# Event Priority & Status
# =============================================================================


class EventPriority(Enum):
    """이벤트 우선순위"""

    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventStatus(Enum):
    """이벤트 처리 상태"""

    PENDING = auto()
    PROCESSING = auto()
    COMPLETED = auto()
    FAILED = auto()
    RETRYING = auto()


# =============================================================================
# Base Event Classes
# =============================================================================


@dataclass
class Event:
    """기본 이벤트 클래스

    모든 이벤트의 베이스 클래스입니다.

    Attributes:
        event_id: 고유 이벤트 ID
        event_type: 이벤트 타입 (문자열)
        payload: 이벤트 데이터
        timestamp: 이벤트 발생 시간
        correlation_id: 연관 이벤트 추적용 ID
        causation_id: 원인 이벤트 ID
        source: 이벤트 발생 소스
        metadata: 추가 메타데이터
        priority: 이벤트 우선순위

    Examples:
        # 기본 이벤트 생성
        event = Event(
            event_type="user.created",
            payload={"user_id": 1, "name": "John"}
        )

        # 연관 이벤트 추적
        event2 = Event(
            event_type="email.sent",
            payload={"email": "john@example.com"},
            correlation_id=event.event_id
        )
    """

    event_type: str
    payload: Any = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    correlation_id: str | None = None
    causation_id: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL

    def with_correlation(self, correlation_id: str) -> Event:
        """correlation_id를 설정한 새 이벤트 반환"""
        return Event(
            event_type=self.event_type,
            payload=self.payload,
            event_id=self.event_id,
            timestamp=self.timestamp,
            correlation_id=correlation_id,
            causation_id=self.causation_id,
            source=self.source,
            metadata=self.metadata,
            priority=self.priority,
        )

    def with_causation(self, causation_id: str) -> Event:
        """causation_id를 설정한 새 이벤트 반환"""
        return Event(
            event_type=self.event_type,
            payload=self.payload,
            event_id=self.event_id,
            timestamp=self.timestamp,
            correlation_id=self.correlation_id,
            causation_id=causation_id,
            source=self.source,
            metadata=self.metadata,
            priority=self.priority,
        )

    def to_dict(self) -> dict[str, Any]:
        """이벤트를 딕셔너리로 변환"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "source": self.source,
            "metadata": self.metadata,
            "priority": self.priority.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """딕셔너리에서 이벤트 생성"""
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=data["event_type"],
            payload=data.get("payload"),
            timestamp=datetime.fromisoformat(data["timestamp"])
            if isinstance(data.get("timestamp"), str)
            else data.get("timestamp", datetime.now()),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            source=data.get("source"),
            metadata=data.get("metadata", {}),
            priority=EventPriority(data.get("priority", EventPriority.NORMAL.value)),
        )


# =============================================================================
# Domain Event
# =============================================================================


T = TypeVar("T")


@dataclass
class DomainEvent(Event, Generic[T]):
    """도메인 이벤트 베이스 클래스

    타입이 지정된 payload를 가지는 도메인 이벤트입니다.
    클래스 이름이 자동으로 event_type이 됩니다.

    Examples:
        @dataclass
        class UserCreatedEvent(DomainEvent[UserCreatedPayload]):
            pass

        # 자동으로 event_type = "UserCreatedEvent"
        event = UserCreatedEvent(payload=UserCreatedPayload(user_id=1))
    """

    def __post_init__(self):
        # 클래스 이름을 event_type으로 사용
        if not self.event_type or self.event_type == "":
            object.__setattr__(self, "event_type", self.__class__.__name__)


# =============================================================================
# Typed Domain Events
# =============================================================================


@dataclass
class UserCreatedPayload:
    """사용자 생성 이벤트 페이로드"""

    user_id: int
    username: str
    email: str | None = None


@dataclass
class UserCreatedEvent(DomainEvent[UserCreatedPayload]):
    """사용자 생성 이벤트"""

    event_type: str = "user.created"


@dataclass
class UserUpdatedPayload:
    """사용자 수정 이벤트 페이로드"""

    user_id: int
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass
class UserUpdatedEvent(DomainEvent[UserUpdatedPayload]):
    """사용자 수정 이벤트"""

    event_type: str = "user.updated"


@dataclass
class UserDeletedPayload:
    """사용자 삭제 이벤트 페이로드"""

    user_id: int


@dataclass
class UserDeletedEvent(DomainEvent[UserDeletedPayload]):
    """사용자 삭제 이벤트"""

    event_type: str = "user.deleted"


# =============================================================================
# Event Result
# =============================================================================


@dataclass
class EventResult:
    """이벤트 처리 결과

    Attributes:
        event_id: 처리된 이벤트 ID
        status: 처리 상태
        handler_name: 처리한 핸들러 이름
        result: 처리 결과 (있는 경우)
        error: 에러 정보 (실패 시)
        duration_ms: 처리 소요 시간 (밀리초)
    """

    event_id: str
    status: EventStatus
    handler_name: str
    result: Any = None
    error: Exception | None = None
    duration_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        return self.status == EventStatus.COMPLETED

    @property
    def is_failure(self) -> bool:
        return self.status == EventStatus.FAILED


# =============================================================================
# Helper Functions
# =============================================================================


def get_event_type(event_or_type: Event | type[Event] | str) -> str:
    """이벤트 또는 이벤트 타입에서 event_type 문자열 추출"""
    if isinstance(event_or_type, str):
        return event_or_type
    elif isinstance(event_or_type, Event):
        return event_or_type.event_type
    elif isinstance(event_or_type, type) and issubclass(event_or_type, Event):
        # 클래스에서 기본 event_type 추출
        try:
            # dataclass의 기본값 확인
            hints = get_type_hints(event_or_type)
            if hasattr(event_or_type, "__dataclass_fields__"):
                fields = event_or_type.__dataclass_fields__
                if "event_type" in fields and fields["event_type"].default:
                    return fields["event_type"].default
        except Exception:
            pass
        return event_or_type.__name__
    else:
        raise ValueError(f"Invalid event type: {event_or_type}")


def create_event(
    event_type: str | type[Event],
    payload: Any = None,
    **kwargs: Any,
) -> Event:
    """이벤트 생성 헬퍼 함수

    Args:
        event_type: 이벤트 타입 (문자열 또는 이벤트 클래스)
        payload: 이벤트 페이로드
        **kwargs: 추가 이벤트 속성

    Returns:
        생성된 이벤트

    Examples:
        # 문자열 타입
        event = create_event("user.created", {"user_id": 1})

        # 클래스 타입
        event = create_event(UserCreatedEvent, UserCreatedPayload(user_id=1))
    """
    if isinstance(event_type, type) and issubclass(event_type, Event):
        return event_type(payload=payload, **kwargs)
    else:
        return Event(event_type=str(event_type), payload=payload, **kwargs)
