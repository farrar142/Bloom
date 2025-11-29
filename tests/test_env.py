"""환경변수 주입 테스트"""

import os
import pytest
from typing import Literal

from bloom import Application, Component
from bloom.config.env import Env, EnvStr, EnvInt, EnvFloat, EnvBool


class TestEnvInjection:
    """환경변수 주입 테스트"""

    def test_env_str_injection(self):
        """문자열 환경변수 주입"""
        os.environ["TEST_PASSWORD"] = "secret123"

        @Component
        class Service:
            password: EnvStr[Literal["TEST_PASSWORD"]]

        app = Application("test").scan(Service).ready()
        service = app.manager.get_instance(Service)

        assert service.password == "secret123"

        # 정리
        del os.environ["TEST_PASSWORD"]

    def test_env_int_injection(self):
        """정수 환경변수 주입"""
        os.environ["TEST_PORT"] = "8080"

        @Component
        class Service:
            port: EnvInt[Literal["TEST_PORT"]]

        app = Application("test").scan(Service).ready()
        service = app.manager.get_instance(Service)

        assert service.port == 8080
        assert isinstance(service.port, int)

        del os.environ["TEST_PORT"]

    def test_env_float_injection(self):
        """실수 환경변수 주입"""
        os.environ["TEST_RATE"] = "0.75"

        @Component
        class Service:
            rate: EnvFloat[Literal["TEST_RATE"]]

        app = Application("test").scan(Service).ready()
        service = app.manager.get_instance(Service)

        assert service.rate == 0.75
        assert isinstance(service.rate, float)

        del os.environ["TEST_RATE"]

    def test_env_bool_injection(self):
        """불리언 환경변수 주입"""
        os.environ["TEST_DEBUG"] = "true"

        @Component
        class Service:
            debug: EnvBool[Literal["TEST_DEBUG"]]

        app = Application("test").scan(Service).ready()
        service = app.manager.get_instance(Service)

        assert service.debug is True
        assert isinstance(service.debug, bool)

        del os.environ["TEST_DEBUG"]

    def test_env_bool_various_values(self):
        """다양한 불리언 값 테스트"""
        true_values = ["true", "1", "yes", "on", "True", "TRUE", "YES"]
        false_values = ["false", "0", "no", "off", "False", "FALSE", "NO", ""]

        for val in true_values:
            os.environ["TEST_FLAG"] = val

            @Component
            class TrueService:
                flag: EnvBool[Literal["TEST_FLAG"]]

            app = Application("test").scan(TrueService).ready()
            service = app.manager.get_instance(TrueService)
            assert service.flag is True, f"Expected True for '{val}'"

        for val in false_values:
            os.environ["TEST_FLAG"] = val

            @Component
            class FalseService:
                flag: EnvBool[Literal["TEST_FLAG"]]

            app = Application("test").scan(FalseService).ready()
            service = app.manager.get_instance(FalseService)
            assert service.flag is False, f"Expected False for '{val}'"

        del os.environ["TEST_FLAG"]

    def test_env_missing_variable(self):
        """환경변수가 없는 경우"""
        # 환경변수가 없는 경우 필드가 설정되지 않음
        if "NONEXISTENT_VAR" in os.environ:
            del os.environ["NONEXISTENT_VAR"]

        @Component
        class Service:
            missing: EnvStr[Literal["NONEXISTENT_VAR"]]

        app = Application("test").scan(Service).ready()
        service = app.manager.get_instance(Service)

        # 환경변수가 없으면 해당 필드가 주입되지 않음
        assert not hasattr(service, "missing") or service.missing is None

    def test_multiple_env_variables(self):
        """여러 환경변수 동시 주입"""
        os.environ["DB_HOST"] = "localhost"
        os.environ["DB_PORT"] = "5432"
        os.environ["DB_DEBUG"] = "true"

        @Component
        class DatabaseConfig:
            host: EnvStr[Literal["DB_HOST"]]
            port: EnvInt[Literal["DB_PORT"]]
            debug: EnvBool[Literal["DB_DEBUG"]]

        app = Application("test").scan(DatabaseConfig).ready()
        config = app.manager.get_instance(DatabaseConfig)

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.debug is True

        del os.environ["DB_HOST"]
        del os.environ["DB_PORT"]
        del os.environ["DB_DEBUG"]

    def test_env_with_regular_dependency(self):
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

        app = Application("test").scan(Logger, ApiClient).ready()
        client = app.manager.get_instance(ApiClient)

        assert client.api_key == "my-api-key"
        assert isinstance(client.logger, Logger)
        assert client.call() == "[LOG] Using key: my-api-key"

        del os.environ["API_KEY"]
