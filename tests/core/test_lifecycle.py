"""@PostConstruct, @PreDestroy, AutoClosable 라이프사이클 테스트"""

import pytest

from bloom.core import (
    Component,
    PostConstruct,
    PreDestroy,
    AutoClosable,
    get_container_manager,
)


class TestLifecycle:
    """@PostConstruct, @PreDestroy, AutoClosable 테스트"""

    @pytest.mark.asyncio
    async def test_post_construct_called(self):
        """@PostConstruct가 초기화 시 호출되는지"""
        called = {"init": False}

        @Component
        class ServiceWithInit:
            @PostConstruct
            async def init(self):
                called["init"] = True

        manager = get_container_manager()
        await manager.initialize()

        assert called["init"] is True

    @pytest.mark.asyncio
    async def test_pre_destroy_called(self):
        """@PreDestroy가 종료 시 호출되는지"""
        called = {"destroy": False}

        @Component
        class ServiceWithDestroy:
            @PreDestroy
            async def cleanup(self):
                called["destroy"] = True

        manager = get_container_manager()
        await manager.initialize()
        await manager.shutdown()

        assert called["destroy"] is True

    @pytest.mark.asyncio
    async def test_auto_closable(self):
        """AutoClosable.close()가 종료 시 호출되는지"""
        called = {"close": False}

        @Component
        class ResourceService(AutoClosable):
            async def close(self):
                called["close"] = True

        manager = get_container_manager()
        await manager.initialize()
        await manager.shutdown()

        assert called["close"] is True
