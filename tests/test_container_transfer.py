"""
Container 흡수/전이 시스템 테스트

@Scoped와 다른 컨테이너 데코레이터의 조합을 테스트합니다.
"""

import pytest
from bloom.core.container import (
    Container,
    HandlerContainer,
    ContainerTransferError,
)
from bloom.core.container.factory import FactoryContainer
from bloom.core.container.manager import get_container_registry
from bloom.core.container.scope import Scope
from bloom.core.decorators import (
    Scoped,
    Factory,
    Handler,
    Service,
    Component,
    Configuration,
)


# 테스트 전용 타입 클래스 (str 등 내장 타입 대신 사용하여 테스트 격리)
class TestResult1:
    """테스트용 반환 타입 1"""

    pass


class TestResult2:
    """테스트용 반환 타입 2"""

    pass


class TestResult3:
    """테스트용 반환 타입 3"""

    pass


class TestResult4:
    """테스트용 반환 타입 4"""

    pass


class TestResult5:
    """테스트용 반환 타입 5"""

    pass


class TestResult6:
    """테스트용 반환 타입 6"""

    pass


class TestHandlerResult:
    """Handler 테스트용 반환 타입"""

    pass


class TestPlainFactory:
    """Plain factory 테스트용 반환 타입"""

    pass


class TestContainerTransferRules:
    """컨테이너 흡수/전이 규칙 테스트"""

    def test_container_can_transfer_to_subclass(self):
        """Container -> HandlerContainer 전이 가능"""
        container = Container(str, "id1")
        assert container.can_transfer_to(HandlerContainer)

    def test_container_can_transfer_to_factory_subclass(self):
        """Container -> FactoryContainer 전이 가능 (subclass이므로)"""
        container = Container(str, "id1")
        # FactoryContainer도 Container의 subclass이므로 전이 가능
        assert container.can_transfer_to(FactoryContainer)

    def test_subclass_cannot_transfer_to_superclass(self):
        """HandlerContainer -> Container 전이 불가 (반대로 흡수해야 함)"""

        def test_func(self):
            return

        handler_container = HandlerContainer(test_func, "id1")
        assert not handler_container.can_transfer_to(Container)

    def test_subclass_can_absorb_superclass(self):
        """HandlerContainer가 Container를 흡수 가능"""

        def test_func(self):
            return

        handler_container = HandlerContainer(test_func, "id1")
        container = Container(str, "id2")
        assert handler_container.can_absorb_from(container)

    def test_superclass_cannot_absorb_subclass(self):
        """Container가 HandlerContainer를 흡수 불가"""

        def test_func(self):
            return

        container = Container(str, "id1")
        handler_container = HandlerContainer(test_func, "id2")
        assert not container.can_absorb_from(handler_container)

    def test_unrelated_cannot_absorb(self):
        """HandlerContainer와 FactoryContainer는 서로 흡수 불가"""

        def test_func(self):
            return

        handler = HandlerContainer(test_func, "id1")

        # FactoryContainer는 추가 파라미터가 필요해서 직접 생성
        def factory_func() -> TestResult1:
            return TestResult1()

        factory = FactoryContainer(factory_func, "id2", TestResult1, {}, False)

        assert not handler.can_absorb_from(factory)
        assert not factory.can_absorb_from(handler)


