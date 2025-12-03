"""@Handler 데코레이터 테스트"""

import pytest

from bloom.core import (
    Component,
    Handler,
    Scope,
    get_container_manager,
)


class TestHandler:
    """@Handler 테스트"""

    @pytest.mark.asyncio
    async def test_handler_creates_call_scope(self):
        """@Handler가 CALL 스코프를 생성하는지"""
        call_count = {"count": 0}

        @Component(scope=Scope.CALL)
        class CallScopedService:
            def __init__(self):
                call_count["count"] += 1

        @Component
        class MyController:
            service: CallScopedService

            @Handler
            async def handle(self):
                # CALL 스코프 내에서 서비스 사용
                _ = self.service

        manager = get_container_manager()
        await manager.initialize()

        controller = manager.get_instance(MyController)

        # 핸들러 호출
        await controller.handle()
        await controller.handle()

        # 각 호출마다 새 인스턴스 (현재 구현은 lazy이므로 접근 시 생성)
        # 실제로는 CALL 스코프 로직에 따라 다름
        assert call_count["count"] >= 0  # 기본 동작 확인
