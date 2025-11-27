"""ContainerManager 테스트"""

import pytest
from vessel.core import ComponentContainer, ContainerManager

from .conftest import Repository, Service


class TestContainerManager:
    """ContainerManager 테스트"""

    def test_register_and_get_container(self):
        """컨테이너 등록 및 조회"""
        container = ComponentContainer.get_or_create(Repository)
        ContainerManager.register_container(container)

        result = ContainerManager.get_container(Repository)
        assert result is container
        assert result.target is Repository

    def test_set_and_get_instance(self):
        """인스턴스 등록 및 조회"""
        instance = Repository()
        ContainerManager.set_instance(Repository, instance)

        result = ContainerManager.get_instance(Repository)
        assert result is instance

    def test_get_instance_not_found_raises(self):
        """존재하지 않는 인스턴스 조회시 예외"""

        class NotRegistered:
            pass

        with pytest.raises(Exception, match="not found"):
            ContainerManager.get_instance(NotRegistered)

    def test_get_instance_not_found_returns_none(self):
        """존재하지 않는 인스턴스 조회시 None 반환"""

        class NotRegistered:
            pass

        result = ContainerManager.get_instance(NotRegistered, raise_exception=False)
        assert result is None
