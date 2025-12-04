"""@Component 데코레이터 테스트"""

import pytest

from bloom.core import (
    Component,
    Service,
    Repository,
    ScopeEnum,
    get_container_manager,
)


class TestComponentDecorator:
    """@Component 데코레이터 테스트"""

    def test_component_registers_to_manager(self):
        """@Component가 ContainerManager에 등록되는지"""

        @Component
        class SimpleService:
            pass

        manager = get_container_manager()
        container = manager.get_container(SimpleService)

        assert container is not None
        assert container.target is SimpleService
        assert container.scope == ScopeEnum.SINGLETON

    def test_component_with_scope(self):
        """@Component(scope=...) 스코프 지정"""

        @Component(scope=ScopeEnum.REQUEST)
        class RequestService:
            pass

        manager = get_container_manager()
        container = manager.get_container(RequestService)

        assert container is not None
        assert container.scope == ScopeEnum.REQUEST

    def test_component_analyzes_dependencies(self):
        """@Component가 필드 의존성을 분석하는지"""

        @Component
        class DependencyA:
            pass

        @Component
        class DependencyB:
            a: DependencyA

        manager = get_container_manager()
        container = manager.get_container(DependencyB)

        assert container is not None
        assert len(container.dependencies) == 1
        assert container.dependencies[0].field_name == "a"
        assert container.dependencies[0].field_type is DependencyA


class TestServiceRepositoryDecorators:
    """@Service, @Repository 별칭 데코레이터 테스트"""

    def test_service_is_component_alias(self):
        """@Service가 @Component와 동일하게 동작"""

        @Service
        class MyService:
            pass

        manager = get_container_manager()
        container = manager.get_container(MyService)

        assert container is not None
        assert container.scope == ScopeEnum.SINGLETON

    def test_repository_is_component_alias(self):
        """@Repository가 @Component와 동일하게 동작"""

        @Repository
        class MyRepository:
            pass

        manager = get_container_manager()
        container = manager.get_container(MyRepository)

        assert container is not None
