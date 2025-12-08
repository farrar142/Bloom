"""Factory 데코레이터 통합 테스트

conftest.py에 등록된 Factory 컴포넌트들을 사용하여 테스트합니다.
"""

import pytest

from bloom.core import FactoryContainer, get_container_manager
from bloom.core.container.manager import containers

# conftest.py에서 등록된 클래스들 import
from tests.conftest import (
    User,
    Config,
    UserFactory,
    ConfigFactory,
    UserEnhancerFactory,
    UserProcessorFactory,
    EmailService,
    # 복잡한 체인 테스트용
    Order,
    Product,
    Report,
    LoggingService,
    NotificationService,
    DiscountService,
    ValidationComponent,
    OrderFactory,
    ProductFactory,
    ReportFactory,
    OrderProcessingComponent,
)


def get_factory_container[T](factory_cls: type[T]) -> FactoryContainer[T]:
    """Factory 클래스에서 FactoryContainer를 가져오는 헬퍼 함수"""
    manager = get_container_manager()
    c = manager.get_container(factory_cls)
    assert c is not None, f"Container not found for {factory_cls.__name__}"
    container = manager.get_container_by_container_type_and_id(
        FactoryContainer, c.component_id
    )
    assert container is not None, f"FactoryContainer not found for {factory_cls.__name__}"
    return container


class TestFactoryRegistration:
    """Factory 등록 테스트"""

    def test_factory_registration(self):
        """Factory 클래스 등록 테스트"""
        assert hasattr(UserFactory, "__component_id__")
        assert UserFactory in containers

    def test_factory_container_type(self):
        """FactoryContainer 타입 확인"""
        container = get_factory_container(UserFactory)
        assert isinstance(container, FactoryContainer)

    def test_all_factories_registered(self):
        """모든 Factory가 등록되어 있는지 확인"""
        assert UserFactory in containers
        assert ConfigFactory in containers
        assert UserEnhancerFactory in containers
        assert UserProcessorFactory in containers


class TestFactoryMethodAnalysis:
    """Factory 메서드 분석 테스트"""

    def test_creator_method_detection(self):
        """Creator 메서드 감지 테스트"""
        container = get_factory_container(UserFactory)

        creator_methods = container.get_creator_methods(User)
        assert "create" in creator_methods
        assert "create_async" in creator_methods
        assert "create_and_notify" in creator_methods

    def test_modifier_method_detection(self):
        """Modifier 메서드 감지 테스트"""
        container = get_factory_container(UserFactory)

        modifier_methods = container.get_modifier_methods(User)
        assert "enhance" in modifier_methods
        assert "process_async" in modifier_methods

    def test_mixed_creator_and_modifier(self):
        """Creator와 Modifier 혼합 테스트"""
        container = get_factory_container(UserFactory)

        assert User in container.get_all_creator_types()
        assert User in container.get_all_modifier_types()

    def test_config_factory_methods(self):
        """ConfigFactory 메서드 분석 테스트"""
        container = get_factory_container(ConfigFactory)

        creator_methods = container.get_creator_methods(Config)
        modifier_methods = container.get_modifier_methods(Config)

        assert "create" in creator_methods
        assert "update" in modifier_methods


class TestFactoryExecution:
    """Factory 실행 테스트"""

    @pytest.mark.asyncio
    async def test_sync_creator_execution(self):
        """동기 Creator 실행 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(UserFactory)

        result = await container.create(
            User, "create", "Alice", email="alice@example.com"
        )
        assert isinstance(result, User)
        assert result.name == "Alice"
        assert result.email == "alice@example.com"

    @pytest.mark.asyncio
    async def test_async_creator_execution(self):
        """비동기 Creator 실행 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(UserFactory)

        result = await container.create(User, "create_async", "Bob")
        assert isinstance(result, User)
        assert result.name == "Bob"
        assert result.processed is True

    @pytest.mark.asyncio
    async def test_sync_modifier_execution(self):
        """동기 Modifier 실행 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(UserFactory)

        user = User(name="Alice")
        result = await container.modify(user, "enhance")

        assert result.enhanced is True
        assert result.name == "Alice"

    @pytest.mark.asyncio
    async def test_async_modifier_execution(self):
        """비동기 Modifier 실행 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(UserFactory)

        user = User(name="Bob")
        result = await container.modify(user, "process_async")

        assert result.processed is True


