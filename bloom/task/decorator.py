"""@Task 데코레이터 - Celery 스타일 태스크 정의

@Task 데코레이터로 메서드를 태스크로 정의합니다.

Example:
    @Component
    class EmailService:
        @Task
        def send_email(self, to: str, subject: str) -> str:
            return f"Sent to {to}"

    # 1. 백그라운드 실행 (비동기)
    result = service.send_email.delay("user@example.com", "Hello")
    value = result.get()

    # 2. 직접 실행 (동기)
    value = service.send_email("user@example.com", "Hello")

    # 3. 스케줄 등록
    task = service.send_email.schedule(fixed_rate=60)
"""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING, Any, Callable, Concatenate, Generic, TypeVar, overload

from bloom.core.abstract import ProxyableDescriptor
from bloom.core.container import HandlerContainer
from bloom.core.container.element import Element

from .result import AbstractTaskResult, AsyncTaskResult, ScheduledTask, TaskResult
from .trigger import CronTrigger, FixedDelayTrigger, FixedRateTrigger, Trigger

if TYPE_CHECKING:
    from .backend import TaskBackend

T = TypeVar("T")


class TaskElement(Element):
    """태스크 메타데이터 Element"""

    key = "task"

    def __init__(
        self,
        name: str | None = None,
        bind: bool = False,
        max_retries: int = 0,
        retry_delay: float = 1.0,
    ):
        super().__init__()
        self.metadata["name"] = name
        self.metadata["bind"] = bind
        self.metadata["max_retries"] = max_retries
        self.metadata["retry_delay"] = retry_delay

    @property
    def name(self) -> str | None:
        return self.metadata.get("name")

    @property
    def bind(self) -> bool:
        return self.metadata.get("bind", False)

    @property
    def max_retries(self) -> int:
        return self.metadata.get("max_retries", 0)

    @property
    def retry_delay(self) -> float:
        return self.metadata.get("retry_delay", 1.0)


