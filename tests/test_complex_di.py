"""복잡한 의존성 주입 시나리오 테스트"""

import pytest
from bloom import Application, Component
from bloom.core import (
    Factory,
    Handler,
)

from .conftest import Module


class TestComplexDependencyInjection:
    """복잡한 의존성 체인 테스트"""

    def test_deep_dependency_chain(self):
        """깊은 의존성 체인 (A → B → C → D)"""
        init_order: list[str] = []

        class M:
            pass

        @Module(M)
        @Component
        class D:
            def __init__(self):
                init_order.append("D")

        @Module(M)
        @Component
        class C:
            d: D

            def __init__(self):
                init_order.append("C")

        @Module(M)
        @Component
        class B:
            c: C

            def __init__(self):
                init_order.append("B")

        @Module(M)
        @Component
        class A:
            b: B

            def __init__(self):
                init_order.append("A")

        app = Application("test_deep_chain")
        app.scan_components(M)
        app.initialize_components()

        # D → C → B → A 순서로 초기화되어야 함
        assert init_order == ["D", "C", "B", "A"]

        # 의존성이 제대로 주입되었는지 확인
        a_instance = app.manager.get_instance(A)
        assert a_instance.b is not None
        assert a_instance.b.c is not None
        assert a_instance.b.c.d is not None

    def test_diamond_dependency(self):
        """다이아몬드 의존성 (A → B, C → D)"""

        class M:
            pass

        @Module(M)
        @Component
        class D:
            pass

        @Module(M)
        @Component
        class B:
            d: D

        @Module(M)
        @Component
        class C:
            d: D

        @Module(M)
        @Component
        class A:
            b: B
            c: C

        app = Application("test_diamond")
        app.scan_components(M)
        app.initialize_components()

        a_instance = app.manager.get_instance(A)
        # B와 C가 같은 D 인스턴스를 공유해야 함
        assert a_instance.b.d is a_instance.c.d

    def test_factory_with_multiple_dependencies(self):
        """여러 의존성을 가진 Factory"""

        class M:
            pass

        @Module(M)
        @Component
        class Logger:
            pass

        @Module(M)
        @Component
        class Database:
            pass

        class ComplexService:
            def __init__(self, logger: Logger, db: Database):
                self.logger = logger
                self.db = db

        @Module(M)
        @Component
        class ServiceFactory:
            @Factory
            def create_complex_service(
                self, logger: Logger, db: Database
            ) -> ComplexService:
                return ComplexService(logger, db)

        app = Application("test_factory_multi_deps")
        app.scan_components(M)
        app.initialize_components()

        service = app.manager.get_instance(ComplexService)
        assert service is not None
        assert isinstance(service.logger, Logger)
        assert isinstance(service.db, Database)

    def test_factory_depending_on_another_factory(self):
        """Factory가 다른 Factory의 결과물에 의존"""

        class M:
            pass

        @Module(M)
        @Component
        class Config:
            pass

        class Connection:
            def __init__(self, config: Config):
                self.config = config

        class Client:
            def __init__(self, connection: Connection):
                self.connection = connection

        @Module(M)
        @Component
        class ConnectionFactory:
            @Factory
            def create_connection(self, config: Config) -> Connection:
                return Connection(config)

        @Module(M)
        @Component
        class ClientFactory:
            @Factory
            def create_client(self, conn: Connection) -> Client:
                return Client(conn)

        app = Application("test_factory_chain")
        app.scan_components(M)
        app.initialize_components()

        client = app.manager.get_instance(Client)
        assert client is not None
        assert isinstance(client.connection, Connection)
        assert isinstance(client.connection.config, Config)


class TestHandlerIntegration:
    """Handler와 다른 컴포넌트 통합 테스트"""

    @pytest.mark.asyncio
    async def test_handler_with_injected_service(self):
        """Handler가 주입된 서비스를 사용 (비동기)"""

        class M:
            pass

        @Module(M)
        @Component
        class UserRepository:
            def get_all(self) -> list[str]:
                return ["user1", "user2", "user3"]

        @Module(M)
        @Component
        class UserController:
            repo: UserRepository

            @Handler(("GET", "/users"))
            def list_users(self) -> list[str]:
                return self.repo.get_all()

        app = Application("test_handler_service")
        app.scan_components(M)
        app.initialize_components()

        handler = UserController.list_users.__container__
        result = await handler()
        assert result == ["user1", "user2", "user3"]

    @pytest.mark.asyncio
    async def test_multiple_handlers_same_controller(self):
        """같은 Controller에 여러 Handler (비동기)"""

        class M:
            pass

        @Module(M)
        @Component
        class MultiController:
            @Handler(("GET", "/a"))
            def handle_a(self) -> str:
                return "A"

            @Handler(("GET", "/b"))
            def handle_b(self) -> str:
                return "B"

            @Handler(("POST", "/c"))
            def handle_c(self) -> str:
                return "C"

        app = Application("test_multi_handlers")
        app.scan_components(M)
        app.initialize_components()

        assert await MultiController.handle_a.__container__() == "A"
        assert await MultiController.handle_b.__container__() == "B"
        assert await MultiController.handle_c.__container__() == "C"


class TestCircularDependencyDetection:
    """순환 의존성 감지 테스트"""

    def test_circular_dependency_raises(self):
        """순환 의존성이 있으면 예외 발생"""

        class M:
            pass

        @Module(M)
        @Component
        class Circular1:
            pass

        @Module(M)
        @Component
        class Circular2:
            c1: Circular1

        # Circular1이 Circular2에 의존하도록 수정 (순환 생성)
        Circular1.__annotations__ = {"c2": Circular2}
        getattr(Circular1, "__container__")._target = Circular1

        app = Application("test_circular")
        app.scan_components(M)

        with pytest.raises(Exception, match="Circular dependency"):
            app.initialize_components()
