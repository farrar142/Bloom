"""@Async - 동기 메서드를 별도 스레드에서 실행하여 AsyncTask를 반환"""

import concurrent.futures
import threading
from typing import Any, TypeVar, Callable

from ...container import HandlerContainer
from ...container.element import Element

T = TypeVar("T")


class AsyncTask[T]:
    """
    비동기 작업을 나타내는 객체.

    Thread와 유사하게 join(), result() 등의 메서드를 제공합니다.

    Example:
        @Component
        class HeavyService:
            @Async
            @Handler
            def blocking_io(self) -> str:
                time.sleep(1)
                return "done"

        # 사용
        task = service.blocking_io()  # 즉시 반환 (AsyncTask)
        task.join()                    # 완료 대기
        result = task.result()         # 결과 조회

        # 또는
        result = service.blocking_io().result()  # 완료까지 대기 후 결과 반환
    """

    def __init__(
        self,
        future: concurrent.futures.Future[T],
        executor: concurrent.futures.ThreadPoolExecutor | None = None,
    ):
        self._future = future
        self._executor = executor

    @property
    def future(self) -> concurrent.futures.Future[T]:
        """내부 Future 객체 반환"""
        return self._future

    def join(self, timeout: float | None = None) -> "AsyncTask[T]":
        """
        작업 완료를 대기합니다.

        Args:
            timeout: 대기 시간 (초). None이면 무한 대기

        Returns:
            self (메서드 체이닝 지원)

        Raises:
            TimeoutError: timeout 초과 시
        """
        try:
            self._future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Task did not complete within {timeout} seconds")
        return self

    def result(self, timeout: float | None = None) -> T:
        """
        작업 결과를 반환합니다. 완료될 때까지 대기합니다.

        Args:
            timeout: 대기 시간 (초). None이면 무한 대기

        Returns:
            작업 결과

        Raises:
            TimeoutError: timeout 초과 시
            Exception: 작업 중 발생한 예외
        """
        try:
            return self._future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Task did not complete within {timeout} seconds")

    def exception(self, timeout: float | None = None) -> BaseException | None:
        """
        작업 중 발생한 예외를 반환합니다.

        Args:
            timeout: 대기 시간 (초)

        Returns:
            예외 객체 또는 None (정상 완료 시)
        """
        try:
            return self._future.exception(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Task did not complete within {timeout} seconds")

    def is_done(self) -> bool:
        """작업이 완료되었는지 확인 (성공/실패 무관)"""
        return self._future.done()

    def is_running(self) -> bool:
        """작업이 현재 실행 중인지 확인"""
        return self._future.running()

    def cancel(self) -> bool:
        """
        작업 취소를 시도합니다.

        Returns:
            True: 취소 성공
            False: 이미 실행 중이거나 완료됨
        """
        return self._future.cancel()

    def is_cancelled(self) -> bool:
        """작업이 취소되었는지 확인"""
        return self._future.cancelled()

    def add_done_callback(self, fn: Callable[["AsyncTask[T]"], Any]) -> "AsyncTask[T]":
        """
        작업 완료 시 호출될 콜백을 등록합니다.

        Args:
            fn: 콜백 함수 (AsyncTask를 인자로 받음)

        Returns:
            self (메서드 체이닝 지원)
        """

        def wrapper(future: concurrent.futures.Future[T]) -> None:
            fn(self)

        self._future.add_done_callback(wrapper)
        return self

    def __repr__(self) -> str:
        status = (
            "cancelled"
            if self.is_cancelled()
            else (
                "running"
                if self.is_running()
                else "done" if self.is_done() else "pending"
            )
        )
        return f"<AsyncTask status={status}>"


class AsyncElement(Element):
    """
    @Async 데코레이터가 적용되었음을 나타내는 마커 Element
    """

    pass


# 기본 공유 executor (모듈 레벨)
_default_executor: concurrent.futures.ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def get_default_executor() -> concurrent.futures.ThreadPoolExecutor:
    """기본 ThreadPoolExecutor 반환 (lazy 생성)"""
    global _default_executor
    if _default_executor is None:
        with _executor_lock:
            if _default_executor is None:
                _default_executor = concurrent.futures.ThreadPoolExecutor(
                    thread_name_prefix="bloom-async"
                )
    return _default_executor


class AsyncHandlerContainer[**P, R](HandlerContainer[P, R]):
    """
    @Async 전용 핸들러 컨테이너

    @Handler와는 별개의 컨테이너로, 수평적으로 충돌합니다.
    실제 AsyncTask 반환은 AsyncMethodAdvice가 담당합니다.
    """

    pass


# === @Async 데코레이터 ===


def Async[**P, R](func: Callable[P, R]) -> Callable[P, AsyncTask[R]]:
    """
    동기 메서드를 별도 스레드에서 실행하여 AsyncTask를 반환하도록 변환합니다.

    I/O 바운드 동기 작업(예: 동기 DB 호출, 파일 I/O)을
    논블로킹으로 실행할 수 있습니다.

    Example:
        @Component
        class HeavyService:
            @Async
            def blocking_io(self) -> str:
                time.sleep(1)  # 블로킹 I/O
                return "done"

        # 사용법 1: join 후 결과
        task = service.blocking_io()
        task.join()
        result = task.result()

        # 사용법 2: 바로 결과 (블로킹)
        result = service.blocking_io().result()

        # 사용법 3: 여러 작업 동시 실행
        task1 = service.blocking_io()
        task2 = service.blocking_io()
        task1.join()
        task2.join()

    Note:
        - @Async만 붙이면 됩니다 (@Handler 불필요)
        - 동기 메서드만 변환됩니다 (이미 async def인 경우 무시)
        - executor는 AsyncMethodAdvice 생성 시 지정합니다
    """
    container = AsyncHandlerContainer.get_or_create(func)
    container.add_elements(AsyncElement())
    return func  # type: ignore


# === AsyncMethodAdvice ===

from ..base import MethodAdvice
from ..context import InvocationContext


class AsyncMethodAdvice(MethodAdvice):
    """
    @Async가 적용된 동기 메서드를 ThreadPool에서 실행하고 AsyncTask를 반환하는 Advice

    이 Advice는 AsyncHandlerContainer에 적용되며,
    invoke_sync에서 호출을 ThreadPoolExecutor에 제출하고 AsyncTask를 반환합니다.

    Example:
        # 기본 executor 사용
        registry.register(AsyncMethodAdvice())

        # 커스텀 executor 사용
        custom_executor = ThreadPoolExecutor(max_workers=10)
        registry.register(AsyncMethodAdvice(executor=custom_executor))
    """

    def __init__(
        self, executor: concurrent.futures.ThreadPoolExecutor | None = None
    ) -> None:
        super().__init__()
        self._executor = executor

    @property
    def executor(self) -> concurrent.futures.ThreadPoolExecutor:
        return self._executor or get_default_executor()

    def supports(self, container: HandlerContainer) -> bool:
        """컨테이너의 메타데이터(AsyncElement) 존재 여부로 @Async 적용 여부를 판단합니다."""
        # 설계 철학: 수평적 컨테이너 타입 비교 대신 컨테이너의 Element(metadata)를 기준으로 판단
        return container.has_element(AsyncElement)

    def invoke_sync(
        self,
        context: InvocationContext,
        proceed: Callable[[], Any],
    ) -> AsyncTask[Any]:
        """
        동기 호출을 ThreadPool에 제출하고 AsyncTask를 반환합니다.

        Args:
            context: 호출 컨텍스트
            proceed: 나머지 Advice 체인 + 핸들러를 실행하는 함수

        Returns:
            AsyncTask: 비동기 작업 객체
        """
        future = self.executor.submit(proceed)
        return AsyncTask(future, self.executor)
