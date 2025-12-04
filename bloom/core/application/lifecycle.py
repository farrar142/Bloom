"""bloom.core.application.lifecycle - 라이프사이클 관리

애플리케이션 초기화 및 종료를 담당합니다.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager
    from .queue import QueueManager


logger = logging.getLogger(__name__)


class LifecycleManager:
    """라이프사이클 관리자

    애플리케이션의 초기화 및 종료를 관리합니다.
    """

    def __init__(self, app_name: str):
        self._app_name = app_name
        self._is_ready = False

    @property
    def is_ready(self) -> bool:
        """초기화 완료 여부"""
        return self._is_ready

    async def startup(
        self,
        container_manager: "ContainerManager",
        queue_manager: "QueueManager",
        invalidate_asgi_cache: Any,
    ) -> None:
        """애플리케이션 초기화

        Args:
            container_manager: 컨테이너 관리자
            queue_manager: 큐 관리자
            invalidate_asgi_cache: ASGI 캐시 무효화 콜백
        """
        if self._is_ready:
            return

        # ContainerManager 초기화
        await container_manager.initialize()

        # TaskApp 초기화
        await queue_manager.initialize(container_manager)

        # @Task 메서드 자동 등록
        await queue_manager.register_task_methods(container_manager)

        # ASGI 앱 캐시 무효화
        invalidate_asgi_cache()

        self._is_ready = True
        logger.info(f"Application {self._app_name} is ready")

    async def shutdown(
        self,
        container_manager: "ContainerManager",
        queue_manager: "QueueManager",
    ) -> None:
        """애플리케이션 종료

        Args:
            container_manager: 컨테이너 관리자
            queue_manager: 큐 관리자
        """
        if not self._is_ready:
            return

        # ContainerManager 종료 (@PreDestroy 실행)
        await container_manager.shutdown()

        # TaskApp 연결 해제
        await queue_manager.disconnect()

        self._is_ready = False
        logger.info(f"Application {self._app_name} shutdown complete")

    def startup_sync(
        self,
        startup_coro: Any,
    ) -> None:
        """동기 초기화

        Args:
            startup_coro: 초기화 코루틴
        """
        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "이미 실행 중인 이벤트 루프가 있습니다. "
                "await application.ready_async()를 사용하세요."
            )
        except RuntimeError as e:
            if "no running event loop" in str(e):
                asyncio.run(startup_coro)
            else:
                raise

    def shutdown_sync(
        self,
        shutdown_coro: Any,
    ) -> None:
        """동기 종료

        Args:
            shutdown_coro: 종료 코루틴
        """
        if not self._is_ready:
            return
        asyncio.run(shutdown_coro)