class TestFactoryWithDependencies:
    """의존성 주입이 있는 Factory 테스트"""

    @pytest.mark.asyncio
    async def test_factory_with_service_dependency(self):
        """서비스 의존성 주입 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(UserFactory)

        result = await container.create(User, "create_and_notify", "Alice")
        assert result.name == "Alice"
        assert result.notified is True

    def test_email_service_registered(self):
        """EmailService가 등록되어 있는지 확인"""
        assert EmailService in containers


class TestContainerManagerFactoryMethods:
    """ContainerManager의 Factory 관련 메서드 테스트"""

    def test_get_factories(self):
        """get_factories 테스트"""
        manager = get_container_manager()
        factories = manager.get_factories()

        # conftest.py에 등록된 4개의 Factory
        assert len(factories) >= 4

    def test_get_factories_for_type(self):
        """타입별 Factory 조회 테스트"""
        manager = get_container_manager()

        user_factories = manager.get_factories_for_type(User)
        # UserFactory, UserEnhancerFactory, UserProcessorFactory
        assert len(user_factories) >= 3

        config_factories = manager.get_factories_for_type(Config)
        # ConfigFactory
        assert len(config_factories) >= 1

    def test_get_factories_creating(self):
        """생성 타입별 Factory 조회 테스트"""
        manager = get_container_manager()

        user_factories = manager.get_factories_creating(User)
        # UserFactory만 User를 생성 (Creator 메서드 보유)
        assert len(user_factories) >= 1

        config_factories = manager.get_factories_creating(Config)
        # ConfigFactory만 Config를 생성
        assert len(config_factories) >= 1

    @pytest.mark.asyncio
    async def test_apply_modifiers(self):
        """apply_modifiers 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        user = User(name="Alice")
        result = await manager.apply_modifiers(user, User)

        # UserFactory, UserEnhancerFactory, UserProcessorFactory의 Modifier가 적용됨
        assert result.enhanced is True
        assert result.processed is True


class TestMultipleFactories:
    """여러 Factory 테스트"""

    @pytest.mark.asyncio
    async def test_multiple_factories_same_type(self):
        """같은 타입에 대한 여러 Factory의 Modifier 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        user = User(name="Alice")
        result = await manager.apply_modifiers(user, User)

        # 여러 Factory의 Modifier가 모두 적용됨
        assert result.enhanced is True
        assert result.processed is True

    @pytest.mark.asyncio
    async def test_factory_create_then_modify(self):
        """Factory로 생성 후 수정 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(UserFactory)

        # 생성
        user = await container.create(User, "create", "Bob")
        assert user.name == "Bob"
        assert user.enhanced is False

        # 수정
        user = await container.modify(user, "enhance")
        assert user.enhanced is True


# =============================================================================
# 복잡한 Factory 체인 통합 테스트
# =============================================================================


class TestComplexFactoryChainRegistration:
    """복잡한 Factory 체인 등록 테스트"""

    def test_all_complex_components_registered(self):
        """모든 복잡한 컴포넌트들이 등록되어 있는지 확인"""
        # 서비스들
        assert LoggingService in containers
        assert NotificationService in containers
        assert DiscountService in containers

        # 컴포넌트들
        assert ValidationComponent in containers
        assert OrderProcessingComponent in containers

        # Factory들
        assert OrderFactory in containers
        assert ProductFactory in containers
        assert ReportFactory in containers

    def test_factory_container_types(self):
        """Factory 컨테이너 타입 확인"""
        for factory_cls in [OrderFactory, ProductFactory, ReportFactory]:
            container = get_factory_container(factory_cls)
            assert isinstance(container, FactoryContainer)


class TestComplexFactoryMethodAnalysis:
    """복잡한 Factory 메서드 분석 테스트"""

    def test_order_factory_methods(self):
        """OrderFactory 메서드 분석"""
        container = get_factory_container(OrderFactory)

        # Creator 메서드들
        creator_methods = container.get_creator_methods(Order)
        assert "create_order" in creator_methods
        assert "create_with_notification" in creator_methods

        # Modifier 메서드들
        modifier_methods = container.get_modifier_methods(Order)
        assert "validate" in modifier_methods
        assert "apply_discount" in modifier_methods
        assert "notify_order" in modifier_methods

    def test_product_factory_methods(self):
        """ProductFactory 메서드 분석"""
        container = get_factory_container(ProductFactory)

        creator_methods = container.get_creator_methods(Product)
        assert "create_product" in creator_methods

        modifier_methods = container.get_modifier_methods(Product)
        assert "mark_out_of_stock" in modifier_methods

    def test_report_factory_methods(self):
        """ReportFactory 메서드 분석"""
        container = get_factory_container(ReportFactory)

        creator_methods = container.get_creator_methods(Report)
        assert "create_report" in creator_methods
        # create_order_report는 Order 파라미터를 받으므로 Creator
        assert "create_order_report" in creator_methods

        modifier_methods = container.get_modifier_methods(Report)
        assert "format_report" in modifier_methods
        assert "export_report" in modifier_methods


