"""Configuration/Factory 데코레이터 통합 테스트

Spring의 @Configuration/@Factory 스타일로 외부 클래스 인스턴스를
컨테이너에 싱글톤으로 등록하는 기능을 테스트합니다.
"""

import pytest

from bloom.application import Application
from bloom.core import (
    ConfigurationContainer,
    get_container_manager,
)
from bloom.core.container.manager import containers

# conftest.py에서 등록된 클래스들 import
from tests.conftest import (
    # 데이터 클래스
    DatabaseConnection,
    CacheClient,
    AppSettings,
    # 서비스
    LoggingService,
    MyComponent,
    NotificationService,
    # Configuration
    InfrastructureConfig,
    ServiceConfig,
    # Factory 클래스
    UserRepository,
    UserService,
)


def get_configuration_container[T](config_cls: type[T]) -> ConfigurationContainer[T]:
    """Configuration 클래스에서 ConfigurationContainer를 가져오는 헬퍼 함수"""
    manager = get_container_manager()
    c = manager.container(type=config_cls)
    assert c is not None, f"Container not found for {config_cls.__name__}"
    container = manager.container(
        container_type=ConfigurationContainer, id=c.component_id
    )
    assert (
        container is not None
    ), f"ConfigurationContainer not found for {config_cls.__name__}"
    return container


class TestConfigurationRegistration:
    """Configuration 등록 테스트"""

    def test_configuration_registration(self):
        """Configuration 클래스 등록 테스트"""
        assert hasattr(InfrastructureConfig, "__component_id__")
        assert InfrastructureConfig in containers

    def test_configuration_container_type(self):
        """ConfigurationContainer 타입 확인"""
        container = get_configuration_container(InfrastructureConfig)
        assert isinstance(container, ConfigurationContainer)

    def test_all_configurations_registered(self):
        """모든 Configuration이 등록되어 있는지 확인"""
        assert InfrastructureConfig in containers
        assert ServiceConfig in containers


class TestFactoryDefinitionAnalysis:
    """Factory 정의 분석 테스트"""

    def test_infrastructure_Factory_definitions(self):
        """InfrastructureConfig의 Factory 정의 분석"""
        container = get_configuration_container(InfrastructureConfig)

        Factory_types = container.get_factory_types()
        assert DatabaseConnection in Factory_types
        assert CacheClient in Factory_types
        assert AppSettings in Factory_types

    def test_service_config_Factory_definitions(self):
        """ServiceConfig의 Factory 정의 분석"""
        container = get_configuration_container(ServiceConfig)

        Factory_types = container.get_factory_types()
        assert UserRepository in Factory_types
        assert UserService in Factory_types

    def test_Factory_dependencies(self):
        """Factory 의존성 분석"""
        container = get_configuration_container(ServiceConfig)

        # UserRepository는 DatabaseConnection에 의존
        user_repo_def = container.get_factory_definition(UserRepository)
        assert user_repo_def is not None
        assert "db" in user_repo_def.param_dependencies
        assert user_repo_def.param_dependencies["db"] == DatabaseConnection

        # UserService는 UserRepository와 CacheClient에 의존
        user_service_def = container.get_factory_definition(UserService)
        assert user_service_def is not None
        assert "user_repo" in user_service_def.param_dependencies
        assert "cache" in user_service_def.param_dependencies
        assert user_service_def.is_async is True

    def test_has_factory(self):
        """has_bean 메서드 테스트"""
        infra_container = get_configuration_container(InfrastructureConfig)
        service_container = get_configuration_container(ServiceConfig)

        assert infra_container.has_factory(DatabaseConnection)
        assert not infra_container.has_factory(UserRepository)

        assert service_container.has_factory(UserRepository)
        assert not service_container.has_factory(DatabaseConnection)


class TestFactoryCreation:
    """Factory 생성 테스트"""

    @pytest.mark.asyncio
    async def test_simple_Factory_creation(self):
        """단순 Factory 생성 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        # DatabaseConnection Factory 생성
        db = await manager.factory(DatabaseConnection)
        assert isinstance(db, DatabaseConnection)
        assert db.host == "localhost"
        assert db.port == 5432
        assert db.connected is True

    @pytest.mark.asyncio
    async def test_Factory_singleton(self):
        """Factory 싱글톤 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        db1 = await manager.factory(DatabaseConnection)
        db2 = await manager.factory(DatabaseConnection)

        # 같은 인스턴스여야 함
        assert db1 is db2

    @pytest.mark.asyncio
    async def test_Factory_with_dependency(self):
        """의존성이 있는 Factory 생성 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        # UserRepository는 DatabaseConnection에 의존
        user_repo = await manager.factory(UserRepository)
        assert isinstance(user_repo, UserRepository)
        assert isinstance(user_repo.db, DatabaseConnection)
        assert user_repo.db.connected is True

    @pytest.mark.asyncio
    async def test_async_Factory_creation(self):
        """비동기 Factory 생성 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        # UserService는 비동기로 초기화됨
        user_service = await manager.factory(UserService)
        assert isinstance(user_service, UserService)
        assert user_service.initialized is True

    @pytest.mark.asyncio
    async def test_Factory_chain_creation(self):
        """Factory 체인 생성 테스트 (A -> B -> C 의존성)"""
        manager = get_container_manager()
        await manager.initialize()

        # UserService -> UserRepository -> DatabaseConnection
        user_service = await manager.factory(UserService)

        assert user_service.repository is not None
        assert user_service.repository.db is not None
        assert user_service.repository.db.connected is True

    @pytest.mark.asyncio
    async def test_multiple_factories_from_same_configuration(self):
        """같은 Configuration에서 여러 Factory 생성"""
        manager = get_container_manager()
        await manager.initialize()

        db = await manager.factory(DatabaseConnection)
        cache = await manager.factory(CacheClient)
        settings = await manager.factory(AppSettings)

        assert db.host == "localhost"
        assert cache.ttl == 600
        assert settings.debug is True


