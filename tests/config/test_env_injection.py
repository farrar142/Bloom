"""환경변수 지연 주입 테스트

TDD 기반으로 EnvStr, EnvInt 등의 환경변수 타입과
ConfigurationProperties를 테스트합니다.
"""

import os
import pytest
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from bloom.core import (
    Component,
    Service,
    Configuration,
    Factory,
    reset_container_manager,
    get_container_manager,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
async def setup_and_teardown():
    """각 테스트 전후로 컨테이너 및 환경변수 초기화"""
    reset_container_manager()
    # 환경변수 백업
    original_env = os.environ.copy()
    yield
    # 환경변수 복원
    os.environ.clear()
    os.environ.update(original_env)
    manager = get_container_manager()
    await manager.scope_manager.destroy_singletons()
    reset_container_manager()


# =============================================================================
# Test: EnvStr, EnvInt, EnvFloat, EnvBool 기본 사용
# =============================================================================


class TestEnvTypes:
    """환경변수 타입 기본 테스트"""

    @pytest.mark.asyncio
    async def test_env_str_injection(self):
        """EnvStr로 문자열 환경변수 주입"""
        from bloom.config import EnvStr

        os.environ["TEST_API_KEY"] = "secret-key-123"

        @Service
        class MyService:
            api_key: EnvStr["TEST_API_KEY"]

        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(MyService)
        assert service.api_key == "secret-key-123"

    @pytest.mark.asyncio
    async def test_env_int_injection(self):
        """EnvInt로 정수 환경변수 주입"""
        from bloom.config import EnvInt

        os.environ["TEST_PORT"] = "6379"

        @Service
        class RedisService:
            port: EnvInt["TEST_PORT"]

        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(RedisService)
        assert service.port == 6379
        assert isinstance(service.port, int)

    @pytest.mark.asyncio
    async def test_env_float_injection(self):
        """EnvFloat로 실수 환경변수 주입"""
        from bloom.config import EnvFloat

        os.environ["TEST_RATE"] = "0.75"

        @Service
        class RateLimiter:
            rate: EnvFloat["TEST_RATE"]

        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(RateLimiter)
        assert service.rate == 0.75
        assert isinstance(service.rate, float)

    @pytest.mark.asyncio
    async def test_env_bool_injection(self):
        """EnvBool로 불리언 환경변수 주입"""
        from bloom.config import EnvBool

        os.environ["TEST_DEBUG"] = "true"

        @Service
        class DebugService:
            debug: EnvBool["TEST_DEBUG"]

        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(DebugService)
        assert service.debug is True
        assert isinstance(service.debug, bool)

    @pytest.mark.asyncio
    async def test_env_bool_various_values(self):
        """EnvBool 다양한 값 테스트"""
        from bloom.config import EnvBool

        # "1", "yes", "on" 도 True로 변환
        os.environ["TEST_ENABLED"] = "1"

        @Service
        class Service1:
            enabled: EnvBool["TEST_ENABLED"]

        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(Service1)
        assert service.enabled is True

    @pytest.mark.asyncio
    async def test_env_enum_injection(self):
        """EnvEnum으로 Enum 환경변수 주입"""
        from bloom.config import EnvEnum
        from typing import Literal

        class Environment(Enum):
            DEV = "development"
            PROD = "production"
            TEST = "test"

        os.environ["APP_ENV"] = "PROD"

        @Service
        class AppService:
            env: EnvEnum[Environment, Literal["APP_ENV"]]

        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(AppService)
        assert service.env == Environment.PROD

    @pytest.mark.asyncio
    async def test_env_missing_returns_none(self):
        """환경변수가 없으면 None 반환"""
        from bloom.config import EnvStr

        # TEST_MISSING 환경변수는 설정하지 않음

        @Service
        class ServiceWithMissing:
            missing: EnvStr["TEST_MISSING"]

        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(ServiceWithMissing)
        assert service.missing is None


# =============================================================================
# Test: 새로운 문법 EnvStr["KEY"] (문자열 키 직접 사용)
# =============================================================================


class TestEnvStringKeyFormat:
    """EnvStr["KEY"] 형식 문자열 키 테스트"""

    @pytest.mark.asyncio
    async def test_env_str_string_key(self):
        """EnvStr["KEY"] 형식으로 환경변수 주입"""
        from bloom.config import EnvStr

        os.environ["MY_SECRET"] = "super-secret"

        @Service
        class SecretService:
            secret: EnvStr["MY_SECRET"]

        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(SecretService)
        assert service.secret == "super-secret"

    @pytest.mark.asyncio
    async def test_env_int_string_key(self):
        """EnvInt["KEY"] 형식으로 환경변수 주입"""
        from bloom.config import EnvInt

        os.environ["REDIS_PORT"] = "6380"

        @Service
        class RedisConfig:
            redis_port: EnvInt["REDIS_PORT"]

        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(RedisConfig)
        assert service.redis_port == 6380

    @pytest.mark.asyncio
    async def test_multiple_env_fields(self):
        """여러 환경변수 필드 주입"""
        from bloom.config import EnvStr, EnvInt, EnvBool

        os.environ["DB_HOST"] = "localhost"
        os.environ["DB_PORT"] = "5432"
        os.environ["DB_SSL"] = "true"

        @Service
        class DatabaseConfig:
            host: EnvStr["DB_HOST"]
            port: EnvInt["DB_PORT"]
            ssl: EnvBool["DB_SSL"]

        manager = get_container_manager()
        await manager.initialize()

        config = await manager.get_instance_async(DatabaseConfig)
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.ssl is True


# =============================================================================
# Test: ConfigurationProperties - YAML/ENV에서 설정 주입
# =============================================================================


@pytest.mark.skip(reason="ConfigurationProperties config_manager 시스템 미구현")
class TestConfigurationProperties:
    """ConfigurationProperties 테스트"""

    @pytest.mark.asyncio
    async def test_configuration_properties_basic(self):
        """기본 ConfigurationProperties 사용"""
        from bloom.config import ConfigurationProperties

        @ConfigurationProperties("app")
        @dataclass
        class AppConfig:
            name: str = "default"
            version: str = "1.0.0"

        manager = get_container_manager()

        # 설정 로드
        manager.config_manager.load_config(
            {"app": {"name": "MyApp", "version": "2.0.0"}}, source_type="dict"
        )
        await manager.initialize()

        config = await manager.get_instance_async(AppConfig)
        assert config.name == "MyApp"
        assert config.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_configuration_properties_nested(self):
        """중첩된 설정 바인딩"""
        from bloom.config import ConfigurationProperties

        @ConfigurationProperties("bloom.redis")
        @dataclass
        class RedisConfig:
            host: str = "localhost"
            port: int = 6379
            password: str = ""

        manager = get_container_manager()

        manager.config_manager.load_config(
            {
                "bloom": {
                    "redis": {
                        "host": "redis.example.com",
                        "port": 6380,
                        "password": "secret123",
                    }
                }
            },
            source_type="dict",
        )
        await manager.initialize()

        config = await manager.get_instance_async(RedisConfig)
        assert config.host == "redis.example.com"
        assert config.port == 6380
        assert config.password == "secret123"

    @pytest.mark.asyncio
    async def test_configuration_properties_with_pydantic(self):
        """Pydantic BaseModel과 ConfigurationProperties"""
        from bloom.config import ConfigurationProperties

        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("Pydantic not installed")

        @ConfigurationProperties("database")
        class DatabaseConfig(BaseModel):
            host: str = "localhost"
            port: int = 5432
            username: str = ""
            password: str = ""

        manager = get_container_manager()

        manager.config_manager.load_config(
            {
                "database": {
                    "host": "db.example.com",
                    "port": 5433,
                    "username": "admin",
                    "password": "pass123",
                }
            },
            source_type="dict",
        )
        await manager.initialize()

        config = await manager.get_instance_async(DatabaseConfig)
        assert config.host == "db.example.com"
        assert config.port == 5433
        assert config.username == "admin"

    @pytest.mark.asyncio
    async def test_configuration_properties_injection_to_service(self):
        """ConfigurationProperties를 Service에 주입"""
        from bloom.config import ConfigurationProperties

        @ConfigurationProperties("app.mail")
        @dataclass
        class MailConfig:
            smtp_host: str = "smtp.gmail.com"
            smtp_port: int = 587

        @Service
        class MailService:
            config: MailConfig

            def get_server(self) -> str:
                return f"{self.config.smtp_host}:{self.config.smtp_port}"

        manager = get_container_manager()

        manager.config_manager.load_config(
            {"app": {"mail": {"smtp_host": "mail.example.com", "smtp_port": 465}}},
            source_type="dict",
        )
        await manager.initialize()

        service = await manager.get_instance_async(MailService)
        assert service.get_server() == "mail.example.com:465"

    @pytest.mark.asyncio
    async def test_configuration_properties_nested_object(self):
        """중첩 객체가 있는 ConfigurationProperties"""
        from bloom.config import ConfigurationProperties

        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("Pydantic not installed")

        class ConnectionPool(BaseModel):
            min_size: int = 5
            max_size: int = 20

        @ConfigurationProperties("database")
        class DatabaseConfig(BaseModel):
            host: str = "localhost"
            port: int = 5432
            pool: ConnectionPool = ConnectionPool()

        manager = get_container_manager()

        manager.config_manager.load_config(
            {
                "database": {
                    "host": "db.example.com",
                    "pool": {"min_size": 10, "max_size": 50},
                }
            },
            source_type="dict",
        )
        await manager.initialize()

        config = await manager.get_instance_async(DatabaseConfig)
        assert config.host == "db.example.com"
        assert config.pool.min_size == 10
        assert config.pool.max_size == 50


# =============================================================================
# Test: ConfigurationProperties from YAML file
# =============================================================================


@pytest.mark.skip(reason="ConfigurationProperties config_manager 시스템 미구현")
class TestConfigurationPropertiesFromFile:
    """파일에서 ConfigurationProperties 로드 테스트"""

    @pytest.mark.asyncio
    async def test_load_from_yaml_string(self):
        """YAML 형식 설정 로드"""
        from bloom.config import ConfigurationProperties
        import tempfile
        import os

        yaml_content = """
bloom:
  app:
    name: YamlApp
    debug: true
  redis:
    host: yaml-redis.local
    port: 6381
"""
        # 임시 YAML 파일 생성
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:

            @ConfigurationProperties("bloom.redis")
            @dataclass
            class RedisConfig:
                host: str = "localhost"
                port: int = 6379

            manager = get_container_manager()
            manager.config_manager.load_config(yaml_path)
            await manager.initialize()

            config = await manager.get_instance_async(RedisConfig)
            assert config.host == "yaml-redis.local"
            assert config.port == 6381
        finally:
            os.unlink(yaml_path)


# =============================================================================
# Test: Environment variable resolution in YAML
# =============================================================================


@pytest.mark.skip(reason="ConfigurationProperties config_manager 시스템 미구현")
class TestEnvVarResolutionInYaml:
    """YAML 내 환경변수 참조 해석 테스트"""

    @pytest.mark.asyncio
    async def test_env_var_in_config(self):
        """설정 파일 내 ${ENV_VAR} 참조"""
        from bloom.config import ConfigurationProperties

        os.environ["DB_PASSWORD"] = "env-secret-password"

        @ConfigurationProperties("database")
        @dataclass
        class DbConfig:
            host: str = "localhost"
            password: str = ""

        manager = get_container_manager()

        # ${ENV_VAR} 형식 지원
        manager.config_manager.load_config(
            {"database": {"host": "db.local", "password": "${DB_PASSWORD}"}},
            source_type="dict",
        )
        await manager.initialize()

        config = await manager.get_instance_async(DbConfig)
        assert config.password == "env-secret-password"

    @pytest.mark.asyncio
    async def test_env_var_with_default(self):
        """${ENV_VAR:default} 형식 기본값"""
        from bloom.config import ConfigurationProperties

        # MISSING_VAR는 설정하지 않음

        @ConfigurationProperties("app")
        @dataclass
        class AppConfig:
            name: str = ""

        manager = get_container_manager()

        manager.config_manager.load_config(
            {"app": {"name": "${MISSING_VAR:DefaultApp}"}},
            source_type="dict",
        )
        await manager.initialize()

        config = await manager.get_instance_async(AppConfig)
        assert config.name == "DefaultApp"


# =============================================================================
# Test: Mixed Env and ConfigurationProperties
# =============================================================================


@pytest.mark.skip(reason="ConfigurationProperties config_manager 시스템 미구현")
class TestMixedEnvAndConfig:
    """EnvStr과 ConfigurationProperties 혼합 사용"""

    @pytest.mark.asyncio
    async def test_service_with_both_env_and_config(self):
        """EnvStr과 ConfigurationProperties 동시 주입"""
        from bloom.config import ConfigurationProperties, EnvStr

        os.environ["API_SECRET"] = "env-api-secret"

        @ConfigurationProperties("app.settings")
        @dataclass
        class AppSettings:
            name: str = "MyApp"
            max_connections: int = 100

        @Service
        class ApiService:
            api_secret: EnvStr["API_SECRET"]
            settings: AppSettings

            def get_info(self) -> dict:
                return {
                    "name": self.settings.name,
                    "secret_prefix": self.api_secret[:3] if self.api_secret else None,
                }

        manager = get_container_manager()

        manager.config_manager.load_config(
            {"app": {"settings": {"name": "ConfiguredApp", "max_connections": 200}}},
            source_type="dict",
        )
        await manager.initialize()

        service = await manager.get_instance_async(ApiService)
        info = service.get_info()

        assert info["name"] == "ConfiguredApp"
        assert info["secret_prefix"] == "env"
        assert service.settings.max_connections == 200


# =============================================================================
# Test: Factory with ConfigurationProperties
# =============================================================================


@pytest.mark.skip(reason="ConfigurationProperties config_manager 시스템 미구현")
class TestFactoryWithConfig:
    """@Factory에서 ConfigurationProperties 사용"""

    @pytest.mark.asyncio
    async def test_factory_uses_config(self):
        """@Factory 메서드에서 ConfigurationProperties 주입"""
        from bloom.config import ConfigurationProperties

        @ConfigurationProperties("redis")
        @dataclass
        class RedisConfig:
            host: str = "localhost"
            port: int = 6379

        class RedisClient:
            def __init__(self, host: str, port: int):
                self.host = host
                self.port = port

            def get_url(self) -> str:
                return f"redis://{self.host}:{self.port}"

        @Configuration
        class RedisConfiguration:
            @Factory
            def redis_client(self, config: RedisConfig) -> RedisClient:
                return RedisClient(host=config.host, port=config.port)

        manager = get_container_manager()

        manager.config_manager.load_config(
            {"redis": {"host": "redis.cluster.local", "port": 6380}},
            source_type="dict",
        )
        await manager.initialize()

        client = await manager.get_instance_async(RedisClient)
        assert client.get_url() == "redis://redis.cluster.local:6380"
