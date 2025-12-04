"""bloom.task.app - TaskApp 및 TaskRegistry

태스크 정의, 등록, 관리를 담당합니다.
Celery의 Celery 클래스와 유사한 역할입니다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Awaitable, TypeVar, Generic, TYPE_CHECKING, overload

from .models import (
    Task,
    TaskMessage,
    TaskResult,
    TaskStatus,
    TaskPriority,
    create_task_message,
)
from .broker import TaskBroker
from .backend import TaskBackend

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


T = TypeVar("T")
TaskFunc = TypeVar("TaskFunc", bound=Callable[..., Any])


# =============================================================================
# Async Result
# =============================================================================


class AsyncResult(Generic[T]):
    """비동기 태스크 결과

    태스크 호출 시 반환되는 결과 객체입니다.
    결과가 준비될 때까지 대기하거나 상태를 확인할 수 있습니다.

    Examples:
        result = my_task.delay("arg1", "arg2")

        # 상태 확인
        if result.ready():
            print(result.get())

        # 결과 대기 (blocking)
        value = await result.get_async(timeout=10)
    """

    def __init__(
        self,
        task_id: str,
        backend: TaskBackend | None = None,
        app: "TaskApp | None" = None,
    ):
        self.task_id = task_id
        self._backend = backend
        self._app = app
        self._cache: TaskResult[T] | None = None

    @property
    def backend(self) -> TaskBackend | None:
        """결과 백엔드"""
        if self._backend:
            return self._backend
        if self._app:
            return self._app.backend
        return None

    async def _get_task_result(self) -> TaskResult[T] | None:
        """내부: 태스크 결과 조회"""
        if self.backend is None:
            return None
        return await self.backend.get_result(self.task_id)

    async def status_async(self) -> TaskStatus:
        """현재 상태 조회"""
        result = await self._get_task_result()
        if result:
            return result.status
        return TaskStatus.PENDING

    def status(self) -> TaskStatus:
        """현재 상태 (동기)"""
        import asyncio

        return asyncio.get_event_loop().run_until_complete(self.status_async())

    async def ready_async(self) -> bool:
        """완료 여부 (비동기)"""
        result = await self._get_task_result()
        return result is not None and result.is_ready()

    def ready(self) -> bool:
        """완료 여부 (동기)"""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            # 이미 이벤트 루프가 실행 중이면 Task로 실행
            future = asyncio.ensure_future(self.ready_async())
            return loop.run_until_complete(future)
        except RuntimeError:
            # 이벤트 루프가 없으면 새로 생성
            return asyncio.run(self.ready_async())

    async def successful_async(self) -> bool:
        """성공 여부 (비동기)"""
        result = await self._get_task_result()
        return result is not None and result.is_successful()

    async def failed_async(self) -> bool:
        """실패 여부 (비동기)"""
        result = await self._get_task_result()
        return result is not None and result.is_failed()

    async def get_async(
        self,
        timeout: float | None = None,
        interval: float = 0.1,
    ) -> T:
        """결과 대기 및 반환 (비동기)

        Args:
            timeout: 최대 대기 시간 (초)
            interval: 폴링 간격 (초)

        Raises:
            TimeoutError: 타임아웃 시
            TaskError: 태스크 실패 시
        """
        if self.backend is None:
            raise RuntimeError("No backend configured")

        result = await self.backend.wait_for_result(
            self.task_id,
            timeout=timeout,
            interval=interval,
        )

        if result is None:
            raise TimeoutError(
                f"Task {self.task_id} did not complete within {timeout}s"
            )

        return result.get()

    def get(self, timeout: float | None = None) -> T:
        """결과 대기 및 반환 (동기)"""
        import asyncio

        return asyncio.run(self.get_async(timeout=timeout))

    async def revoke_async(self, terminate: bool = False) -> None:
        """태스크 취소 (비동기)"""
        if self.backend:
            await self.backend.update_status(
                self.task_id,
                TaskStatus.REVOKED,
            )

    def revoke(self, terminate: bool = False) -> None:
        """태스크 취소 (동기)"""
        import asyncio

        asyncio.run(self.revoke_async(terminate=terminate))

    def __repr__(self) -> str:
        return f"<AsyncResult: {self.task_id}>"


# =============================================================================
# Bound Task
# =============================================================================


class BoundTask(Generic[T]):
    """바인딩된 태스크

    TaskApp에 등록된 태스크를 나타냅니다.
    delay(), apply_async() 등의 메서드로 태스크를 호출할 수 있습니다.

    Examples:
        @task_app.task
        async def send_email(to: str, subject: str):
            ...

        # 비동기 호출
        result = send_email.delay("user@example.com", "Hello")

        # 옵션과 함께 호출
        result = send_email.apply_async(
            args=("user@example.com", "Hello"),
            countdown=60,
        )
    """

    def __init__(
        self,
        task: Task,
        app: "TaskApp",
    ):
        self.task = task
        self.app = app
        self.name = task.name

        # 함수 메타데이터 복사
        if task.func:
            self.__name__ = task.func.__name__
            self.__doc__ = task.func.__doc__
            self.__module__ = task.func.__module__

    async def __call__(self, *args: Any, **kwargs: Any) -> T:
        """직접 호출 (로컬 실행)"""
        if self.task.func is None:
            raise RuntimeError(f"Task {self.name} has no function")

        result = self.task.func(*args, **kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result

    def delay(self, *args: Any, **kwargs: Any) -> AsyncResult[T]:
        """태스크를 큐에 추가 (비동기 실행)

        delay()는 apply_async()의 간편 버전입니다.

        Examples:
            result = my_task.delay("arg1", "arg2", key="value")
        """
        import asyncio

        return asyncio.get_event_loop().run_until_complete(
            self.apply_async(args=args, kwargs=kwargs)
        )

    async def apply_async(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        *,
        task_id: str | None = None,
        countdown: float | None = None,
        eta: datetime | None = None,
        expires: datetime | timedelta | None = None,
        priority: TaskPriority | None = None,
        queue: str | None = None,
        correlation_id: str | None = None,
    ) -> AsyncResult[T]:
        """태스크를 큐에 추가 (상세 옵션)

        Args:
            args: 위치 인자
            kwargs: 키워드 인자
            task_id: 태스크 ID (지정하지 않으면 자동 생성)
            countdown: 지연 실행 시간 (초)
            eta: 실행 예정 시간
            expires: 만료 시간
            priority: 우선순위
            queue: 대상 큐
            correlation_id: 관련 요청 ID

        Returns:
            AsyncResult 객체
        """
        # 만료 시간 처리
        expires_dt: datetime | None = None
        if isinstance(expires, timedelta):
            expires_dt = datetime.now() + expires
        elif isinstance(expires, datetime):
            expires_dt = expires

        # 메시지 생성
        message = create_task_message(
            task_name=self.name,
            args=args or (),
            kwargs=kwargs or {},
            task_id=task_id,
            countdown=countdown,
            eta=eta,
            expires=expires_dt,
            priority=priority or self.task.priority,
            queue=queue or self.task.queue,
            correlation_id=correlation_id,
            max_retries=self.task.retry,
        )

        # 초기 상태 저장
        if self.app.backend and not self.task.ignore_result:
            await self.app.backend.store_result(
                message.task_id,
                TaskResult(task_id=message.task_id, status=TaskStatus.PENDING),
            )

        # 브로커에 발행
        if self.app.broker:
            await self.app.broker.publish(message)

        return AsyncResult(
            task_id=message.task_id,
            app=self.app,
        )

    def s(self, *args: Any, **kwargs: Any) -> "Signature":
        """시그니처 생성 (체인용)"""
        return Signature(self, args=args, kwargs=kwargs)

    def si(self, *args: Any, **kwargs: Any) -> "Signature":
        """불변 시그니처 생성 (이전 결과 무시)"""
        return Signature(self, args=args, kwargs=kwargs, immutable=True)

    def __repr__(self) -> str:
        return f"<BoundTask: {self.name}>"


# =============================================================================
# Signature (for chains)
# =============================================================================


class Signature:
    """태스크 시그니처 (체인/그룹용)

    태스크와 인자를 묶어서 나중에 실행할 수 있게 합니다.

    Examples:
        sig = my_task.s("arg1", "arg2")
        result = await sig.apply_async()
    """

    def __init__(
        self,
        task: BoundTask[Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        *,
        immutable: bool = False,
        options: dict[str, Any] | None = None,
    ):
        self.task = task
        self.args = args
        self.kwargs = kwargs or {}
        self.immutable = immutable
        self.options = options or {}

    async def apply_async(
        self,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
        **options: Any,
    ) -> AsyncResult[Any]:
        """시그니처 실행"""
        # 인자 병합 (immutable이 아니면)
        final_args = self.args
        final_kwargs = dict(self.kwargs)

        if not self.immutable:
            if args:
                final_args = args + self.args
            if kwargs:
                final_kwargs.update(kwargs)

        # 옵션 병합
        final_options = dict(self.options)
        final_options.update(options)

        return await self.task.apply_async(
            args=final_args,
            kwargs=final_kwargs,
            **final_options,
        )

    def __or__(self, other: "Signature") -> "Chain":
        """| 연산자로 체인 생성"""
        return Chain(self, other)

    def __repr__(self) -> str:
        return f"{self.task.name}({self.args}, {self.kwargs})"


class Chain:
    """태스크 체인

    여러 태스크를 순차적으로 실행합니다.
    이전 태스크의 결과가 다음 태스크의 첫 인자로 전달됩니다.

    Examples:
        chain = task1.s("arg") | task2.s() | task3.s()
        result = await chain.apply_async()
    """

    def __init__(self, *tasks: Signature):
        self.tasks = list(tasks)

    def __or__(self, other: Signature) -> "Chain":
        """체인에 태스크 추가"""
        self.tasks.append(other)
        return self

    async def apply_async(self) -> AsyncResult[Any]:
        """체인 실행"""
        if not self.tasks:
            raise ValueError("Empty chain")

        # 첫 태스크 실행
        result = await self.tasks[0].apply_async()

        # TODO: 실제로는 브로커 레벨에서 체인 지원 필요
        # 현재는 단순 구현

        return result

    def __repr__(self) -> str:
        return " | ".join(repr(t) for t in self.tasks)


# =============================================================================
# Task Registry
# =============================================================================


class TaskRegistry:
    """태스크 레지스트리

    등록된 모든 태스크를 관리합니다.
    """

    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def register(self, task: Task) -> None:
        """태스크 등록"""
        self._tasks[task.name] = task
        logger.debug(f"Registered task: {task.name}")

    def unregister(self, name: str) -> bool:
        """태스크 등록 해제"""
        if name in self._tasks:
            del self._tasks[name]
            return True
        return False

    def get(self, name: str) -> Task | None:
        """태스크 조회"""
        return self._tasks.get(name)

    def get_all(self) -> dict[str, Task]:
        """모든 태스크 조회"""
        return dict(self._tasks)

    def __contains__(self, name: str) -> bool:
        return name in self._tasks

    def __len__(self) -> int:
        return len(self._tasks)


# =============================================================================
# Task App
# =============================================================================


class TaskApp:
    """태스크 애플리케이션

    태스크 정의, 등록, 실행을 관리하는 메인 클래스입니다.
    Celery의 Celery 클래스와 유사합니다.

    Examples:
        # TaskApp 생성
        task_app = TaskApp("my_tasks")

        # 브로커/백엔드 설정 (선택)
        task_app.config_from_object({
            "broker_url": "redis://localhost:6379/0",
            "result_backend": "redis://localhost:6379/1",
        })

        # 태스크 정의
        @task_app.task
        async def send_email(to: str, subject: str):
            ...

        # 태스크 호출
        result = send_email.delay("user@example.com", "Hello")
    """

    def __init__(
        self,
        name: str = "default",
        *,
        broker: TaskBroker | None = None,
        backend: TaskBackend | None = None,
    ):
        self.name = name
        self.broker = broker
        self.backend = backend
        self.registry = TaskRegistry()
        self._config: dict[str, Any] = {}

    def config_from_object(self, config: dict[str, Any] | object) -> None:
        """설정 로드"""
        if isinstance(config, dict):
            self._config.update(config)
        else:
            # 객체의 대문자 속성들을 설정으로 사용
            for key in dir(config):
                if key.isupper():
                    self._config[key.lower()] = getattr(config, key)

    @overload
    def task(self, func: TaskFunc) -> BoundTask[Any]: ...

    @overload
    def task(
        self,
        *,
        name: str | None = None,
        queue: str = "default",
        retry: int = 0,
        retry_delay: float = 1.0,
        timeout: float | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        bind: bool = False,
        ignore_result: bool = False,
    ) -> Callable[[TaskFunc], BoundTask[Any]]: ...

    def task(
        self,
        func: TaskFunc | None = None,
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
    ) -> BoundTask[Any] | Callable[[TaskFunc], BoundTask[Any]]:
        """태스크 데코레이터

        함수를 태스크로 등록합니다.

        Args:
            func: 태스크 함수
            name: 태스크 이름 (기본: 함수의 전체 경로)
            queue: 사용할 큐 이름
            retry: 최대 재시도 횟수
            retry_delay: 재시도 간격 (초)
            retry_backoff: 지수 백오프 사용 여부
            timeout: 실행 제한 시간 (초)
            priority: 우선순위
            bind: self 바인딩 여부
            autoretry_for: 자동 재시도할 예외 타입들
            ignore_result: 결과 저장 안함
            track_started: STARTED 상태 추적
            acks_late: 완료 후 ACK
            rate_limit: 속도 제한

        Returns:
            BoundTask 인스턴스

        Examples:
            @task_app.task
            async def simple_task():
                ...

            @task_app.task(retry=3, timeout=60)
            async def task_with_options(data):
                ...

            @task_app.task(bind=True)
            async def task_with_self(self, data):
                # self.retry() 가능
                ...
        """

        def decorator(fn: TaskFunc) -> BoundTask[Any]:
            task_name = name
            if task_name is None:
                module = getattr(fn, "__module__", "__main__")
                qualname = getattr(fn, "__qualname__", fn.__name__)
                task_name = f"{module}.{qualname}"

            task = Task(
                name=task_name,
                func=fn,
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

            # 레지스트리에 등록
            self.registry.register(task)

            # BoundTask 반환
            return BoundTask(task, self)

        if func is not None:
            return decorator(func)
        return decorator

    def get_task(self, name: str) -> BoundTask[Any] | None:
        """이름으로 태스크 조회"""
        task = self.registry.get(name)
        if task:
            return BoundTask(task, self)
        return None

    def register_task(
        self,
        name: str,
        func: Callable[..., Any],
        *,
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
    ) -> BoundTask[Any]:
        """태스크 직접 등록

        데코레이터 없이 함수를 태스크로 등록합니다.
        @Service 클래스의 @Task 메서드를 동적으로 등록할 때 사용합니다.

        Args:
            name: 태스크 이름
            func: 태스크 함수 (bound method 포함)
            queue: 사용할 큐 이름
            retry: 최대 재시도 횟수
            retry_delay: 재시도 간격 (초)
            timeout: 실행 제한 시간 (초)
            priority: 우선순위
            ...

        Returns:
            BoundTask 인스턴스
        """
        task = Task(
            name=name,
            func=func,
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

        # 레지스트리에 등록
        self.registry.register(task)

        # BoundTask 반환
        return BoundTask(task, self)

    async def send_task(
        self,
        name: str,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        **options: Any,
    ) -> AsyncResult[Any]:
        """이름으로 태스크 전송

        태스크 함수에 직접 접근하지 않고 이름으로 태스크를 호출합니다.
        다른 프로세스/서버에서 정의된 태스크를 호출할 때 유용합니다.
        """
        task = self.get_task(name)
        if task:
            return await task.apply_async(args=args, kwargs=kwargs, **options)

        # 태스크가 없어도 메시지 발송 (원격 태스크)
        message = create_task_message(
            task_name=name,
            args=args,
            kwargs=kwargs or {},
            **options,
        )

        if self.broker:
            await self.broker.publish(message)

        return AsyncResult(task_id=message.task_id, app=self)

    def __repr__(self) -> str:
        return f"<TaskApp: {self.name}>"