class TestContainerManagerFactoryMethods:
    """ContainerManager의 Factory 관련 메서드 테스트"""

    def test_get_configurations(self):
        """configurations 테스트"""
        manager = get_container_manager()
        configs = manager.containers(ConfigurationContainer)

        assert len(configs) >= 2  # InfrastructureConfig, ServiceConfig

    def test_get_all_factory_types(self):
        """factory_types 테스트"""
        manager = get_container_manager()
        Factory_types = manager.factory_types()

        assert DatabaseConnection in Factory_types
        assert CacheClient in Factory_types
        assert AppSettings in Factory_types
        assert UserRepository in Factory_types
        assert UserService in Factory_types

    def test_find_configuration_for_factory(self):
        """configuration_for 테스트"""
        manager = get_container_manager()

        db_config = manager.configuration_for(DatabaseConnection)
        assert db_config is not None
        assert db_config.kls == InfrastructureConfig

        user_repo_config = manager.configuration_for(UserRepository)
        assert user_repo_config is not None
        assert user_repo_config.kls == ServiceConfig

    @pytest.mark.asyncio
    async def test_get_or_create_factory_instance(self):
        """factory(required=False) 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        # 존재하는 Factory
        db = await manager.factory(DatabaseConnection, required=False)
        assert db is not None

        # 존재하지 않는 Factory
        result = await manager.factory(str, required=False)  # str은 Factory이 아님
        assert result is None


class TestFactoryWithServiceDependency:
    """@Service와 @Factory 혼합 의존성 테스트"""

    @pytest.mark.asyncio
    async def test_Factory_using_service_dependency(self):
        """Factory이 @Service 의존성을 사용하는 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        # ServiceConfig는 LoggingService를 주입받음
        logging_service = manager.instance(type=LoggingService)
        assert logging_service is not None

        # ServiceConfig 컨테이너의 Factory 캐시 초기화
        service_container = get_configuration_container(ServiceConfig)
        service_container.clear_factories()

        # 로그 초기화
        logging_service.logs.clear()

        # UserRepository Factory 생성 시 로그가 기록됨
        await manager.factory(UserRepository)

        assert any(
            "UserRepository" in log for log in logging_service.logs
        ), f"Logs: {logging_service.logs}"

    @pytest.mark.asyncio
    async def test_Factory_and_service_coexistence(self):
        """Factory과 Service가 함께 사용되는 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        # @Service로 등록된 것
        logging_service = manager.instance(type=LoggingService)
        notification_service = manager.instance(type=NotificationService)

        # @Factory으로 등록된 것
        db = await manager.factory(DatabaseConnection)
        user_service = await manager.factory(UserService)

        assert logging_service is not None
        assert notification_service is not None
        assert db is not None
        assert user_service is not None


class TestFactoryFunctionality:
    """Factory 인스턴스 기능 테스트"""

    @pytest.mark.asyncio
    async def test_user_repository_operations(self):
        """UserRepository Factory 동작 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        user_repo = await manager.factory(UserRepository)

        # 사용자 저장
        user_repo.save("user1", {"id": "user1", "name": "Alice"})

        # 사용자 조회
        user = user_repo.find("user1")
        assert user is not None
        assert user["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_user_service_operations(self):
        """UserService Factory 동작 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        user_service = await manager.factory(UserService)
        assert user_service.initialized is True

        # 사용자 생성
        user = user_service.create_user("user2", "Bob")
        assert user["id"] == "user2"
        assert user["name"] == "Bob"

        # 사용자 조회
        found = user_service.get_user("user2")
        assert found is not None
        assert found["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_app_settings_Factory(self):
        """AppSettings Factory 테스트"""
        manager = get_container_manager()
        await manager.initialize()

        settings = await manager.factory(AppSettings)

        assert settings.debug is True
        assert settings.timeout == 60
        assert settings.max_connections == 50


class TestFactoryErrorHandling:
    """Factory 에러 처리 테스트"""

    @pytest.mark.asyncio
    async def test_get_factory_not_found(self):
        """존재하지 않는 Factory 조회 시 예외"""
        manager = get_container_manager()
        await manager.initialize()

        with pytest.raises(ValueError) as exc_info:
            await manager.factory(dict)  # dict는 Factory이 아님

        assert "No Factory found" in str(exc_info.value)


class TestFactoryDependencyInjection:
    """Factory 의존성 주입 테스트"""

    @pytest.mark.asyncio
    async def test_factory_dependency_injection(self, application: Application):
        """Factory 의존성 주입 동작 테스트"""
        await application.ready()
        my_service = application.container_manager.instance(type=MyComponent)

        my_service.cache_client.host
