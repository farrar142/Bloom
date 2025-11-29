"""라이프사이클 훅 테스트"""

import pytest
from bloom import Application, Component, PostConstruct, PreDestroy


class TestLifecycleHooks:
    """@PostConstruct, @PreDestroy 라이프사이클 훅 테스트"""

    def test_post_construct_called_on_ready(self, reset_container_manager):
        """@PostConstruct 메서드가 ready() 시 호출됨"""
        call_log = []

        @Component
        class Service:
            @PostConstruct
            def init(self):
                call_log.append("init")

        app = Application("test").ready()

        assert "init" in call_log
        assert len(call_log) == 1

    def test_pre_destroy_called_on_shutdown(self, reset_container_manager):
        """@PreDestroy 메서드가 shutdown() 시 호출됨"""
        call_log = []

        @Component
        class Service:
            @PreDestroy
            def cleanup(self):
                call_log.append("cleanup")

        app = Application("test").ready()
        assert "cleanup" not in call_log

        app.shutdown()
        assert "cleanup" in call_log

    def test_multiple_post_construct_methods(self, reset_container_manager):
        """여러 @PostConstruct 메서드가 모두 호출됨"""
        call_log = []

        @Component
        class Service:
            @PostConstruct
            def init1(self):
                call_log.append("init1")

            @PostConstruct
            def init2(self):
                call_log.append("init2")

        app = Application("test").ready()

        assert "init1" in call_log
        assert "init2" in call_log
        assert len(call_log) == 2

    def test_multiple_pre_destroy_methods(self, reset_container_manager):
        """여러 @PreDestroy 메서드가 모두 호출됨"""
        call_log = []

        @Component
        class Service:
            @PreDestroy
            def cleanup1(self):
                call_log.append("cleanup1")

            @PreDestroy
            def cleanup2(self):
                call_log.append("cleanup2")

        app = Application("test").ready()
        app.shutdown()

        assert "cleanup1" in call_log
        assert "cleanup2" in call_log
        assert len(call_log) == 2

    def test_post_construct_has_access_to_dependencies(self, reset_container_manager):
        """@PostConstruct에서 주입된 의존성에 접근 가능"""
        call_log = []

        @Component
        class Repository:
            def get_data(self):
                return "data"

        @Component
        class Service:
            repository: Repository

            @PostConstruct
            def init(self):
                # 의존성이 이미 주입되어 있어야 함
                call_log.append(self.repository.get_data())

        app = Application("test").ready()

        assert "data" in call_log

    def test_pre_destroy_called_in_reverse_order(self, reset_container_manager):
        """@PreDestroy가 초기화 역순으로 호출됨"""
        call_log = []

        @Component
        class Repository:
            @PreDestroy
            def cleanup(self):
                call_log.append("repository")

        @Component
        class Service:
            repository: Repository  # Repository에 의존

            @PreDestroy
            def cleanup(self):
                call_log.append("service")

        app = Application("test").ready()
        app.shutdown()

        # Service가 나중에 초기화되므로 먼저 정리됨
        assert call_log.index("service") < call_log.index("repository")

    def test_post_construct_and_pre_destroy_together(self, reset_container_manager):
        """@PostConstruct와 @PreDestroy를 함께 사용"""
        call_log = []

        @Component
        class DatabaseConnection:
            @PostConstruct
            def connect(self):
                call_log.append("connected")

            @PreDestroy
            def disconnect(self):
                call_log.append("disconnected")

        app = Application("test").ready()
        assert call_log == ["connected"]

        app.shutdown()
        assert call_log == ["connected", "disconnected"]

    def test_shutdown_without_ready_does_nothing(self, reset_container_manager):
        """ready() 없이 shutdown() 호출하면 아무 일도 안 함"""
        call_log = []

        @Component
        class Service:
            @PreDestroy
            def cleanup(self):
                call_log.append("cleanup")

        app = Application("test")
        app.shutdown()  # ready() 호출 안 함

        assert call_log == []

    def test_lifecycle_with_factory(self, reset_container_manager):
        """Factory로 생성된 컴포넌트의 라이프사이클"""
        call_log = []

        class ExternalClient:
            def connect(self):
                call_log.append("client_connected")

            def disconnect(self):
                call_log.append("client_disconnected")

        from bloom import Factory

        @Component
        class Config:
            @Factory
            def create_client(self) -> ExternalClient:
                client = ExternalClient()
                client.connect()
                return client

            @PostConstruct
            def init(self):
                call_log.append("config_init")

        app = Application("test").ready()

        # Config의 PostConstruct가 호출됨
        assert "config_init" in call_log
        # Factory로 생성된 ExternalClient도 connect 호출됨
        assert "client_connected" in call_log

    def test_post_construct_container_attribute(self, reset_container_manager):
        """@PostConstruct 메서드에 __container__ 속성이 있음"""

        @Component
        class Service:
            @PostConstruct
            def init(self):
                pass

        # __container__ 속성 확인
        assert hasattr(Service.init, "__container__")
        container = Service.init.__container__
        # PostConstructElement가 추가되었는지 확인
        from bloom.core.decorators import PostConstructElement

        assert container.has_element(PostConstructElement)

    def test_pre_destroy_container_attribute(self, reset_container_manager):
        """@PreDestroy 메서드에 __container__ 속성이 있음"""

        @Component
        class Service:
            @PreDestroy
            def cleanup(self):
                pass

        # __container__ 속성 확인
        assert hasattr(Service.cleanup, "__container__")
        container = Service.cleanup.__container__
        # PreDestroyElement가 추가되었는지 확인
        from bloom.core.decorators import PreDestroyElement

        assert container.has_element(PreDestroyElement)
