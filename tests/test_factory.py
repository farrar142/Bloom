"""Factory 데코레이터 테스트"""

import pytest
from dataclasses import dataclass

from bloom.core import Factory, FactoryContainer, get_container_manager, Service
from bloom.core.container.manager import containers


@dataclass
class User:
    """테스트용 User 클래스"""
    name: str
    email: str = ""
    enhanced: bool = False
    processed: bool = False
    notified: bool = False


@dataclass
class Config:
    """테스트용 Config 클래스"""
    debug: bool = False
    timeout: int = 30


class TestFactoryRegistration:
    """Factory 등록 테스트"""

    def setup_method(self):
        """각 테스트 전 컨테이너 레지스트리 초기화"""
        containers.clear()

    def test_factory_registration(self):
        """Factory 클래스 등록 테스트"""

        @Factory
        class UserFactory:
            def create(self, name: str) -> User:
                return User(name=name)

        assert hasattr(UserFactory, "__component_id__")
        assert UserFactory in containers

    def test_factory_container_type(self):
        """FactoryContainer 타입 확인"""

        @Factory
        class ConfigFactory:
            def create(self) -> Config:
                return Config()

        component_id = ConfigFactory.__component_id__
        container = containers[ConfigFactory][component_id]
        assert isinstance(container, FactoryContainer)


class TestFactoryMethodAnalysis:
    """Factory 메서드 분석 테스트"""

    def setup_method(self):
        """각 테스트 전 컨테이너 레지스트리 초기화"""
        containers.clear()

    def test_creator_method_detection(self):
        """Creator 메서드 감지 테스트"""

        @Factory
        class UserFactory:
            def create_user(self, name: str, email: str) -> User:
                return User(name=name, email=email)

            def create_default_user(self) -> User:
                return User(name="default")

        component_id = UserFactory.__component_id__
        container: FactoryContainer = containers[UserFactory][component_id]

        creator_methods = container.get_creator_methods(User)
        assert "create_user" in creator_methods
        assert "create_default_user" in creator_methods

    def test_modifier_method_detection(self):
        """Modifier 메서드 감지 테스트"""

        @Factory
        class UserFactory:
            def enhance(self, user: User) -> User:
                user.enhanced = True
                return user

            def process(self, user: User) -> User:
                user.processed = True
                return user

        component_id = UserFactory.__component_id__
        container: FactoryContainer = containers[UserFactory][component_id]

        modifier_methods = container.get_modifier_methods(User)
        assert "enhance" in modifier_methods
        assert "process" in modifier_methods

    def test_mixed_creator_and_modifier(self):
        """Creator와 Modifier 혼합 테스트"""

        @Factory
        class UserFactory:
            def create(self, name: str) -> User:
                return User(name=name)

            def enhance(self, user: User) -> User:
                user.enhanced = True
                return user

        component_id = UserFactory.__component_id__
        container: FactoryContainer = containers[UserFactory][component_id]

        assert User in container.get_all_creator_types()
        assert User in container.get_all_modifier_types()

        creator_methods = container.get_creator_methods(User)
        modifier_methods = container.get_modifier_methods(User)

        assert "create" in creator_methods
        assert "enhance" in modifier_methods


class TestFactoryExecution:
    """Factory 실행 테스트"""

    def setup_method(self):
        """각 테스트 전 컨테이너 레지스트리 초기화"""
        containers.clear()

    @pytest.mark.asyncio
    async def test_sync_creator_execution(self):
        """동기 Creator 실행 테스트"""

        @Factory
        class UserFactory:
            def create(self, name: str, email: str = "") -> User:
                return User(name=name, email=email)

        manager = get_container_manager()
        await manager.initialize()

        component_id = UserFactory.__component_id__
        container: FactoryContainer = containers[UserFactory][component_id]

        result = await container.create(User, "create", "Alice", email="alice@example.com")
        assert isinstance(result, User)
        assert result.name == "Alice"
        assert result.email == "alice@example.com"

    @pytest.mark.asyncio
    async def test_async_creator_execution(self):
        """비동기 Creator 실행 테스트"""

        @Factory
        class UserFactory:
            async def create_async(self, name: str) -> User:
                return User(name=name, processed=True)

        manager = get_container_manager()
        await manager.initialize()

        component_id = UserFactory.__component_id__
        container: FactoryContainer = containers[UserFactory][component_id]

        result = await container.create(User, "create_async", "Bob")
        assert isinstance(result, User)
        assert result.name == "Bob"
        assert result.processed is True

    @pytest.mark.asyncio
    async def test_sync_modifier_execution(self):
        """동기 Modifier 실행 테스트"""

        @Factory
        class UserFactory:
            def enhance(self, user: User) -> User:
                user.enhanced = True
                return user

        manager = get_container_manager()
        await manager.initialize()

        component_id = UserFactory.__component_id__
        container: FactoryContainer = containers[UserFactory][component_id]

        user = User(name="Alice")
        result = await container.modify(user, "enhance")

        assert result.enhanced is True
        assert result.name == "Alice"

    @pytest.mark.asyncio
    async def test_async_modifier_execution(self):
        """비동기 Modifier 실행 테스트"""

        @Factory
        class UserFactory:
            async def process_async(self, user: User) -> User:
                user.processed = True
                return user

        manager = get_container_manager()
        await manager.initialize()

        component_id = UserFactory.__component_id__
        container: FactoryContainer = containers[UserFactory][component_id]

        user = User(name="Bob")
        result = await container.modify(user, "process_async")

        assert result.processed is True