class TestScopedDecoratorOrder:
    """@Scoped 데코레이터 순서 테스트"""

    def test_scoped_before_factory(self):
        """@Scoped 먼저, @Factory 나중 - Factory가 Container 흡수"""

        @Configuration
        class AppConfig:
            @Scoped(Scope.CALL)
            @Factory
            def scoped_before_factory(self) -> TestResult2:
                return TestResult2()

        registry = get_container_registry()
        component_id = AppConfig.scoped_before_factory.__component_id__
        container = registry[AppConfig.scoped_before_factory][component_id]

        # FactoryContainer여야 함
        assert isinstance(container, FactoryContainer)
        # scope element가 유지되어야 함
        assert container.scope == Scope.CALL

    def test_factory_before_scoped(self):
        """@Factory 먼저, @Scoped 나중 - scope element 추가"""

        @Configuration
        class AppConfig:
            @Factory
            @Scoped(Scope.REQUEST)
            def factory_before_scoped(self) -> int:
                return 42

        registry = get_container_registry()
        component_id = AppConfig.factory_before_scoped.__component_id__
        container = registry[AppConfig.factory_before_scoped][component_id]

        # FactoryContainer여야 함
        assert isinstance(container, FactoryContainer)
        # scope element가 있어야 함
        assert container.scope == Scope.REQUEST

    def test_scoped_before_handler(self):
        """@Scoped 먼저, @Handler 나중"""

        class TestService:
            @Scoped(Scope.CALL)
            @Handler
            def scoped_handler(self) -> TestHandlerResult:
                return TestHandlerResult()

        registry = get_container_registry()
        component_id = TestService.scoped_handler.__component_id__
        container = registry[TestService.scoped_handler][component_id]

        # HandlerContainer여야 함
        assert isinstance(container, HandlerContainer)
        # scope element가 유지되어야 함
        assert container.scope == Scope.CALL

    def test_scoped_before_component(self):
        """@Scoped 먼저, @Component 나중"""

        @Scoped(Scope.REQUEST)
        @Component
        class ScopedComponent:
            pass

        registry = get_container_registry()
        component_id = ScopedComponent.__component_id__  # type:ignore
        container = registry[ScopedComponent][component_id]

        # Container여야 함 (Component는 기본 Container)
        assert type(container) == Container
        # scope element가 있어야 함
        assert container.scope == Scope.REQUEST

    def test_component_before_scoped(self):
        """@Component 먼저, @Scoped 나중"""

        @Component
        @Scoped(Scope.CALL)
        class ComponentBeforeScoped:
            pass

        registry = get_container_registry()
        component_id = ComponentBeforeScoped.__component_id__  # type:ignore
        container = registry[ComponentBeforeScoped][component_id]

        assert container.scope == Scope.CALL


class TestIncompatibleContainerError:
    """호환 불가능한 컨테이너 조합 에러 테스트"""

    def test_handler_factory_conflict_raises_error(self):
        """HandlerContainer와 FactoryContainer 충돌 시 에러"""
        # 이 케이스는 실제로 발생하기 어려움
        # (Factory와 Handler는 다른 상황에서 사용됨)
        # 하지만 수동으로 테스트 가능

        def test_func(self) -> TestResult3:
            return TestResult3()

        # 먼저 HandlerContainer로 등록
        handler = HandlerContainer.register(test_func)

        # 같은 함수를 FactoryContainer로 등록 시도하면 에러
        with pytest.raises(ContainerTransferError):
            FactoryContainer.register(test_func, TestResult3, {}, False)


class TestElementAbsorption:
    """Element 흡수 테스트"""

    def test_elements_absorbed_correctly(self):
        """Container의 elements가 흡수될 때 유지됨"""

        @Configuration
        class AppConfig:
            @Scoped(Scope.CALL)  # scope element 추가
            @Factory
            def test_factory(self) -> TestResult4:
                return TestResult4()

        registry = get_container_registry()
        component_id = AppConfig.test_factory.__component_id__
        container = registry[AppConfig.test_factory][component_id]

        # scope element가 존재해야 함
        assert container.get_element("scope") == Scope.CALL

    def test_multiple_elements_absorbed(self):
        """여러 elements가 모두 흡수됨"""

        # 수동으로 여러 element 추가 테스트
        class TestClass:
            pass

        container1 = Container.register(TestClass)
        container1.add_element("key1", "value1")
        container1.add_element("key2", "value2")
        container1.add_element("scope", Scope.CALL)

        # Container가 이미 있으므로 그대로 반환
        container2 = Container.register(TestClass)

        assert container1 is container2
        assert container2.get_element("key1") == "value1"
        assert container2.get_element("key2") == "value2"
        assert container2.scope == Scope.CALL


class TestDefaultScopeWhenNoScoped:
    """@Scoped 없이 사용 시 기본 SINGLETON 스코프"""

    def test_factory_default_singleton(self):
        """@Factory만 사용 시 SINGLETON"""

        @Configuration
        class AppConfig:
            @Factory
            def plain_factory(self) -> TestPlainFactory:
                return TestPlainFactory()

        registry = get_container_registry()
        component_id = AppConfig.plain_factory.__component_id__
        container = registry[AppConfig.plain_factory][component_id]

        assert container.scope == Scope.SINGLETON

    def test_component_default_singleton(self):
        """@Component만 사용 시 SINGLETON"""

        @Component
        class PlainComponent:
            pass

        registry = get_container_registry()
        component_id = PlainComponent.__component_id__  # type:ignore
        container = registry[PlainComponent][component_id]

        assert container.scope == Scope.SINGLETON

    def test_service_default_singleton(self):
        """@Service만 사용 시 SINGLETON"""

        @Service
        class PlainService:
            pass

        registry = get_container_registry()
        component_id = PlainService.__component_id__  # type:ignore
        container = registry[PlainService][component_id]

        assert container.scope == Scope.SINGLETON
