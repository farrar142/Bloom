"""환경변수 주입 테스트"""

import os
import pytest
from enum import Enum
from typing import Literal

from bloom import Application, Component
from bloom.config.env import Env, EnvStr, EnvInt, EnvFloat, EnvBool, EnvEnum


# 테스트용 Enum 정의
class Environment(str, Enum):
    """환경 Enum"""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class LogLevel(str, Enum):
    """로그 레벨 Enum"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Priority(int, Enum):
    """우선순위 Enum (int 기반)"""

    LOW = 1
    MEDIUM = 2
    HIGH = 3


class TestEnvInjection:
    """환경변수 주입 테스트"""

    async def test_env_str_injection(self):
        """문자열 환경변수 주입"""
        os.environ["TEST_PASSWORD"] = "secret123"

        @Component
        class Service:
            password: EnvStr[Literal["TEST_PASSWORD"]]

        app = await Application("test").scan(Service).ready_async()
        service = app.manager.get_instance(Service)

        assert service.password == "secret123"

        # 정리
        del os.environ["TEST_PASSWORD"]

    async def test_env_int_injection(self):
        """정수 환경변수 주입"""
        os.environ["TEST_PORT"] = "8080"

        @Component
        class Service:
            port: EnvInt[Literal["TEST_PORT"]]

        app = await Application("test").scan(Service).ready_async()
        service = app.manager.get_instance(Service)

        assert service.port == 8080
        assert isinstance(service.port, int)

        del os.environ["TEST_PORT"]

    async def test_env_float_injection(self):
        """실수 환경변수 주입"""
        os.environ["TEST_RATE"] = "0.75"

        @Component
        class Service:
            rate: EnvFloat[Literal["TEST_RATE"]]

        app = await Application("test").scan(Service).ready_async()
        service = app.manager.get_instance(Service)

        assert service.rate == 0.75
        assert isinstance(service.rate, float)

        del os.environ["TEST_RATE"]

    async def test_env_bool_injection(self):
        """불리언 환경변수 주입"""
        os.environ["TEST_DEBUG"] = "true"

        @Component
        class Service:
            debug: EnvBool[Literal["TEST_DEBUG"]]

        app = await Application("test").scan(Service).ready_async()
        service = app.manager.get_instance(Service)

        assert service.debug is True
        assert isinstance(service.debug, bool)

        del os.environ["TEST_DEBUG"]

    async def test_env_bool_various_values(self):
        """다양한 불리언 값 테스트"""
        true_values = ["true", "1", "yes", "on", "True", "TRUE", "YES"]
        false_values = ["false", "0", "no", "off", "False", "FALSE", "NO", ""]

        for val in true_values:
            os.environ["TEST_FLAG"] = val

            @Component
            class TrueService:
                flag: EnvBool[Literal["TEST_FLAG"]]

            app = await Application("test").scan(TrueService).ready_async()
            service = app.manager.get_instance(TrueService)
            assert service.flag is True, f"Expected True for '{val}'"

        for val in false_values:
            os.environ["TEST_FLAG"] = val

            @Component
            class FalseService:
                flag: EnvBool[Literal["TEST_FLAG"]]

            app = await Application("test").scan(FalseService).ready_async()
            service = app.manager.get_instance(FalseService)
            assert service.flag is False, f"Expected False for '{val}'"

        del os.environ["TEST_FLAG"]

    async def test_env_missing_variable(self):
        """환경변수가 없는 경우"""
        # 환경변수가 없는 경우 필드가 설정되지 않음
        if "NONEXISTENT_VAR" in os.environ:
            del os.environ["NONEXISTENT_VAR"]

        @Component
        class Service:
            missing: EnvStr[Literal["NONEXISTENT_VAR"]]

        app = await Application("test").scan(Service).ready_async()
        service = app.manager.get_instance(Service)

        # 환경변수가 없으면 해당 필드가 주입되지 않음
        assert not hasattr(service, "missing") or service.missing is None

    async def test_multiple_env_variables(self):
        """여러 환경변수 동시 주입"""
        os.environ["DB_HOST"] = "localhost"
        os.environ["DB_PORT"] = "5432"
        os.environ["DB_DEBUG"] = "true"

        @Component
        class DatabaseConfig:
            host: EnvStr[Literal["DB_HOST"]]
            port: EnvInt[Literal["DB_PORT"]]
            debug: EnvBool[Literal["DB_DEBUG"]]

        app = await Application("test").scan(DatabaseConfig).ready_async()
        config = app.manager.get_instance(DatabaseConfig)

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.debug is True

        del os.environ["DB_HOST"]
        del os.environ["DB_PORT"]
        del os.environ["DB_DEBUG"]

    async def test_env_with_regular_dependency(self):
        """환경변수와 일반 의존성 혼합"""
        os.environ["API_KEY"] = "my-api-key"

        @Component
        class Logger:
            def log(self, msg: str):
                return f"[LOG] {msg}"

        @Component
        class ApiClient:
            logger: Logger
            api_key: EnvStr[Literal["API_KEY"]]

            def call(self):
                return self.logger.log(f"Using key: {self.api_key}")

        app = await Application("test").scan(Logger, ApiClient).ready_async()
        client = app.manager.get_instance(ApiClient)

        assert client.api_key == "my-api-key"
        assert isinstance(client.logger, Logger)
        assert client.call() == "[LOG] Using key: my-api-key"

        del os.environ["API_KEY"]


class TestEnvEnumInjection:
    """EnvEnum 환경변수 주입 테스트"""

    async def test_env_enum_by_name(self, reset_container_manager):
        """Enum 이름으로 환경변수 주입"""
        os.environ["APP_ENV"] = "PROD"  # Enum 이름

        @Component
        class Service:
            env: EnvEnum[Environment, Literal["APP_ENV"]]

        app = await Application("test").scan(Service).ready_async()
        service = app.manager.get_instance(Service)

        assert service.env == Environment.PROD
        assert service.env.value == "prod"

        del os.environ["APP_ENV"]

    async def test_env_enum_by_value(self, reset_container_manager):
        """Enum 값으로 환경변수 주입"""
        os.environ["APP_ENV"] = "staging"  # Enum 값

        @Component
        class Service:
            env: EnvEnum[Environment, Literal["APP_ENV"]]

        app = await Application("test").scan(Service).ready_async()
        service = app.manager.get_instance(Service)

        assert service.env == Environment.STAGING
        assert service.env.value == "staging"

        del os.environ["APP_ENV"]

    async def test_env_enum_log_level(self, reset_container_manager):
        """로그 레벨 Enum 주입"""
        os.environ["LOG_LEVEL"] = "WARNING"

        @Component
        class LogConfig:
            level: EnvEnum[LogLevel, Literal["LOG_LEVEL"]]

        app = await Application("test").scan(LogConfig).ready_async()
        config = app.manager.get_instance(LogConfig)

        assert config.level == LogLevel.WARNING

        del os.environ["LOG_LEVEL"]

    async def test_env_enum_missing_variable(self, reset_container_manager):
        """Enum 환경변수가 없는 경우"""
        if "NONEXISTENT_ENV" in os.environ:
            del os.environ["NONEXISTENT_ENV"]

        @Component
        class Service:
            env: EnvEnum[Environment, Literal["NONEXISTENT_ENV"]]

        app = await Application("test").scan(Service).ready_async()
        service = app.manager.get_instance(Service)

        # 환경변수가 없으면 None
        assert not hasattr(service, "env") or service.env is None

    async def test_env_enum_invalid_value(self, reset_container_manager):
        """잘못된 Enum 값인 경우"""
        os.environ["APP_ENV"] = "invalid_value"

        @Component
        class Service:
            env: EnvEnum[Environment, Literal["APP_ENV"]]

        app = await Application("test").scan(Service).ready_async()
        service = app.manager.get_instance(Service)

        # 잘못된 값이면 None 반환 (기본값)
        assert not hasattr(service, "env") or service.env is None

        del os.environ["APP_ENV"]

    async def test_env_enum_with_other_env_types(self, reset_container_manager):
        """EnvEnum과 다른 Env 타입 혼합"""
        os.environ["APP_NAME"] = "MyApp"
        os.environ["APP_PORT"] = "8080"
        os.environ["APP_ENV"] = "prod"
        os.environ["APP_DEBUG"] = "false"

        @Component
        class AppConfig:
            name: EnvStr[Literal["APP_NAME"]]
            port: EnvInt[Literal["APP_PORT"]]
            env: EnvEnum[Environment, Literal["APP_ENV"]]
            debug: EnvBool[Literal["APP_DEBUG"]]

        app = await Application("test").scan(AppConfig).ready_async()
        config = app.manager.get_instance(AppConfig)

        assert config.name == "MyApp"
        assert config.port == 8080
        assert config.env == Environment.PROD
        assert config.debug is False

        del os.environ["APP_NAME"]
        del os.environ["APP_PORT"]
        del os.environ["APP_ENV"]
        del os.environ["APP_DEBUG"]

    async def test_env_enum_case_sensitivity(self, reset_container_manager):
        """Enum 이름은 대소문자 구분"""
        # LogLevel.DEBUG (이름) vs "DEBUG" (값)
        os.environ["LOG_LEVEL"] = "DEBUG"  # 이름과 값이 같음

        @Component
        class Config:
            level: EnvEnum[LogLevel, Literal["LOG_LEVEL"]]

        app = await Application("test").scan(Config).ready_async()
        config = app.manager.get_instance(Config)

        assert config.level == LogLevel.DEBUG

        del os.environ["LOG_LEVEL"]
