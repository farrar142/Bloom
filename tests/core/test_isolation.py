"""테스트 격리 검증"""

import pytest

from bloom.core import (
    Component,
    get_container_manager,
)


class TestIsolation:
    """테스트 격리 확인 - 각 테스트가 독립적인 상태를 가지는지"""

    def test_isolation_first(self):
        """첫 번째 테스트 - 컴포넌트 등록"""

        @Component
        class IsolatedServiceA:
            pass

        manager = get_container_manager()
        assert manager.get_container(IsolatedServiceA) is not None

    def test_isolation_second(self):
        """두 번째 테스트 - 이전 테스트의 컴포넌트가 없어야 함"""

        @Component
        class IsolatedServiceB:
            pass

        manager = get_container_manager()

        # 이전 테스트의 컴포넌트가 없어야 함
        # IsolatedServiceA는 이 테스트에서 정의되지 않았으므로 없어야 함
        assert manager.get_container(IsolatedServiceB) is not None

        # containers 개수로 간접 확인 (새로운 매니저는 B만 가짐)
        assert len(manager._containers) == 1

    def test_isolation_third(self):
        """세 번째 테스트 - 완전히 새로운 상태"""
        manager = get_container_manager()

        # 이전 테스트들의 컴포넌트가 전혀 없어야 함
        assert len(manager._containers) == 0