class TestComplexFactoryDependencyInjection:
    """복잡한 Factory 의존성 주입 테스트"""

    @pytest.mark.asyncio
    async def test_order_factory_with_all_dependencies(self):
        """OrderFactory의 모든 의존성 주입 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(OrderFactory)

        # 주문 생성
        order = await container.create(Order, "create_order", "ORD-001", "Alice", 100.0)
        assert order.id == "ORD-001"
        assert order.user_name == "Alice"
        assert order.total == 100.0

        # LoggingService가 주입되어 로그가 기록되었는지 확인
        logging_service = manager.get_instance(LoggingService)
        assert logging_service is not None
        assert any("ORD-001" in log for log in logging_service.logs)

    @pytest.mark.asyncio
    async def test_order_factory_validation_with_nested_dependency(self):
        """ValidationComponent를 통한 중첩 의존성 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(OrderFactory)

        # 주문 생성 후 검증
        order = await container.create(Order, "create_order", "ORD-002", "Bob", 50.0)
        order = await container.modify(order, "validate")

        assert order.validated is True

        # ValidationComponent가 LoggingService를 사용했는지 확인
        logging_service = manager.get_instance(LoggingService)
        assert logging_service is not None
        assert any("Validating order ORD-002" in log for log in logging_service.logs)

    @pytest.mark.asyncio
    async def test_order_factory_discount_service_injection(self):
        """DiscountService 주입 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(OrderFactory)

        order = await container.create(
            Order, "create_order", "ORD-003", "Charlie", 100.0
        )
        order = await container.modify(order, "apply_discount")

        # 10% 할인 적용
        assert order.total == 90.0
        assert order.discounted is True


class TestComplexFactoryAsyncOperations:
    """복잡한 Factory 비동기 작업 테스트"""

    @pytest.mark.asyncio
    async def test_async_creator_with_notification(self):
        """비동기 Creator와 NotificationService 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(OrderFactory)

        order = await container.create(
            Order, "create_with_notification", "ORD-004", "Diana", 200.0
        )

        assert order.id == "ORD-004"

        # NotificationService 확인
        notification_service = manager.get_instance(NotificationService)
        assert notification_service is not None
        assert any("ORD-004" in notif for notif in notification_service.notifications)

    @pytest.mark.asyncio
    async def test_async_modifier(self):
        """비동기 Modifier 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(OrderFactory)

        order = await container.create(Order, "create_order", "ORD-005", "Eve", 150.0)
        order = await container.modify(order, "notify_order")

        assert order.notified is True

        notification_service = manager.get_instance(NotificationService)
        assert notification_service is not None
        assert any("ORD-005" in notif for notif in notification_service.notifications)

    @pytest.mark.asyncio
    async def test_report_async_export(self):
        """Report 비동기 내보내기 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(ReportFactory)

        report = await container.create(Report, "create_report", "Monthly Sales")
        report = await container.modify(report, "export_report")

        assert report.exported is True

        notification_service = manager.get_instance(NotificationService)
        assert notification_service is not None
        assert any(
            "Monthly Sales" in notif for notif in notification_service.notifications
        )


