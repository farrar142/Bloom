"""Configuration properties tests"""

import pytest
from dataclasses import dataclass, field
from typing import Optional

from bloom import Application, Component
from bloom.config import ConfigurationProperties


class TestConfigurationPropertiesBasic:
    """기본 ConfigurationProperties 테스트"""

    def test_dataclass_without_prefix(self):
        """prefix 없이 dataclass 사용"""

        @ConfigurationProperties
        @dataclass
        class AppConfig:
            name: str = "MyApp"
            debug: bool = False

        app = Application("test")
        app.load_config({"name": "TestApp", "debug": True}, source_type="dict")
        app.scan(__name__).ready()

        config = app.manager.get_instance(AppConfig)
        assert config.name == "TestApp"
        assert config.debug is True

    def test_dataclass_with_prefix(self):
        """prefix와 함께 dataclass 사용"""

        @ConfigurationProperties("app.database")
        @dataclass
        class DatabaseConfig:
            host: str = "localhost"
            port: int = 5432
            username: str = ""
            password: str = ""

        app = Application("test")
        app.load_config(
            {
                "app": {
                    "database": {
                        "host": "db.example.com",
                        "port": 3306,
                        "username": "admin",
                        "password": "secret",
                    }
                }
            },
            source_type="dict",
        )
        app.scan(__name__).ready()

        config = app.manager.get_instance(DatabaseConfig)
        assert config.host == "db.example.com"
        assert config.port == 3306
        assert config.username == "admin"
        assert config.password == "secret"

    def test_dataclass_with_default_values(self):
        """기본값이 있는 dataclass"""

        @ConfigurationProperties("app")
        @dataclass
        class AppConfig:
            name: str = "MyApp"
            debug: bool = False
            version: str = "1.0.0"

        app = Application("test")
        app.load_config({"app": {"name": "TestApp"}}, source_type="dict")
        app.scan(__name__).ready()

        config = app.manager.get_instance(AppConfig)
        assert config.name == "TestApp"
        assert config.debug is False  # 기본값
        assert config.version == "1.0.0"  # 기본값

    def test_configuration_injection_into_component(self):
        """Component에 설정 주입"""

        @ConfigurationProperties("database")
        @dataclass
        class DatabaseConfig:
            host: str = "localhost"
            port: int = 5432

        @Component
        class DatabaseService:
            config: DatabaseConfig

            def get_connection_string(self) -> str:
                return f"{self.config.host}:{self.config.port}"

        app = Application("test")
        app.load_config(
            {"database": {"host": "prod-db.com", "port": 3306}}, source_type="dict"
        )
        app.scan(__name__).ready()

        service = app.manager.get_instance(DatabaseService)
        assert service.get_connection_string() == "prod-db.com:3306"


class TestConfigurationPropertiesPydantic:
    """Pydantic 모델 ConfigurationProperties 테스트"""

    def test_pydantic_model_basic(self):
        """Pydantic 모델 기본 사용"""
        try:
            from pydantic import BaseModel, Field
        except ImportError:
            pytest.skip("Pydantic not installed")

        @ConfigurationProperties("app.database")
        class DatabaseConfig(BaseModel):
            host: str = "localhost"
            port: int = Field(default=5432, ge=1, le=65535)
            username: str
            password: str

        app = Application("test")
        app.load_config(
            {
                "app": {
                    "database": {
                        "host": "db.example.com",
                        "port": 3306,
                        "username": "admin",
                        "password": "secret",
                    }
                }
            },
            source_type="dict",
        )
        app.scan(__name__).ready()

        config = app.manager.get_instance(DatabaseConfig)
        assert config.host == "db.example.com"
        assert config.port == 3306
        assert config.username == "admin"

    def test_pydantic_model_validation(self):
        """Pydantic 검증 테스트"""
        try:
            from pydantic import BaseModel, Field, ValidationError
        except ImportError:
            pytest.skip("Pydantic not installed")

        @ConfigurationProperties("app.database")
        class DatabaseConfig(BaseModel):
            host: str
            port: int = Field(ge=1, le=65535)

        app = Application("test")
        app.load_config(
            {"app": {"database": {"host": "localhost", "port": 99999}}},  # 범위 초과
            source_type="dict",
        )

        with pytest.raises(ValidationError):
            app.scan(__name__).ready()


class TestConfigurationPropertiesNested:
    """중첩된 설정 테스트"""

    def test_nested_dataclass(self):
        """중첩된 dataclass"""

        @ConfigurationProperties("app.database")
        @dataclass
        class DatabaseConfig:
            host: str = "localhost"
            port: int = 5432

            @dataclass
            class Pool:
                min_size: int = 5
                max_size: int = 20

            pool: Pool = field(default_factory=Pool)

        app = Application("test")
        app.load_config(
            {
                "app": {
                    "database": {
                        "host": "db.example.com",
                        "port": 3306,
                        "pool": {"min_size": 10, "max_size": 50},
                    }
                }
            },
            source_type="dict",
        )
        app.scan(__name__).ready()

        config = app.manager.get_instance(DatabaseConfig)
        assert config.host == "db.example.com"
        assert config.pool.min_size == 10
        assert config.pool.max_size == 50


class TestConfigurationLoader:
    """설정 로더 테스트"""

    def test_load_from_dict(self):
        """딕셔너리에서 설정 로드"""

        @ConfigurationProperties("app")
        @dataclass
        class AppConfig:
            name: str = "MyApp"

        app = Application("test")
        app.load_config({"app": {"name": "TestApp"}}, source_type="dict")
        app.scan(__name__).ready()

        config = app.manager.get_instance(AppConfig)
        assert config.name == "TestApp"

    def test_multiple_config_sources(self):
        """여러 설정 소스 병합"""

        @ConfigurationProperties("app")
        @dataclass
        class AppConfig:
            name: str = "MyApp"
            debug: bool = False
            version: str = "1.0.0"

        app = Application("test")
        app.load_config({"app": {"name": "TestApp", "debug": True}}, source_type="dict")
        app.load_config({"app": {"version": "2.0.0"}}, source_type="dict")  # 병합
        app.scan(__name__).ready()

        config = app.manager.get_instance(AppConfig)
        assert config.name == "TestApp"
        assert config.debug is True
        assert config.version == "2.0.0"


class TestConfigurationPropertiesHelper:
    """Helper 함수 테스트"""

    def test_is_configuration_properties(self):
        """is_configuration_properties 함수"""
        from bloom.config.properties import is_configuration_properties

        @ConfigurationProperties("app")
        @dataclass
        class AppConfig:
            name: str = "MyApp"

        @dataclass
        class RegularClass:
            value: str = "test"

        assert is_configuration_properties(AppConfig) is True
        assert is_configuration_properties(RegularClass) is False

    def test_get_prefix(self):
        """get_prefix 함수"""
        from bloom.config.properties import get_prefix

        @ConfigurationProperties("app.database")
        @dataclass
        class DatabaseConfig:
            host: str = "localhost"

        @ConfigurationProperties
        @dataclass
        class NoPrefix:
            value: str = "test"

        assert get_prefix(DatabaseConfig) == "app.database"
        assert get_prefix(NoPrefix) == ""
