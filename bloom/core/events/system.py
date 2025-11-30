"""시스템 이벤트 정의

프레임워크 내부에서 발생하는 이벤트들입니다.
컨테이너 등록, 인스턴스 생성/소멸, 메서드 호출 등을 추적할 수 있습니다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TYPE_CHECKING

from .base import Event, InMemoryEventBus

if TYPE_CHECKING:
    from ..container import Container
    from ..container.element import Scope
    from ..advice.tracing import CallFrame


# =============================================================================
# 시스템 이벤트 베이스
# =============================================================================


@dataclass
class SystemEvent(Event):
    """시스템 이벤트 베이스 클래스"""

    pass


# =============================================================================
# 컨테이너 이벤트
# =============================================================================


@dataclass
class ContainerRegisteredEvent(SystemEvent):
    """컨테이너가 등록되었을 때 발생"""

    container: "Container" = field(default=None)  # type: ignore
    target_type: type = field(default=None)  # type: ignore

    def __post_init__(self):
        if self.container and not self.target_type:
            self.target_type = self.container.target


# =============================================================================
# 인스턴스 생명주기 이벤트
# =============================================================================


@dataclass
class InstanceCreatedEvent(SystemEvent):
    """인스턴스가 생성되었을 때 발생"""

    instance: Any = field(default=None)
    instance_type: type = field(default=None)  # type: ignore
    scope: "Scope" = field(default=None)  # type: ignore

    def __post_init__(self):
        if self.instance and not self.instance_type:
            self.instance_type = type(self.instance)


@dataclass
class InstanceDestroyingEvent(SystemEvent):
    """인스턴스가 소멸되기 전에 발생 (PreDestroy 전)"""

    instance: Any = field(default=None)
    instance_type: type = field(default=None)  # type: ignore
    scope: "Scope" = field(default=None)  # type: ignore

    def __post_init__(self):
        if self.instance and not self.instance_type:
            self.instance_type = type(self.instance)


# =============================================================================
# 메서드 호출 이벤트
# =============================================================================


@dataclass
class MethodEnteredEvent(SystemEvent):
    """메서드 진입 시 발생"""

    frame: "CallFrame" = field(default=None)  # type: ignore
    instance: Any = field(default=None)
    method_name: str = field(default="")

    def __post_init__(self):
        if self.frame:
            if not self.method_name:
                self.method_name = self.frame.method_name


@dataclass
class MethodExitedEvent(SystemEvent):
    """메서드 정상 종료 시 발생"""

    frame: "CallFrame" = field(default=None)  # type: ignore
    instance: Any = field(default=None)
    method_name: str = field(default="")
    duration_ms: float = field(default=0.0)
    result: Any = field(default=None)

    def __post_init__(self):
        if self.frame:
            if not self.method_name:
                self.method_name = self.frame.method_name
            if not self.duration_ms:
                self.duration_ms = self.frame.elapsed_ms


@dataclass
class MethodErrorEvent(SystemEvent):
    """메서드에서 예외 발생 시"""

    frame: "CallFrame" = field(default=None)  # type: ignore
    instance: Any = field(default=None)
    method_name: str = field(default="")
    error: Exception = field(default=None)  # type: ignore

    def __post_init__(self):
        if self.frame:
            if not self.method_name:
                self.method_name = self.frame.method_name


# =============================================================================
# 시스템 이벤트 버스
# =============================================================================


class SystemEventBus(InMemoryEventBus[SystemEvent]):
    """
    시스템 이벤트 버스

    프레임워크 내부 이벤트를 발행하고 구독하는 버스입니다.
    ContainerManager에서 자동으로 생성되어 @Component로 등록됩니다.

    사용 예시:
        @Component
        class LifecycleLogger:
            system_events: SystemEventBus

            @PostConstruct
            def setup(self):
                self.system_events.subscribe(InstanceCreatedEvent, self.on_created)

            def on_created(self, event: InstanceCreatedEvent):
                print(f"Created: {event.instance_type.__name__}")
    """

    pass
