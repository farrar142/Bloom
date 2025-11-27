"""ContainerManager 테스트"""

import pytest
from vessel.core import ComponentContainer
from vessel.core.manager import ContainerManager

from .conftest import Repository, Service


class TestContainerManager:
    """ContainerManager 테스트"""

    def test_register_and_get_container(self, reset_container_manager):
        """컨테이너 등록 및 조회"""
        manager = reset_container_manager
        container = ComponentContainer.get_or_create(Repository)
        manager.register_container(container)

        result = manager.get_container(Repository)
        assert result is container
        assert result.target is Repository

    def test_set_and_get_instance(self, reset_container_manager):
        """인스턴스 등록 및 조회"""
        manager = reset_container_manager
        instance = Repository()
        manager.set_instance(Repository, instance)

        result = manager.get_instance(Repository)
        assert result is instance

    def test_get_instance_not_found_raises(self, reset_container_manager):
        """존재하지 않는 인스턴스 조회시 예외"""
        manager = reset_container_manager

        class NotRegistered:
            pass

        with pytest.raises(Exception, match="not found"):
            manager.get_instance(NotRegistered)

    def test_get_instance_not_found_returns_none(self, reset_container_manager):
        """존재하지 않는 인스턴스 조회시 None 반환"""
        manager = reset_container_manager

        class NotRegistered:
            pass

        result = manager.get_instance(NotRegistered, raise_exception=False)
        assert result is None
