"""이벤트 시스템 베이스 클래스"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, Protocol, TypeVar, runtime_checkable


# =============================================================================
# Event Protocol
# =============================================================================


@runtime_checkable
class Event(Protocol):
    """
    이벤트 프로토콜

    pydantic BaseModel과 호환되는 직렬화 인터페이스를 정의합니다.
    dataclass나 pydantic 모델 모두 이 프로토콜을 만족할 수 있습니다.

    Required Methods:
        model_dump(): dict로 변환 (pydantic v2)
        model_validate(): dict에서 인스턴스 생성 (classmethod)

    Example (pydantic):
        class UserCreatedEvent(BaseModel):
            user_id: str
            username: str

    Example (dataclass with mixin):
        @dataclass
        class UserCreatedEvent(EventMixin):
            user_id: str
            username: str
    """

    def model_dump(self) -> dict[str, Any]:
        """이벤트를 dict로 변환"""
        ...

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "Event":
        """dict에서 이벤트 인스턴스 생성"""
        ...


E = TypeVar("E", bound=Event)


# =============================================================================
# EventMixin (dataclass용)
# =============================================================================


class EventMixin:
    """
    dataclass용 이벤트 믹스인

    dataclass에 Event 프로토콜 호환 메서드를 제공합니다.

    Example:
        from dataclasses import dataclass

        @dataclass
        class UserCreatedEvent(EventMixin):
            user_id: str
            username: str

        event = UserCreatedEvent(user_id="123", username="alice")
        data = event.model_dump()  # {"user_id": "123", "username": "alice"}
        restored = UserCreatedEvent.model_validate(data)
    """

    def model_dump(self) -> dict[str, Any]:
        """dataclass를 dict로 변환"""
        from dataclasses import asdict, is_dataclass
        from datetime import datetime

        if not is_dataclass(self):
            raise TypeError(f"{type(self).__name__} is not a dataclass")

        result = {}
        for key, value in asdict(self).items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result

    @classmethod
    def model_validate(cls, data: dict[str, Any]) -> "EventMixin":
        """dict에서 dataclass 인스턴스 생성"""
        from dataclasses import fields, is_dataclass
        from datetime import datetime

        if not is_dataclass(cls):
            raise TypeError(f"{cls.__name__} is not a dataclass")

        # datetime 필드 복원
        converted = {}
        field_types = {f.name: f.type for f in fields(cls)}

        for key, value in data.items():
            if key in field_types:
                field_type = field_types[key]
                # datetime 문자열 복원
                if field_type is datetime and isinstance(value, str):
                    converted[key] = datetime.fromisoformat(value)
                else:
                    converted[key] = value
            else:
                converted[key] = value

        return cls(**converted)  # type: ignore[return-value]


# =============================================================================
# EventBus 추상 인터페이스
# =============================================================================


class EventBus(ABC, Generic[E]):
    """
    이벤트 버스 추상 인터페이스

    이벤트를 발행하고 구독하는 pub/sub 패턴을 제공합니다.
    """

    @abstractmethod
    def publish(self, event: E) -> None:
        """
        이벤트 발행

        Args:
            event: 발행할 이벤트
        """
        ...

    @abstractmethod
    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """
        이벤트 구독

        Args:
            event_type: 구독할 이벤트 타입
            handler: 이벤트 핸들러 함수
        """
        ...

    @abstractmethod
    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """
        구독 해제

        Args:
            event_type: 구독 해제할 이벤트 타입
            handler: 제거할 핸들러 함수
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """모든 구독 해제"""
        ...


# =============================================================================
# InMemoryEventBus 구현
# =============================================================================


class InMemoryEventBus(EventBus[E]):
    """
    메모리 기반 이벤트 버스 구현

    동기적으로 이벤트를 처리합니다.
    이벤트 타입의 상속 계층을 고려하여 부모 타입 핸들러도 호출합니다.
    """

    def __init__(self):
        self._handlers: dict[type, list[Callable[[Any], None]]] = {}
        # 등록된 이벤트 타입들 (부모 검색 최적화용)
        self._registered_types: set[type] = set()

    def publish(self, event: E) -> None:
        """
        이벤트 발행

        이벤트 타입과 그 부모 타입에 등록된 모든 핸들러를 호출합니다.
        """
        event_type = type(event)

        # Fast path: 정확한 타입 핸들러 호출
        handlers = self._handlers.get(event_type)
        if handlers:
            for handler in handlers:
                handler(event)

        # 부모 타입 핸들러 호출 (등록된 타입이 2개 이상일 때만)
        if len(self._registered_types) <= 1:
            return

        # 부모 타입 중 등록된 것만 확인
        called_handlers: set[int] = set()
        if handlers:
            for handler in handlers:
                called_handlers.add(id(handler))

        for cls in event_type.__mro__[1:]:  # 자기 자신 제외
            if cls is object:
                continue
            if cls not in self._registered_types:
                continue
            parent_handlers = self._handlers.get(cls)
            if parent_handlers:
                for handler in parent_handlers:
                    handler_id = id(handler)
                    if handler_id not in called_handlers:
                        handler(event)
                        called_handlers.add(handler_id)

    def subscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """이벤트 구독"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []

        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)
            self._registered_types.add(event_type)

    def unsubscribe(self, event_type: type[E], handler: Callable[[E], None]) -> None:
        """구독 해제"""
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass  # 핸들러가 없으면 무시

    def clear(self) -> None:
        """모든 구독 해제"""
        self._handlers.clear()
        self._registered_types.clear()

    def __len__(self) -> int:
        """등록된 총 핸들러 수"""
        return sum(len(handlers) for handlers in self._handlers.values())