class TestFactoryWithDependencies:
    """의존성 주입이 있는 Factory 테스트"""

    def setup_method(self):
        """각 테스트 전 컨테이너 레지스트리 초기화"""
        containers.clear()

    @pytest.mark.asyncio
    async def test_factory_with_service_dependency(self):
        """서비스 의존성 주입 테스트"""

        @Service
        class EmailService:
            def send_welcome(self, user: User) -> None:
                user.notified = True

        @Factory
        class UserFactory:
            email_service: EmailService

            def create_and_notify(self, name: str) -> User:
                user = User(name=name)
                self.email_service.send_welcome(user)
                return user

        manager = get_container_manager()
        await manager.initialize()

        component_id = UserFactory.__component_id__
        container: FactoryContainer = containers[UserFactory][component_id]

        result = await container.create(User, "create_and_notify", "Alice")
        assert result.name == "Alice"
        assert result.notified is True


class TestContainerManagerFactoryMethods:
    """ContainerManager의 Factory 관련 메서드 테스트"""

    def setup_method(self):
        """각 테스트 전 컨테이너 레지스트리 초기화"""
        containers.clear()

    def test_get_factories(self):
        """get_factories 테스트"""

        @Factory
        class Factory1:
            def create(self) -> User:
                return User(name="factory1")

        @Factory
        class Factory2:
            def create(self) -> Config:
                return Config()

        manager = get_container_manager()
        factories = manager.get_factories()

        assert len(factories) == 2

    def test_get_factories_for_type(self):
        """타입별 Factory 조회 테스트"""

        @Factory
        class UserFactory:
            def enhance(self, user: User) -> User:
                user.enhanced = True
                return user

        @Factory
        class ConfigFactory:
            def update(self, config: Config) -> Config:
                config.debug = True
                return config

        manager = get_container_manager()

        user_factories = manager.get_factories_for_type(User)
        assert len(user_factories) == 1

        config_factories = manager.get_factories_for_type(Config)
        assert len(config_factories) == 1

    def test_get_factories_creating(self):
        """생성 타입별 Factory 조회 테스트"""

        @Factory
        class UserFactory:
            def create(self, name: str) -> User:
                return User(name=name)

        @Factory
        class ConfigFactory:
            def create(self) -> Config:
                return Config()

        manager = get_container_manager()

        user_factories = manager.get_factories_creating(User)
        assert len(user_factories) == 1

        config_factories = manager.get_factories_creating(Config)
        assert len(config_factories) == 1

    @pytest.mark.asyncio
    async def test_apply_modifiers(self):
        """apply_modifiers 테스트"""

        @Factory
        class UserFactory:
            def enhance(self, user: User) -> User:
                user.enhanced = True
                return user

            async def process(self, user: User) -> User:
                user.processed = True
                return user

        manager = get_container_manager()
        await manager.initialize()

        user = User(name="Alice")
        result = await manager.apply_modifiers(user, User)

        assert result.enhanced is True
        assert result.processed is True


class TestMultipleFactories:
    """여러 Factory 테스트"""

    def setup_method(self):
        """각 테스트 전 컨테이너 레지스트리 초기화"""
        containers.clear()

    @pytest.mark.asyncio
    async def test_multiple_factories_same_type(self):
        """같은 타입에 대한 여러 Factory의 Modifier 테스트"""

        @Factory
        class EnhancerFactory:
            def enhance(self, user: User) -> User:
                user.enhanced = True
                return user

        @Factory
        class ProcessorFactory:
            def process(self, user: User) -> User:
                user.processed = True
                return user

        manager = get_container_manager()
        await manager.initialize()

        user = User(name="Alice")
        result = await manager.apply_modifiers(user, User)

        # 두 Factory의 Modifier가 모두 적용됨
        assert result.enhanced is True
        assert result.processed is True

    @pytest.mark.asyncio
    async def test_factory_create_then_modify(self):
        """Factory로 생성 후 수정 테스트"""

        @Factory
        class UserFactory:
            def create(self, name: str) -> User:
                return User(name=name)

            def enhance(self, user: User) -> User:
                user.enhanced = True
                return user

        manager = get_container_manager()
        await manager.initialize()

        component_id = UserFactory.__component_id__
        container: FactoryContainer = containers[UserFactory][component_id]

        # 생성
        user = await container.create(User, "create", "Bob")
        assert user.name == "Bob"
        assert user.enhanced is False

        # 수정
        user = await container.modify(user, "enhance")
        assert user.enhanced is True