class BoundTask[T, **P, R]:
    """
    인스턴스에 바인딩된 태스크

    메서드 호출, delay(), schedule() 등을 제공합니다.
    """

    def __init__(
        self,
        handler: Callable[Concatenate[T, P], R],
        instance: Any,
        backend: TaskBackend | None = None,
        element: TaskElement | None = None,
    ):
        self._handler = handler
        self._instance = instance
        self._backend = backend
        self._element = element
        # 태스크 이름: @Task(name=...)으로 지정한 이름 또는 ClassName.method_name
        if element and element.name:
            self._name = element.name
        else:
            class_name = type(instance).__name__
            self._name = f"{class_name}.{handler.__name__}"
        # 프록시 지원
        self._proxy: Any = None
        self._use_proxy: bool = False

    @property
    def name(self) -> str:
        return self._name

    def _get_backend(self) -> TaskBackend | None:
        """백엔드를 가져옵니다"""
        if self._backend is not None:
            return self._backend

        # 인스턴스에 주입된 백엔드 확인
        if self._instance is not None:
            backend = getattr(self._instance, "_task_backend", None)
            if backend is not None:
                return backend

        # ContainerManager에서 TaskBackend 조회
        from bloom.core.manager import try_get_current_manager

        manager = try_get_current_manager()
        if manager is not None:
            from .backend import TaskBackend

            backend = manager.get_instance(TaskBackend, raise_exception=False)
            if backend is not None:
                # 캐시하여 다음 호출 시 빠르게 반환
                if self._instance is not None:
                    setattr(self._instance, "_task_backend", backend)
                return backend

        return None

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """직접 호출 - 프록시가 있으면 프록시를 통해 실행"""
        # 프록시가 적용되어 있으면 프록시를 통해 호출
        if self._use_proxy and self._proxy is not None:
            return self._proxy(*args, **kwargs)

        # 프록시가 없으면 직접 호출
        return self._call_direct(*args, **kwargs)

    def _call_direct(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Advice 없이 직접 호출"""
        result = self._handler(self._instance, *args, **kwargs)
        if asyncio.iscoroutine(result):
            # 비동기 함수면 이벤트 루프에서 실행
            try:
                loop = asyncio.get_running_loop()
                return loop.run_until_complete(result)
            except RuntimeError:
                # 이벤트 루프가 없으면 새로 생성
                return asyncio.run(result)
        return result

    def delay(self, *args: P.args, **kwargs: P.kwargs) -> AbstractTaskResult[R]:
        """백그라운드에서 실행 (동기 결과)"""
        backend = self._get_backend()
        if backend is None:
            raise RuntimeError(
                "TaskBackend is not configured. Use @Factory to provide TaskBackend."
            )

        # DistributedTaskBackend인 경우: 태스크 이름으로 제출
        from .distributed import DistributedTaskBackend

        if isinstance(backend, DistributedTaskBackend):
            return backend.submit_by_name(
                task_name=self._name,
                args=args,
                kwargs=kwargs,
            )

        # AsyncioTaskBackend인 경우: 로컬 함수로 제출
        def execute() -> R:
            # 프록시가 있으면 프록시를 통해 실행 (Advice 적용)
            if self._use_proxy and self._proxy is not None:
                return self._proxy(*args, **kwargs)
            # 프록시가 없으면 직접 실행
            result = self._handler(self._instance, *args, **kwargs)
            if asyncio.iscoroutine(result):
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(result)
                finally:
                    loop.close()
            return result

        return backend.submit(execute)

    async def delay_async(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> AbstractTaskResult[R]:
        """백그라운드에서 실행 (비동기 결과)"""
        backend = self._get_backend()
        if backend is None:
            raise RuntimeError(
                "TaskBackend is not configured. Use @Factory to provide TaskBackend."
            )

        # DistributedTaskBackend인 경우: 태스크 이름으로 제출
        from .distributed import DistributedTaskBackend

        if isinstance(backend, DistributedTaskBackend):
            return await backend.submit_by_name_async(
                task_name=self._name,
                args=args,
                kwargs=kwargs,
            )

        # AsyncioTaskBackend인 경우: 로컬 함수로 제출
        async def execute() -> R:
            # 프록시가 있으면 프록시를 통해 실행 (Advice 적용)
            if self._use_proxy and self._proxy is not None:
                result = self._proxy(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return await result
                return result
            # 프록시가 없으면 직접 실행
            result = self._handler(self._instance, *args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result

        return await backend.submit_async(execute)

    def schedule(
        self,
        *,
        fixed_rate: float | None = None,
        fixed_delay: float | None = None,
        cron: str | None = None,
        initial_delay: float = 0,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> ScheduledTask[T, P, R]:
        """
        스케줄에 등록

        Args:
            fixed_rate: 시작 시점 기준 고정 간격 (초)
            fixed_delay: 완료 시점 기준 고정 지연 (초)
            cron: cron 표현식 (분 시 일 월 요일)
            initial_delay: 첫 실행 전 지연 (초)
            args: 태스크 인자
            kwargs: 태스크 키워드 인자

        Returns:
            ScheduledTask: 스케줄된 태스크 (제어용)
        """
        backend = self._get_backend()
        if backend is None:
            raise RuntimeError(
                "TaskBackend is not configured. Use @Factory to provide TaskBackend."
            )

        # 트리거 생성
        trigger: Trigger
        count = sum([fixed_rate is not None, fixed_delay is not None, cron is not None])
        if count == 0:
            raise ValueError(
                "One of fixed_rate, fixed_delay, or cron must be specified"
            )
        if count > 1:
            raise ValueError(
                "Only one of fixed_rate, fixed_delay, or cron can be specified"
            )

        if fixed_rate is not None:
            trigger = FixedRateTrigger(seconds=fixed_rate, initial_delay=initial_delay)
        elif fixed_delay is not None:
            trigger = FixedDelayTrigger(
                seconds=fixed_delay, initial_delay=initial_delay
            )
        else:
            trigger = CronTrigger(cron)  # type: ignore

        # ScheduledTask 생성
        # 프록시가 있으면 프록시를 전달하여 Advice가 적용되도록 함
        handler_to_use = (
            self._proxy if (self._use_proxy and self._proxy) else self._handler
        )
        task = ScheduledTask(
            name=self._name,
            handler=handler_to_use,
            trigger=trigger,
            args=args,
            kwargs=kwargs or {},
            instance=self._instance if not (self._use_proxy and self._proxy) else None,
        )

        # 백엔드에 등록
        return backend.schedule(task)


class TaskDescriptor[T, **P, R](ProxyableDescriptor):
    """
    태스크 디스크립터

    클래스 속성 접근 시 BoundTask를 반환합니다.
    ProxyableDescriptor를 상속하여 Application에서 프록시 적용 가능.
    """

    def __init__(
        self,
        handler: Callable[Concatenate[T, P], R],
        element: TaskElement,
    ):
        self._handler = handler
        self._element = element
        functools.update_wrapper(self, handler)  # type:ignore

    def get_original_handler(self) -> Callable[Concatenate[T, P], R]:
        """ProxyableDescriptor: 원본 핸들러 반환"""
        return self._handler

    def apply_proxy(self, instance: Any, proxy: Any) -> BoundTask[T, P, R]:
        """ProxyableDescriptor: 프록시를 적용하고 BoundTask 반환"""
        bound_task = self.__get__(instance, type(instance))
        bound_task._proxy = proxy
        bound_task._use_proxy = True
        return bound_task

    @overload
    def __get__(self, instance: None, owner: type) -> TaskDescriptor[T, P, R]: ...

    @overload
    def __get__(self, instance: T, owner: type) -> BoundTask[T, P, R]: ...

    def __get__(
        self, instance: T | None, owner: type
    ) -> TaskDescriptor[T, P, R] | BoundTask[T, P, R]:
        if instance is None:
            return self

        # 인스턴스에서 백엔드 가져오기 시도
        backend = getattr(instance, "_task_backend", None)

        return BoundTask(
            handler=self._handler,
            instance=instance,
            backend=backend,
            element=self._element,
        )


@overload
def Task[T, **P, R](fn: Callable[Concatenate[T, P], R]) -> TaskDescriptor[T, P, R]: ...


@overload
def Task[T, **P, R](
    *,
    name: str | None = None,
    bind: bool = False,
    max_retries: int = 0,
    retry_delay: float = 1.0,
) -> Callable[[Callable[Concatenate[T, P], R]], TaskDescriptor[T, P, R]]: ...


def Task[T, **P, R](
    fn: Callable[Concatenate[T, P], R] | None = None,
    *,
    name: str | None = None,
    bind: bool = False,
    max_retries: int = 0,
    retry_delay: float = 1.0,
) -> (
    TaskDescriptor[T, P, R]
    | Callable[[Callable[Concatenate[T, P], R]], TaskDescriptor[T, P, R]]
):
    """
    메서드를 태스크로 정의

    Example:
        @Component
        class EmailService:
            @Task
            def send_email(self, to: str) -> str:
                return f"Sent to {to}"

            @Task(name="important-email", max_retries=3)
            def send_important_email(self, to: str) -> str:
                return f"Important: Sent to {to}"

    Args:
        name: 태스크 이름 (기본값: 메서드 이름)
        bind: True면 첫 번째 인자로 BoundTask 전달
        max_retries: 최대 재시도 횟수
        retry_delay: 재시도 간격 (초)
    """

    def decorator(fn: Callable[Concatenate[T, P], R]) -> TaskDescriptor[T, P, R]:
        element = TaskElement(
            name=name,  # None이면 레지스트리에서 ClassName.method_name 사용
            bind=bind,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        # HandlerContainer에 Element 추가
        container = HandlerContainer.get_or_create(fn)
        container.add_elements(element)

        return TaskDescriptor(fn, element)

    if fn is not None:
        return decorator(fn)
    return decorator


def is_task(fn: Callable) -> bool:
    """메서드가 @Task로 데코레이트되었는지 확인"""
    container = HandlerContainer.get_container(fn)
    if container is None:
        return False
    return container.has_element(TaskElement)


def get_task_element(fn: Callable) -> TaskElement | None:
    """메서드의 TaskElement를 반환"""
    container = HandlerContainer.get_container(fn)
    if container is None:
        return None
    return container.get_element(TaskElement)
