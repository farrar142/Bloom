"""데코레이터 테스트 - Component, Qualifier, Factory, Handler"""

import pytest
from bloom.core import (
    ComponentContainer,
    FactoryContainer,
    HandlerContainer,
)
from bloom.core.manager import ContainerManager

from .conftest import (
    Configuration,
    HandlerTestController,
    ExternalService,
    Repository,
    Service,
)


class TestComponent:
    """@Component 데코레이터 테스트"""

    def test_component_creates_container(self):
        """@Component가 컨테이너를 생성"""
        assert hasattr(Repository, "__container__")
        assert isinstance(getattr(Repository, "__container__"), ComponentContainer)

    def test_component_with_dependency(self):
        """의존성이 있는 컴포넌트"""
        container = getattr(Service, "__container__")
        deps = container.get_dependencies()
        assert Repository in deps


class TestQualifier:
    """@Qualifier 데코레이터 테스트"""

    def test_default_qualifier(self):
        """기본 qualifier는 'default'"""
        container = getattr(Repository, "__container__")
        assert container.get_qual_name() == "default"


class TestFactory:
    """@Factory 데코레이터 테스트"""

    def test_factory_creates_container(self):
        """@Factory가 FactoryContainer를 생성"""
        assert hasattr(Configuration.create_external_service, "__container__")
        container = Configuration.create_external_service.__container__
        assert isinstance(container, FactoryContainer)
        assert container.target is ExternalService

    def test_factory_with_dependencies(self):
        """의존성이 있는 팩토리"""
        container = Configuration.create_external_service.__container__
        deps = container.get_dependencies()
        assert Repository in deps


class TestHandler:
    """@Handler 데코레이터 테스트"""

    def test_handler_creates_container(self):
        """@Handler가 HandlerContainer를 생성"""
        assert hasattr(HandlerTestController.get_users, "__container__")
        container = HandlerTestController.get_users.__container__
        assert isinstance(container, HandlerContainer)
        assert container.handler_key == ("GET", "/users")

    def test_handler_with_exception_key(self):
        """예외 타입을 키로 사용"""
        container = HandlerTestController.handle_error.__container__
        assert container.handler_key is ValueError

    @pytest.mark.asyncio
    async def test_handler_callable(self, reset_container_manager):
        """HandlerContainer가 호출 가능 (비동기)"""
        manager = reset_container_manager

        # 컨테이너 등록
        manager.register_container(getattr(HandlerTestController, "__container__"))

        # 인스턴스 생성
        instance = HandlerTestController()
        manager.set_instance(HandlerTestController, instance)

        handler = HandlerTestController.do_something.__container__
        result = await handler()
        assert result == "done"
