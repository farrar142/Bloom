"""tests.core 공통 fixture"""

import pytest

from bloom.core import reset_container_manager


@pytest.fixture(autouse=True)
def reset_manager():
    """각 테스트 전후로 ContainerManager 초기화"""
    reset_container_manager()
    yield
    reset_container_manager()
