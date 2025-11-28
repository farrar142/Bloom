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


class TestConfigurationEnvVars:
    """환경변수 참조 테스트"""

    def test_env_var_in_yaml(self, tmp_path):
        """YAML 파일에서 환경변수 참조"""
        import os

        # 환경변수 설정
        os.environ["TEST_DB_HOST"] = "production.db.com"
        os.environ["TEST_DB_PORT"] = "3306"
        os.environ["TEST_DEBUG"] = "true"

        # YAML 파일 생성
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
app:
  name: MyApp
  debug: ${TEST_DEBUG}
database:
  host: ${TEST_DB_HOST}
  port: ${TEST_DB_PORT}
  username: admin
"""
        )

        @ConfigurationProperties("database")
        @dataclass
        class DatabaseConfig:
            host: str = "localhost"
            port: int = 5432
            username: str = ""

        @ConfigurationProperties("app")
        @dataclass
        class AppConfig:
            name: str = ""
            debug: bool = False

        app = Application("test")
        app.load_config(str(config_file), source_type="yaml")
        app.scan(__name__).ready()

        db_config = app.manager.get_instance(DatabaseConfig)
        app_config = app.manager.get_instance(AppConfig)

        assert db_config.host == "production.db.com"
        assert db_config.port == 3306  # 문자열 "3306"이 int로 자동 변환
        assert db_config.username == "admin"
        assert app_config.debug is True  # 문자열 "true"가 bool로 자동 변환

        # 환경변수 정리
        del os.environ["TEST_DB_HOST"]
        del os.environ["TEST_DB_PORT"]
        del os.environ["TEST_DEBUG"]

    def test_env_var_with_default_value(self, tmp_path):
        """환경변수가 없을 때 기본값 사용"""
        import os

        # 환경변수가 없는 상태에서 기본값 테스트
        assert "TEST_MISSING_VAR" not in os.environ

        # YAML 파일 생성 (기본값 포함)
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
database:
  host: ${MISSING_HOST:localhost}
  port: ${MISSING_PORT:5432}
  username: ${MISSING_USER:defaultuser}
"""
        )

        @ConfigurationProperties("database")
        @dataclass
        class DatabaseConfig:
            host: str = ""
            port: int = 0
            username: str = ""

        app = Application("test")
        app.load_config(str(config_file), source_type="yaml")
        app.scan(__name__).ready()

        config = app.manager.get_instance(DatabaseConfig)
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.username == "defaultuser"

    def test_env_var_partial_substitution(self, tmp_path):
        """문자열 일부만 환경변수로 치환"""
        import os

        os.environ["TEST_DOMAIN"] = "example.com"
        os.environ["TEST_PORT"] = "8080"

        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
server:
  url: https://${TEST_DOMAIN}:${TEST_PORT}/api
  description: Server at ${TEST_DOMAIN}
"""
        )

        @ConfigurationProperties("server")
        @dataclass
        class ServerConfig:
            url: str = ""
            description: str = ""

        app = Application("test")
        app.load_config(str(config_file), source_type="yaml")
        app.scan(__name__).ready()

        config = app.manager.get_instance(ServerConfig)
        assert config.url == "https://example.com:8080/api"
        assert config.description == "Server at example.com"

        del os.environ["TEST_DOMAIN"]
        del os.environ["TEST_PORT"]

    def test_env_var_in_dict(self):
        """딕셔너리에서도 환경변수 참조 가능"""
        import os

        os.environ["TEST_APP_NAME"] = "DictApp"

        @ConfigurationProperties("app")
        @dataclass
        class AppConfig:
            name: str = ""

        app = Application("test")
        app.load_config({"app": {"name": "${TEST_APP_NAME}"}}, source_type="dict")
        app.scan(__name__).ready()

        config = app.manager.get_instance(AppConfig)
        assert config.name == "DictApp"

        del os.environ["TEST_APP_NAME"]

    def test_env_var_nested_dict(self, tmp_path):
        """중첩된 딕셔너리에서 환경변수 참조"""
        import os

        os.environ["TEST_REDIS_HOST"] = "redis.local"
        os.environ["TEST_REDIS_PORT"] = "6379"

        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """
cache:
  redis:
    host: ${TEST_REDIS_HOST}
    port: ${TEST_REDIS_PORT}
    ttl: 3600
"""
        )

        @ConfigurationProperties("cache.redis")
        @dataclass
        class RedisConfig:
            host: str = ""
            port: int = 0
            ttl: int = 0

        app = Application("test")
        app.load_config(str(config_file), source_type="yaml")
        app.scan(__name__).ready()

        config = app.manager.get_instance(RedisConfig)
        assert config.host == "redis.local"
        assert config.port == 6379
        assert config.ttl == 3600

        del os.environ["TEST_REDIS_HOST"]
        del os.environ["TEST_REDIS_PORT"]
