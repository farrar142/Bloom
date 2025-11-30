"""Bloom Task System - Celery 스타일 태스크 시스템

@Task 데코레이터로 메서드를 태스크로 정의하고,
delay(), schedule() 등으로 실행할 수 있습니다.

사용 예시:
    from bloom import Component
    from bloom.task import Task, TaskResult

    @Component
    class EmailService:
        @Task
        def send_email(self, to: str, subject: str) -> str:
            # 이메일 전송 로직
            return f"Sent to {to}"

    # 1. 백그라운드 실행 (비동기)
    result = service.send_email.delay("user@example.com", "Hello")
    value = result.get()  # 결과 대기

    # 2. 직접 실행 (동기)
    value = service.send_email("user@example.com", "Hello")

    # 3. 스케줄 등록
    task = service.send_email.schedule(fixed_rate=60)  # 60초마다
    task.pause()   # 일시정지
    task.resume()  # 재개

구조:
    TaskBackend (추상 인터페이스)
      └── AsyncioTaskBackend (기본 구현)

    @Task → BoundTask (메서드 래퍼)
      ├── delay(*args) → TaskResult (비동기 실행)
      ├── __call__(*args) → T (동기 실행)
      └── schedule(...) → ScheduledTask (스케줄 등록)
"""

# Result
from .result import AbstractTaskResult, TaskResult, AsyncTaskResult, ScheduledTask

# Backend
from .backend import TaskBackend, AsyncioTaskBackend

# Decorator
from .decorator import (
    Task,
    TaskElement,
    TaskDescriptor,
    BoundTask,
    is_task,
    get_task_element,
)

# Advice
from .advice import TaskMethodAdvice

# Trigger (스케줄용)
from .trigger import Trigger, CronTrigger, FixedRateTrigger, FixedDelayTrigger

# Distributed
from .distributed import DistributedTaskBackend, DistributedTaskResult

# Registry
from .registry import TaskRegistry, TaskInfo

# Message
from .message import TaskMessage, TaskState
from .message import TaskResult as TaskResultMessage

# Broker
from .broker import Broker, InMemoryBroker, RedisBroker

# Queue Application
from .queue_app import QueueApplication

__all__ = [
    # Result
    "TaskResult",
    # Result
    "AbstractTaskResult",
    "TaskResult",
    "AsyncTaskResult",
    "ScheduledTask",
    # Backend
    "TaskBackend",
    "AsyncioTaskBackend",
    # Decorator
    "Task",
    "TaskElement",
    "TaskDescriptor",
    "BoundTask",
    "is_task",
    "get_task_element",
    # Advice
    "TaskMethodAdvice",
    # Trigger
    "Trigger",
    "CronTrigger",
    "FixedRateTrigger",
    "FixedDelayTrigger",
    # Distributed
    "DistributedTaskBackend",
    "DistributedTaskResult",
    # Registry
    "TaskRegistry",
    "TaskInfo",
    # Message
    "TaskMessage",
    "TaskState",
    "TaskResultMessage",
    # Broker
    "Broker",
    "InMemoryBroker",
    "RedisBroker",
    # Queue Application
    "QueueApplication",
]
