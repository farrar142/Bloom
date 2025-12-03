"""@Configuration, @Factory 테스트"""

import pytest

from bloom.core import (
    Configuration,
    Factory,
    Scope,
    get_container_manager,
)


class TestConfigurationAndFactory:
    """@Configuration, @Factory 테스트"""

    def test_configuration_registers_as_component(self):
        """@Configuration이 컴포넌트로 등록되는지"""

        @Configuration
        class AppConfig:
            pass

        manager = get_container_manager()
        container = manager.get_container(AppConfig)

        assert container is not None

    def test_factory_method(self):
        """@Factory 메서드가 인스턴스를 생성하는지"""

        class ExternalClient:
            def __init__(self, url: str):
                self.url = url

        @Configuration
        class AppConfig:
            @Factory
            def external_client(self) -> ExternalClient:
                return ExternalClient("http://example.com")

        # Factory 등록은 scan 시점에 발생
        # 여기서는 데코레이터 마킹만 확인
        assert hasattr(AppConfig.external_client, "__bloom_factory__")
        assert AppConfig.external_client.__bloom_factory__ is True
