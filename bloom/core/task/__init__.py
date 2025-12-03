"""bloom.core.task - Celery 스타일 분산 태스크 큐 시스템

Celery와 유사한 분산 태스크 큐 시스템을 제공합니다.

Architecture:
    - TaskApp: 태스크 정의 및 등록 관리
    - TaskBroker: 메시지 브로커 (메시지 전달)
    - TaskBackend: 결과 저장소
    - Worker: 태스크 실행기

Components:
    - models: Task, TaskMessage, TaskResult, TaskStatus 등
    - broker: TaskBroker ABC, LocalBroker 등
    - backend: TaskBackend ABC, LocalBackend 등
    - app: TaskApp (태스크 등록/관리)
    - decorators: @Task 데코레이터
    - worker: Worker (태스크 실행)
    - cli: bloom queue CLI

Usage:
    # 1. TaskApp 생성
    from bloom.core.task import TaskApp

    task_app = TaskApp("my_tasks")

    # 2. 태스크 정의
    @task_app.task(retry=3, timeout=60)
    async def send_email(to: str, subject: str, body: str) -> dict:
        # 이메일 전송 로직
        return {"status": "sent", "to": to}

    # 3. 태스크 호출
    # 비동기 실행 (즉시 반환, 백그라운드 처리)
    result = send_email.delay("user@example.com", "Hello", "World")

    # 또는 파라미터와 함께
    result = send_email.apply_async(
        args=("user@example.com", "Hello", "World"),
        countdown=10,  # 10초 후 실행
        eta=datetime.now() + timedelta(hours=1),  # 특정 시간에 실행
    )

    # 4. 결과 확인
    if result.ready():
        print(result.get())  # {"status": "sent", "to": "user@example.com"}

    # 5. CLI로 워커 실행
    # bloom queue --app=myapp:task_app worker --concurrency=4

Example with Bloom Application:
    from bloom import Application, Component
    from bloom.core.task import TaskApp, Task

    task_app = TaskApp("email_tasks")

    @Component
    class EmailService:
        @Task(task_app, retry=3)
        async def send_welcome_email(self, user_id: int) -> dict:
            # 환영 이메일 전송
            return {"sent": True}

    # 메인 앱에서 태스크 앱 통합
    app = Application("my_app")
    app.register_task_app(task_app)
"""

from .models import (
    Task,
    TaskMessage,
    TaskResult,
    TaskStatus,
    TaskPriority,
    TaskState,
    TaskError,
    TaskRetryError,
    TaskRejectError,
    TaskTimeoutError,
    TaskRevokedError,
    create_task_message,
)
from .broker import TaskBroker
from .backend import TaskBackend
from .app import TaskApp, TaskRegistry, AsyncResult, BoundTask, Signature, Chain
from .decorators import task, Task as TaskDecorator, get_task_methods, scan_task_methods
from .worker import Worker, WorkerConfig, run_worker

__all__ = [
    # Models
    "Task",
    "TaskMessage",
    "TaskResult",
    "TaskStatus",
    "TaskPriority",
    "TaskState",
    "TaskError",
    "TaskRetryError",
    "TaskRejectError",
    "TaskTimeoutError",
    "TaskRevokedError",
    "create_task_message",
    # Interfaces
    "TaskBroker",
    "TaskBackend",
    # App
    "TaskApp",
    "TaskRegistry",
    "AsyncResult",
    "BoundTask",
    "Signature",
    "Chain",
    # Decorators
    "task",
    "TaskDecorator",
    "get_task_methods",
    "scan_task_methods",
    # Worker
    "Worker",
    "WorkerConfig",
    "run_worker",
]
