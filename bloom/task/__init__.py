"""Bloom Task System - Celery 스타일 태스크 시스템

@ 메서드를 태스크로 정의하고,
delay(), schedule() 등으로 실행할 수 있습니다.

Lazy import: 실제 사용 시에만 모듈 로드
"""

__all__ = [
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


def __getattr__(name: str):
    """Lazy import"""
    # Result
    if name in ("AbstractTaskResult", "TaskResult", "AsyncTaskResult", "ScheduledTask"):
        from .result import AbstractTaskResult, TaskResult, AsyncTaskResult, ScheduledTask
        return locals()[name]
    
    # Backend
    if name in ("TaskBackend", "AsyncioTaskBackend"):
        from .backend import TaskBackend, AsyncioTaskBackend
        return locals()[name]
    
    # Decorator
    if name in ("Task", "TaskElement", "TaskDescriptor", "BoundTask", "is_task", "get_task_element"):
        from .decorator import Task, TaskElement, TaskDescriptor, BoundTask, is_task, get_task_element
        return locals()[name]
    
    # Advice
    if name == "TaskMethodAdvice":
        from .advice import TaskMethodAdvice
        return TaskMethodAdvice
    
    # Trigger
    if name in ("Trigger", "CronTrigger", "FixedRateTrigger", "FixedDelayTrigger"):
        from .trigger import Trigger, CronTrigger, FixedRateTrigger, FixedDelayTrigger
        return locals()[name]
    
    # Distributed
    if name in ("DistributedTaskBackend", "DistributedTaskResult"):
        from .distributed import DistributedTaskBackend, DistributedTaskResult
        return locals()[name]
    
    # Registry
    if name in ("TaskRegistry", "TaskInfo"):
        from .registry import TaskRegistry, TaskInfo
        return locals()[name]
    
    # Message
    if name in ("TaskMessage", "TaskState"):
        from .message import TaskMessage, TaskState
        return locals()[name]
    if name == "TaskResultMessage":
        from .message import TaskResult as TaskResultMessage
        return TaskResultMessage
    
    # Broker
    if name in ("Broker", "InMemoryBroker", "RedisBroker"):
        from .broker import Broker, InMemoryBroker, RedisBroker
        return locals()[name]
    
    # Queue Application
    if name == "QueueApplication":
        from .queue_app import QueueApplication
        return QueueApplication
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
