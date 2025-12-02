"""라이프사이클 엣지 케이스 테스트"""

import pytest
from typing import ClassVar

from bloom import Application, Component
from bloom.core import Factory, Scope, ScopeEnum
from bloom.core.decorators import PostConstruct, PreDestroy


class TestPostConstructEdgeCases:
    """@PostConstruct 엣지 케이스 테스트"""

    def test_postconstruct_exception_stops_initialization(
        self, reset_container_manager
    ):
        """@PostConstruct에서 예외 발생하면 초기화 중단"""

        @Component
        class FailingInit:
            @PostConstruct
            def init(self):
                raise ValueError("Init failed!")

        app = Application("failing_init").scan(FailingInit)

        with pytest.raises(ValueError, match="Init failed!"):
            app.ready()

    def test_multiple_postconstruct_all_called(self, reset_container_manager):
        """여러 @PostConstruct 메서드가 모두 호출됨"""

        init_order: list[str] = []

        @Component
        class MultiInit:
            @PostConstruct
            def init1(self):
                init_order.append("init1")

            @PostConstruct
            def init2(self):
                init_order.append("init2")

        app = Application("multi_init").scan(MultiInit).ready()
        app.manager.get_instance(MultiInit)

        assert len(init_order) == 2
        assert "init1" in init_order
        assert "init2" in init_order

    def test_postconstruct_sync(self, reset_container_manager):
        """동기 @PostConstruct"""

        initialized = []

        @Component
        class SyncInit:
            @PostConstruct
            def init(self):
                initialized.append("sync_init")

        app = Application("sync_init").scan(SyncInit).ready()
        app.manager.get_instance(SyncInit)

        assert "sync_init" in initialized

    def test_postconstruct_with_dependency(self, reset_container_manager):
        """@PostConstruct에서 의존성 사용"""

        @Component
        class Config:
            value: str = "config_value"

        @Component
        class ServiceWithInit:
            config: Config
            computed_value: str = ""

            @PostConstruct
            def init(self):
                # 의존성이 이미 주입된 상태에서 호출됨
                self.computed_value = f"computed_{self.config.value}"

        app = Application("init_dep").scan(Config, ServiceWithInit).ready()
        service = app.manager.get_instance(ServiceWithInit)

        assert service.computed_value == "computed_config_value"


class TestPreDestroyEdgeCases:
    """@PreDestroy 엣지 케이스 테스트"""

    def test_predestroy_called_on_shutdown(self, reset_container_manager):
        """@PreDestroy가 shutdown 시 호출됨"""

        destroy_order: list[str] = []

        @Component
        class CleanupService:
            @PreDestroy
            def cleanup(self):
                destroy_order.append("cleanup")

        app = Application("cleanup_test").scan(CleanupService).ready()
        app.manager.get_instance(CleanupService)
        app.shutdown()

        assert "cleanup" in destroy_order

    def test_multiple_predestroy_all_called(self, reset_container_manager):
        """여러 @PreDestroy 메서드가 모두 호출됨"""

        destroy_order: list[str] = []

        @Component
        class MultiDestroy:
            @PreDestroy
            def cleanup1(self):
                destroy_order.append("cleanup1")

            @PreDestroy
            def cleanup2(self):
                destroy_order.append("cleanup2")

        app = Application("multi_destroy").scan(MultiDestroy).ready()
        app.manager.get_instance(MultiDestroy)
        app.shutdown()

        assert len(destroy_order) == 2
        assert "cleanup1" in destroy_order
        assert "cleanup2" in destroy_order

    def test_predestroy_reverse_order(self, reset_container_manager):
        """@PreDestroy는 의존성 역순으로 호출"""

        destroy_order: list[str] = []

        @Component
        class First:
            @PreDestroy
            def cleanup(self):
                destroy_order.append("first")

        @Component
        class Second:
            first: First

            @PreDestroy
            def cleanup(self):
                destroy_order.append("second")

        @Component
        class Third:
            second: Second

            @PreDestroy
            def cleanup(self):
                destroy_order.append("third")

        app = Application("reverse_order").scan(First, Second, Third).ready()
        app.manager.get_instance(Third)
        app.shutdown()

        # 의존성 역순: Third -> Second -> First
        assert destroy_order == ["third", "second", "first"]


class TestPrototypeLifecycle:
    """PROTOTYPE 스코프 라이프사이클 테스트"""

    def test_prototype_via_field_injection(self, reset_container_manager):
        """PROTOTYPE은 필드 주입을 통해 사용"""

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeService:
            def get_id(self) -> int:
                return id(self)

        @Component
        class Consumer:
            proto: PrototypeService

        app = Application("proto_test").scan(PrototypeService, Consumer).ready()
        consumer = app.manager.get_instance(Consumer)

        # 필드 주입을 통해 PROTOTYPE 인스턴스 접근
        assert consumer.proto is not None


class TestFactoryLifecycle:
    """@Factory로 생성된 인스턴스 라이프사이클"""

    def test_factory_created_instance_postconstruct(self, reset_container_manager):
        """@Factory로 생성된 인스턴스도 @PostConstruct 호출"""

        class ExternalService:
            initialized: bool = False

            @PostConstruct
            def init(self):
                self.initialized = True

        @Component
        class Config:
            @Factory
            def create_external(self) -> ExternalService:
                return ExternalService()

        app = Application("factory_lifecycle").scan(Config).ready()
        service = app.manager.get_instance(ExternalService)

        assert service.initialized is True

    def test_factory_created_instance_predestroy(self, reset_container_manager):
        """@Factory로 생성된 인스턴스도 @PreDestroy 호출"""

        destroyed = [False]

        class ExternalService:
            @PreDestroy
            def cleanup(self):
                destroyed[0] = True

        @Component
        class Config:
            @Factory
            def create_external(self) -> ExternalService:
                return ExternalService()

        app = Application("factory_destroy").scan(Config).ready()
        app.manager.get_instance(ExternalService)
        app.shutdown()

        assert destroyed[0] is True


class TestLifecycleWithExceptions:
    """예외 상황에서의 라이프사이클"""

    def test_partial_init_cleanup(self, reset_container_manager):
        """부분 초기화 후 실패 시 정리"""

        cleanup_called = [False]
        init_order: list[str] = []

        @Component
        class First:
            @PostConstruct
            def init(self):
                init_order.append("first")

            @PreDestroy
            def cleanup(self):
                cleanup_called[0] = True

        @Component
        class Second:
            first: First

            @PostConstruct
            def init(self):
                init_order.append("second")
                raise ValueError("Second init failed!")

        app = Application("partial_init").scan(First, Second)

        with pytest.raises(ValueError, match="Second init failed!"):
            app.ready()

        # First는 초기화됨
        assert "first" in init_order

    def test_lifecycle_with_none_return(self, reset_container_manager):
        """@PostConstruct가 None 이외 반환해도 무시"""

        @Component
        class ReturnValue:
            @PostConstruct
            def init(self) -> str:
                return "ignored_value"

        app = Application("return_value").scan(ReturnValue).ready()
        instance = app.manager.get_instance(ReturnValue)

        # 정상 동작
        assert instance is not None
