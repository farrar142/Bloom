"""bloom Application - 최소 버전 (core 재설계 전)"""

import asyncio
from typing import TYPE_CHECKING, Any
from pathlib import Path


class Application:
    """
    bloom 애플리케이션 진입점 (core 재설계 전 최소 버전)

    사용 예시:
        app = Application("my_app")
        # TODO: core 모듈 재설계 후 구현
    """

    def __init__(self, name: str):
        self.name = name
        self._is_ready = False
        self._scanned_modules: list[Any] = []

    def scan(self, *modules: object) -> "Application":
        """모듈들을 스캔하여 컴포넌트 수집"""
        # TODO: core 재설계 후 구현
        for module in modules:
            self._scanned_modules.append(module)
        return self

    async def ready_async(self, parallel: bool = False) -> "Application":
        """애플리케이션 초기화 완료 (비동기)"""
        if self._is_ready:
            return self

        # TODO: core 재설계 후 구현
        # - ContainerManager 초기화
        # - 의존성 주입
        # - @PostConstruct 실행

        self._is_ready = True
        return self

    def ready(self) -> "Application":
        """애플리케이션 초기화 완료 (동기)"""
        return asyncio.run(self.ready_async())

    async def shutdown_async(self, wait: bool = True) -> "Application":
        """애플리케이션 비동기 종료"""
        if not self._is_ready:
            return self

        # TODO: core 재설계 후 구현
        # - @PreDestroy 실행

        self._is_ready = False
        return self

    def shutdown(self) -> "Application":
        """애플리케이션 종료 (동기)"""
        if not self._is_ready:
            return self
        asyncio.run(self.shutdown_async())
        return self