class TestComplexFactoryPipeline:
    """복잡한 Factory 파이프라인 테스트"""

    @pytest.mark.asyncio
    async def test_full_order_processing_pipeline(self):
        """전체 주문 처리 파이프라인 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(OrderFactory)

        # 1. 주문 생성
        order = await container.create(
            Order, "create_order", "ORD-100", "FullTest", 1000.0
        )
        assert order.id == "ORD-100"
        assert order.validated is False
        assert order.discounted is False
        assert order.notified is False

        # 2. 검증
        order = await container.modify(order, "validate")
        assert order.validated is True

        # 3. 할인 적용
        order = await container.modify(order, "apply_discount")
        assert order.discounted is True
        assert order.total == 900.0

        # 4. 알림
        order = await container.modify(order, "notify_order")
        assert order.notified is True

    @pytest.mark.asyncio
    async def test_product_lifecycle(self):
        """상품 생명주기 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        container = get_factory_container(ProductFactory)

        # 상품 생성
        product = await container.create(Product, "create_product", "Laptop", 999.99)
        assert product.name == "Laptop"
        assert product.in_stock is True

        # 품절 처리
        product = await container.modify(product, "mark_out_of_stock")
        assert product.in_stock is False

    @pytest.mark.asyncio
    async def test_report_with_order_data(self):
        """주문 데이터를 포함한 리포트 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        # 먼저 주문 생성
        order_container = get_factory_container(OrderFactory)
        order = await order_container.create(
            Order, "create_order", "ORD-RPT", "Reporter", 500.0
        )

        # 주문 리포트 생성
        report_container = get_factory_container(ReportFactory)
        report = await report_container.create(
            Report, "create_order_report", "Order Report", order
        )

        assert report.title == "Order Report"
        assert report.data is not None
        assert report.data["order_id"] == "ORD-RPT"
        assert report.data["total"] == 500.0

        # 포맷팅
        report = await report_container.modify(report, "format_report")
        assert report.formatted is True

        # 내보내기
        report = await report_container.modify(report, "export_report")
        assert report.exported is True


class TestComplexFactoryWithContainerManager:
    """ContainerManager와 복잡한 Factory 통합 테스트"""

    def test_get_factories_for_order(self):
        """Order 타입에 대한 Factory 조회"""
        manager = get_container_manager()

        order_factories = manager.get_factories_for_type(Order)
        # OrderFactory만 Order에 대한 Modifier를 가짐
        assert len(order_factories) >= 1

    def test_get_factories_creating_order(self):
        """Order를 생성하는 Factory 조회"""
        manager = get_container_manager()

        order_creators = manager.get_factories_creating(Order)
        assert len(order_creators) >= 1

    @pytest.mark.asyncio
    async def test_apply_all_modifiers_to_order(self):
        """Order에 등록된 모든 Modifier 적용"""
        manager = get_container_manager()
        await manager.initialize()

        order = Order(id="ORD-MOD", user_name="ModTest", total=200.0)
        result = await manager.apply_modifiers(order, Order)

        # OrderFactory의 모든 Modifier가 적용됨
        assert result.validated is True
        assert result.discounted is True
        assert result.notified is True


class TestMultipleFactorySameType:
    """같은 타입을 다루는 여러 Factory 테스트"""

    @pytest.mark.asyncio
    async def test_multiple_product_operations(self):
        """여러 Factory에서 같은 타입 처리"""
        manager = get_container_manager()
        await manager.initialize()

        # Product 생성
        product_container = get_factory_container(ProductFactory)
        product = await product_container.create(
            Product, "create_product", "Phone", 699.99
        )

        # 품절 처리
        product = await product_container.modify(product, "mark_out_of_stock")

        assert product.name == "Phone"
        assert product.price == 699.99
        assert product.in_stock is False


class TestFactoryInitializationOrder:
    """Factory 초기화 순서 테스트"""

    @pytest.mark.asyncio
    async def test_initialization_order_does_not_matter(self):
        """초기화 순서에 관계없이 의존성이 올바르게 주입되는지 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        # 모든 Factory가 초기화되었는지 확인
        factories = manager.get_factories()
        assert len(factories) >= 4  # 최소 4개의 Factory

        # 각 Factory의 인스턴스가 존재하는지 확인
        for factory_container in factories:
            instance = manager.get_instance(factory_container.kls)
            assert instance is not None

    @pytest.mark.asyncio
    async def test_nested_dependency_resolution(self):
        """중첩된 의존성 해결 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        # OrderFactory는 ValidationComponent에 의존
        # ValidationComponent는 LoggingService에 의존
        order_factory_instance = manager.get_instance(OrderFactory)
        assert order_factory_instance is not None
        assert order_factory_instance.validation_component is not None
        assert order_factory_instance.logging_service is not None

        # ValidationComponent의 LoggingService도 주입되었는지
        validation_component = manager.get_instance(ValidationComponent)
        assert validation_component is not None
        assert validation_component.logging_service is not None

        # 실제 LoggingService 인스턴스가 싱글톤인지 확인
        # LazyProxy를 통해 접근하므로 실제 동작을 통해 검증
        logging_service = manager.get_instance(LoggingService)
        assert logging_service is not None
        test_message = "singleton_test_message"
        logging_service.log(test_message)

        # OrderFactory와 ValidationComponent 모두 같은 LoggingService를 사용하는지 확인
        assert test_message in order_factory_instance.logging_service.logs
        assert test_message in validation_component.logging_service.logs
