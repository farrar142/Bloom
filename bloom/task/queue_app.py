"""Queue Worker Application

uvicorn이 ASGI 앱을 실행하는 것처럼, bloom worker가 이 Queue App을 실행합니다.

사용 예시:
    # main.py
    from bloom import Application, Component
    from bloom.task import Task, DistributedTaskBackend, RedisBroker
    from bloom.core.decorators import Factory

    @Component
    class EmailService:
        @Task
        def send_email(self, to: str, subject: str) -> str:
            return f"Sent to {to}"

    @Component
    class TaskConfig:
        @Factory
        def task_backend(self) -> DistributedTaskBackend:
            broker = RedisBroker("redis://localhost:6379/0")
            return DistributedTaskBackend(broker)

    app = Application("myapp").scan(__name__).ready()

    # 웹 서버 실행
    # uvicorn main:app.asgi

    # 워커 실행
    # bloom worker main:app.queue
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from bloom.log import get_logger

if TYPE_CHECKING:
    from bloom.application import Application
    from .distributed import DistributedTaskBackend
    from .registry import TaskRegistry

logger = get_logger(__name__)


class QueueApplication:
    """
    Queue Worker Application

    uvicorn의 ASGIApplication처럼, bloom worker로 실행되는 워커 애플리케이션입니다.
    DistributedTaskBackend의 워커 모드를 관리합니다.

    사용 예시:
        # main.py
        app = Application("myapp").scan(__name__).ready()

        # 커맨드라인
        bloom worker main:app.queue --concurrency 4

        # 또는 직접 실행
        asyncio.run(app.queue.run())
    """

    def __init__(
        self,
        application: "Application",
        backend: "DistributedTaskBackend | None" = None,
        concurrency: int = 4,
    ):
        self.application = application
        self._backend = backend
        self._concurrency = concurrency
        self._is_running = False
        self._shutdown_event: asyncio.Event | None = None

        # 라이프사이클 콜백
        self._on_startup: list[Callable[[], Coroutine[Any, Any, None] | None]] = []
        self._on_shutdown: list[Callable[[], Coroutine[Any, Any, None] | None]] = []

    @property
    def backend(self) -> "DistributedTaskBackend | None":
        """DistributedTaskBackend 인스턴스 (lazy 조회)"""
        if self._backend is None:
            from .distributed import DistributedTaskBackend

            # ContainerManager에서 DistributedTaskBackend 조회
            instances = self.application.manager.get_instances(DistributedTaskBackend)
            if instances:
                self._backend = instances[0]
        return self._backend

    @property
    def registry(self) -> "TaskRegistry | None":
        """TaskRegistry 인스턴스 (lazy 조회)"""
        if self.backend is not None:
            return self.backend._registry
        return None

    def on_startup(
        self,
        callback: Callable[[], Coroutine[Any, Any, None] | None],
    ) -> "QueueApplication":
        """시작 시 콜백 등록"""
        self._on_startup.append(callback)
        return self

    def on_shutdown(
        self,
        callback: Callable[[], Coroutine[Any, Any, None] | None],
    ) -> "QueueApplication":
        """종료 시 콜백 등록"""
        self._on_shutdown.append(callback)
        return self

    async def _invoke_callbacks(
        self,
        callbacks: list[Callable[[], Coroutine[Any, Any, None] | None]],
    ) -> None:
        """콜백 리스트 실행"""
        for callback in callbacks:
            result = callback()
            if asyncio.iscoroutine(result):
                await result

    async def startup(self) -> None:
        """워커 시작 처리"""
        if self.backend is None:
            raise RuntimeError(
                "DistributedTaskBackend가 등록되지 않았습니다. "
                "@Factory로 DistributedTaskBackend를 생성하세요."
            )

        # 브로커 연결
        await self.backend.start()

        # 레지스트리 초기화 (없으면 생성) 및 태스크 등록
        from .registry import TaskRegistry

        if self.backend._registry is None:
            self.backend._registry = TaskRegistry()
        self.backend._registry.scan(self.application.manager)

        # 사용자 콜백 실행
        await self._invoke_callbacks(self._on_startup)

        self._is_running = True
        logger.info(f"Starting worker with concurrency={self._concurrency}")
        logger.info("Registered tasks:")
        if self.registry:
            for name in self.registry.names():
                logger.info(f"  - {name}")

    async def shutdown(self) -> None:
        """워커 종료 처리"""
        self._is_running = False

        # 워커 중지
        if self.backend is not None:
            await self.backend.shutdown()

        # 사용자 콜백 실행
        await self._invoke_callbacks(self._on_shutdown)

        # Application 종료
        await self.application.shutdown_async()

        logger.info("Shutdown complete")

    async def run(self) -> None:
        """
        워커 메인 루프

        블로킹으로 실행되며, SIGINT/SIGTERM 시그널로 종료됩니다.

        사용 예시:
            asyncio.run(app.queue.run())
        """
        # 시그널 핸들러 설정
        self._shutdown_event = asyncio.Event()

        loop = asyncio.get_running_loop()

        def signal_handler():
            logger.info("Received shutdown signal...")
            if self._shutdown_event is not None:
                self._shutdown_event.set()

        # Windows에서는 SIGTERM이 없음
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                # Windows: signal.signal 사용
                signal.signal(sig, lambda s, f: signal_handler())

        try:
            # 시작
            await self.startup()

            # 워커 시작 (백그라운드) - start_worker가 내부에서 레지스트리 설정
            if self.backend is not None:
                await self.backend.start_worker(
                    manager=self.application.manager,
                    worker_count=self._concurrency,
                )

            # 종료 시그널 대기
            await self._shutdown_event.wait()

        finally:
            # 종료 처리
            await self.shutdown()

    def run_sync(self) -> None:
        """
        동기 방식으로 워커 실행

        asyncio.run()을 내부적으로 호출합니다.

        사용 예시:
            app.queue.run_sync()
        """
        try:
            asyncio.run(self.run())
        except KeyboardInterrupt:
            pass  # Ctrl+C는 정상 종료
