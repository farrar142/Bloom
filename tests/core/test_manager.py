"""ContainerManager 테스트"""

import pytest

from bloom.core import (
    Component,
    Scope,
    get_container_manager,
)


class TestContainerManager:
    """ContainerManager 테스트"""

    @pytest.mark.asyncio
    async def test_singleton_same_instance(self):
        """SINGLETON 스코프가 동일 인스턴스 반환"""

        @Component
        class SingletonService:
            pass

        manager = get_container_manager()
        await manager.initialize()

        instance1 = manager.get_instance(SingletonService)
        instance2 = manager.get_instance(SingletonService)

        assert instance1 is instance2

    @pytest.mark.asyncio
    async def test_dependency_injection(self):
        """의존성 주입이 정상 동작"""

        @Component
        class DependencyA:
            pass

        @Component
        class DependencyB:
            a: DependencyA

        manager = get_container_manager()
        await manager.initialize()

        instance = manager.get_instance(DependencyB)

        assert instance is not None
        # LazyProxy이므로 실제 인스턴스 확인
        assert instance.a is not None

    @pytest.mark.asyncio
    async def test_deep_dependency_chain(self):
        """깊은 의존성 체인 해결"""

        @Component
        class Level1:
            pass

        @Component
        class Level2:
            level1: Level1

        @Component
        class Level3:
            level2: Level2

        manager = get_container_manager()
        await manager.initialize()

        instance = manager.get_instance(Level3)

        assert instance.level2 is not None
        assert instance.level2.level1 is not None
