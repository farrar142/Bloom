"""bloom.core.application.queue - 태스크 큐 관리

TaskApp 초기화 및 관리를 담당합니다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bloom.task import TaskApp
    from bloom.task.broker import TaskBroker
    from bloom.task.backend import TaskBackend
    from bloom.core.manager import ContainerManager


logger = logging.getLogger(__name__)


class QueueManager:
    """태스크 큐 관리자

    TaskApp 생성, 초기화, 태스크 등록을 관리합니다.
    """

    def __init__(self, app_name: str):
        self._app_name = app_name
        self._queue: "TaskApp | None" = None

    @property
    def queue(self) -> "TaskApp | None":
        """TaskApp 인스턴스"""
        return self._queue

    def get_or_create_queue(self, container_manager: "ContainerManager") -> "TaskApp":
        """태스크 큐 앱 가져오기 또는 생성

        Args:
            container_manager: 컨테이너 관리자

        Returns:
            TaskApp 인스턴스
        """
        if self._queue is not None:
            return self._queue

        from bloom.task import TaskApp
        from bloom.task.broker import TaskBroker
        from bloom.task.backend import TaskBackend

        # 이벤트 루프가 없는 경우에만 동기적으로 DI 조회
        try:
            asyncio.get_running_loop()
            broker = None
            backend = None
        except RuntimeError:
            broker = container_manager.get_instance(TaskBroker, required=False)
            backend = container_manager.get_instance(TaskBackend, required=False)

        self._queue = TaskApp(
            self._app_name,
            broker=broker,
            backend=backend,
        )

        if broker:
            logger.info(f"TaskApp created with broker: {type(broker).__name__}")
        if backend:
            logger.info(f"TaskApp created with backend: {type(backend).__name__}")

        return self._queue

    def configure(
        self,
        *,
        broker: "TaskBroker | None" = None,
        backend: "TaskBackend | None" = None,
        name: str | None = None,
    ) -> None:
        """태스크 큐 설정

        Args:
            broker: 메시지 브로커
            backend: 결과 백엔드
            name: TaskApp 이름
        """
        from bloom.task import TaskApp

        self._queue = TaskApp(
            name or self._app_name,
            broker=broker,
            backend=backend,
        )

        logger.info(f"Configured TaskApp for {self._app_name}")

    async def initialize(self, container_manager: "ContainerManager") -> None:
        """TaskApp 초기화 - DI에서 Broker/Backend 가져오기

        Args:
            container_manager: 컨테이너 관리자
        """
        if self._queue is not None:
            return

        from bloom.task import TaskApp
        from bloom.task.broker import TaskBroker
        from bloom.task.backend import TaskBackend

        broker = await container_manager.get_instance_async(TaskBroker, required=False)
        backend = await container_manager.get_instance_async(
            TaskBackend, required=False
        )

        self._queue = TaskApp(
            self._app_name,
            broker=broker,
            backend=backend,
        )

        if broker:
            logger.info(f"TaskApp created with broker: {type(broker).__name__}")
        if backend:
            logger.info(f"TaskApp created with backend: {type(backend).__name__}")

    async def register_task_methods(
        self, container_manager: "ContainerManager"
    ) -> None:
        """@Task 메서드들을 TaskApp에 등록

        Args:
            container_manager: 컨테이너 관리자
        """
        from bloom.task.decorators import scan_task_methods

        if self._queue is None:
            return

        for container in container_manager.get_all_containers():
            try:
                instance = container_manager.get_instance(
                    container.target, required=False
                )
                if instance is None:
                    continue
            except Exception:
                continue

            task_methods = scan_task_methods(instance)
            if not task_methods:
                continue

            for method_name, bound_method, task_model in task_methods:
                task_name = task_model.name or (
                    f"{instance.__class__.__module__}."
                    f"{instance.__class__.__name__}.{method_name}"
                )

                bound_task = self._queue.register_task(
                    name=task_name,
                    func=bound_method,
                    queue=task_model.queue,
                    retry=task_model.retry,
                    retry_delay=task_model.retry_delay,
                    timeout=task_model.timeout,
                    priority=task_model.priority,
                )

                setattr(instance, method_name, bound_task)
                logger.info(f"Registered task: {task_name}")

    async def connect(self) -> None:
        """브로커/백엔드 연결"""
        if self._queue and self._queue.broker:
            await self._queue.broker.connect()
        if self._queue and self._queue.backend:
            await self._queue.backend.connect()

    async def disconnect(self) -> None:
        """브로커/백엔드 연결 해제"""
        if self._queue:
            if self._queue.broker:
                await self._queue.broker.disconnect()
            if self._queue.backend:
                await self._queue.backend.disconnect()
