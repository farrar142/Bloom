"""bloom.task.decorators - 태스크 데코레이터

@Component 클래스 내부에서 사용할 수 있는 @Task 데코레이터입니다.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, TYPE_CHECKING, overload

from .models import Task as TaskModel, TaskPriority

if TYPE_CHECKING:
    from .app import TaskApp, BoundTask


# =============================================================================
# Task Decorator Metadata
# =============================================================================

TASK_METADATA_KEY = "__bloom_task__"


def _get_task_metadata(func: Callable[..., Any]) -> TaskModel | None:
    """함수에서 태스크 메타데이터 조회"""
    return getattr(func, TASK_METADATA_KEY, None)


def _set_task_metadata(func: Callable[..., Any], metadata: TaskModel) -> None:
    """함수에 태스크 메타데이터 설정"""
    setattr(func, TASK_METADATA_KEY, metadata)


def has_task_metadata(func: Callable[..., Any]) -> bool:
    """태스크 메타데이터 존재 여부"""
    return hasattr(func, TASK_METADATA_KEY)


def get_task_metadata(func: Callable[..., Any]) -> TaskModel | None:
    """태스크 메타데이터 조회"""
    # bound method인 경우 __func__에서 조회
    if hasattr(func, "__func__"):
        return _get_task_metadata(func.__func__)
    return _get_task_metadata(func)


# =============================================================================
# @task Decorator (for TaskApp)
# =============================================================================


@overload
def task(
    app: "TaskApp",
    *,
    name: str | None = None,
    queue: str = "default",
    retry: int = 0,
    retry_delay: float = 1.0,
    timeout: float | None = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    bind: bool = False,
    ignore_result: bool = False,
) -> Callable[[Callable[..., Any]], "BoundTask[Any]"]: ...


@overload
def task(app: "TaskApp") -> Callable[[Callable[..., Any]], "BoundTask[Any]"]: ...


def task(
    app: "TaskApp",
    *,
    name: str | None = None,
    queue: str = "default",
    retry: int = 0,
    retry_delay: float = 1.0,
    retry_backoff: bool = True,
    timeout: float | None = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    bind: bool = False,
    autoretry_for: tuple[type[Exception], ...] = (),
    ignore_result: bool = False,
    track_started: bool = True,
    acks_late: bool = False,
    rate_limit: str | None = None,
) -> Callable[[Callable[..., Any]], "BoundTask[Any]"]:
    """독립 함수용 태스크 데코레이터

    TaskApp.task()를 사용하는 것이 더 일반적입니다.

    Examples:
        from bloom.task import TaskApp, task

        app = TaskApp("my_app")

        @task(app, retry=3)
        async def my_task(data):
            ...
    """
    return app.task(
        name=name,
        queue=queue,
        retry=retry,
        retry_delay=retry_delay,
        retry_backoff=retry_backoff,
        timeout=timeout,
        priority=priority,
        bind=bind,
        autoretry_for=autoretry_for,
        ignore_result=ignore_result,
        track_started=track_started,
        acks_late=acks_late,
        rate_limit=rate_limit,
    )


# =============================================================================
# @Task Decorator (for Component classes)
# =============================================================================


class Task:
    """Component 클래스 메서드용 태스크 데코레이터

    @Component 클래스의 메서드를 태스크로 표시합니다.
    TaskListenerRegistrar에 의해 자동으로 TaskApp에 등록됩니다.

    Examples:
        from bloom import Component
        from bloom.task import Task

        @Component
        class EmailService:
            @Task(retry=3, queue="emails")
            async def send_email(self, to: str, subject: str, body: str):
                # 이메일 전송 로직
                pass

        # 사용
        email_service.send_email.delay("user@example.com", "Hello", "World")
    """

    def __init__(
        self,
        app: "TaskApp | None" = None,
        *,
        name: str | None = None,
        queue: str = "default",
        retry: int = 0,
        retry_delay: float = 1.0,
        retry_backoff: bool = True,
        timeout: float | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        bind: bool = False,
        autoretry_for: tuple[type[Exception], ...] = (),
        ignore_result: bool = False,
        track_started: bool = True,
        acks_late: bool = False,
        rate_limit: str | None = None,
    ):
        """
        Args:
            app: TaskApp 인스턴스 (None이면 나중에 등록)
            name: 태스크 이름 (기본: 클래스.메서드 경로)
            queue: 사용할 큐 이름
            retry: 최대 재시도 횟수
            retry_delay: 재시도 간격 (초)
            retry_backoff: 지수 백오프 사용
            timeout: 실행 제한 시간 (초)
            priority: 우선순위
            bind: self 바인딩 여부
            autoretry_for: 자동 재시도할 예외들
            ignore_result: 결과 저장 안함
            track_started: STARTED 상태 추적
            acks_late: 완료 후 ACK
            rate_limit: 속도 제한
        """
        self.app = app
        self.name = name
        self.queue = queue
        self.retry = retry
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff
        self.timeout = timeout
        self.priority = priority
        self.bind = bind
        self.autoretry_for = autoretry_for
        self.ignore_result = ignore_result
        self.track_started = track_started
        self.acks_late = acks_late
        self.rate_limit = rate_limit

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """데코레이터 적용"""
        # 태스크 메타데이터 생성
        task_model = TaskModel(
            name=self.name or "",  # 나중에 설정
            func=func,
            queue=self.queue,
            retry=self.retry,
            retry_delay=self.retry_delay,
            retry_backoff=self.retry_backoff,
            timeout=self.timeout,
            priority=self.priority,
            bind=self.bind,
            autoretry_for=self.autoretry_for,
            ignore_result=self.ignore_result,
            track_started=self.track_started,
            acks_late=self.acks_late,
            rate_limit=self.rate_limit,
        )

        # 메타데이터 저장
        _set_task_metadata(func, task_model)

        # app이 지정된 경우 즉시 등록
        if self.app is not None:
            return self.app.task(
                name=self.name,
                queue=self.queue,
                retry=self.retry,
                retry_delay=self.retry_delay,
                retry_backoff=self.retry_backoff,
                timeout=self.timeout,
                priority=self.priority,
                bind=self.bind,
                autoretry_for=self.autoretry_for,
                ignore_result=self.ignore_result,
                track_started=self.track_started,
                acks_late=self.acks_late,
                rate_limit=self.rate_limit,
            )(func)

        # async 함수인 경우 async wrapper 사용
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return await func(*args, **kwargs)

            # 메타데이터 복사
            _set_task_metadata(async_wrapper, task_model)
            return async_wrapper
        else:

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            # 메타데이터 복사
            _set_task_metadata(wrapper, task_model)
            return wrapper


# =============================================================================
# Helper Functions
# =============================================================================


def get_task_methods(cls: type) -> list[tuple[str, Callable[..., Any], TaskModel]]:
    """클래스에서 @Task 데코레이터가 적용된 메서드 찾기

    Returns:
        [(메서드명, 메서드, TaskModel), ...] 리스트
    """
    results = []

    for name in dir(cls):
        if name.startswith("_"):
            continue

        try:
            attr = getattr(cls, name)
        except AttributeError:
            continue

        if not callable(attr):
            continue

        metadata = get_task_metadata(attr)
        if metadata is not None:
            results.append((name, attr, metadata))

    return results


def scan_task_methods(
    instance: object,
) -> list[tuple[str, Callable[..., Any], TaskModel]]:
    """인스턴스에서 @Task 데코레이터가 적용된 메서드 찾기

    Returns:
        [(메서드명, bound method, TaskModel), ...] 리스트
    """
    results = []

    for name in dir(instance):
        if name.startswith("_"):
            continue

        try:
            attr = getattr(instance, name)
        except AttributeError:
            continue

        if not callable(attr):
            continue

        metadata = get_task_metadata(attr)
        if metadata is not None:
            results.append((name, attr, metadata))

    return results
