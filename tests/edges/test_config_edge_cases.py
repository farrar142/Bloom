"""Configuration 엣지 케이스 테스트"""

import os
import pytest
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

from bloom import Application, Component
from bloom.config import ConfigurationProperties


class TestMissingConfigValues:
    """누락된 설정값 테스트"""

    def test_missing_required_config_uses_default(self, reset_container_manager):
        """필수 설정값 누락 시 기본값 사용"""

        @ConfigurationProperties("app.database")
        @dataclass
        class DatabaseConfig:
            host: str = "localhost"  # 기본값 있음
            port: int = 5432  # 기본값 있음

        @Component
        class Service:
            config: DatabaseConfig

        app = Application("missing_config")
        app.load_config({}, source_type="dict")  # 빈 설정
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.host == "localhost"
        assert service.config.port == 5432

    def test_optional_config_with_none(self, reset_container_manager):
        """Optional 설정값이 None인 경우"""

        @ConfigurationProperties("app.optional")
        @dataclass
        class OptionalConfig:
            value: Optional[str] = None

        @Component
        class Service:
            config: OptionalConfig

        app = Application("optional_config")
        app.load_config({}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.value is None


class TestConfigDefaultValues:
    """설정 기본값 테스트"""

    def test_default_values_used(self, reset_container_manager):
        """기본값이 사용됨"""

        @ConfigurationProperties("app.defaults")
        @dataclass
        class DefaultConfig:
            host: str = "localhost"
            port: int = 8080
            debug: bool = False

        @Component
        class Service:
            config: DefaultConfig

        app = Application("default_config")
        app.load_config({}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.host == "localhost"
        assert service.config.port == 8080
        assert service.config.debug is False

    def test_partial_override(self, reset_container_manager):
        """일부 값만 오버라이드"""

        @ConfigurationProperties("app.partial")
        @dataclass
        class PartialConfig:
            host: str = "localhost"
            port: int = 8080

        @Component
        class Service:
            config: PartialConfig

        app = Application("partial_config")
        app.load_config({"app": {"partial": {"port": 9090}}}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.host == "localhost"  # 기본값
        assert service.config.port == 9090  # 오버라이드


class TestNestedConfig:
    """중첩된 설정 테스트"""

    def test_deeply_nested_config(self, reset_container_manager):
        """깊이 중첩된 설정"""

        @dataclass
        class InnerConfig:
            value: str = "inner"

        @ConfigurationProperties("app.outer.middle")
        @dataclass
        class NestedConfig:
            inner: InnerConfig = field(default_factory=InnerConfig)
            name: str = "default"

        @Component
        class Service:
            config: NestedConfig

        app = Application("nested_config")
        app.load_config(
            {"app": {"outer": {"middle": {"name": "custom", "inner": {"value": "custom_inner"}}}}},
            source_type="dict",
        )
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.name == "custom"
        assert service.config.inner.value == "custom_inner"


class TestEnvVarSubstitution:
    """환경 변수 치환 테스트"""

    def test_env_var_with_default(self, reset_container_manager, monkeypatch):
        """환경 변수가 없으면 기본값 사용"""

        # 환경 변수 설정 안 함
        monkeypatch.delenv("MY_HOST", raising=False)

        @ConfigurationProperties("app.env")
        @dataclass
        class EnvConfig:
            host: str = "${MY_HOST:default_host}"

        @Component
        class Service:
            config: EnvConfig

        app = Application("env_default")
        app.load_config({"app": {"env": {"host": "${MY_HOST:default_host}"}}}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.host == "default_host"

    def test_env_var_substitution(self, reset_container_manager, monkeypatch):
        """환경 변수 치환"""

        monkeypatch.setenv("MY_HOST", "env_host")

        @ConfigurationProperties("app.env")
        @dataclass
        class EnvConfig:
            host: str = "localhost"

        @Component
        class Service:
            config: EnvConfig

        app = Application("env_sub")
        app.load_config({"app": {"env": {"host": "${MY_HOST}"}}}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.host == "env_host"


class TestTypeConversion:
    """타입 변환 테스트"""

    def test_string_to_int(self, reset_container_manager):
        """문자열 → int 변환"""

        @ConfigurationProperties("app.types")
        @dataclass
        class TypeConfig:
            port: int = 8080

        @Component
        class Service:
            config: TypeConfig

        app = Application("type_int")
        app.load_config({"app": {"types": {"port": "9090"}}}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.port == 9090
        assert isinstance(service.config.port, int)

    def test_string_to_bool(self, reset_container_manager):
        """문자열 → bool 변환"""

        @ConfigurationProperties("app.types")
        @dataclass
        class BoolConfig:
            enabled: bool = False

        @Component
        class Service:
            config: BoolConfig

        app = Application("type_bool")
        app.load_config({"app": {"types": {"enabled": "true"}}}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.enabled is True

    def test_string_to_float(self, reset_container_manager):
        """문자열 → float 변환"""

        @ConfigurationProperties("app.types")
        @dataclass
        class FloatConfig:
            rate: float = 1.0

        @Component
        class Service:
            config: FloatConfig

        app = Application("type_float")
        app.load_config({"app": {"types": {"rate": "0.5"}}}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.rate == 0.5

    def test_list_config(self, reset_container_manager):
        """리스트 설정"""

        @ConfigurationProperties("app.list")
        @dataclass
        class ListConfig:
            items: list[str] = field(default_factory=list)

        @Component
        class Service:
            config: ListConfig

        app = Application("type_list")
        app.load_config({"app": {"list": {"items": ["a", "b", "c"]}}}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.items == ["a", "b", "c"]


class TestEnumConfig:
    """Enum 설정 테스트"""

    def test_enum_from_string(self, reset_container_manager):
        """문자열 → Enum 변환"""

        class LogLevel(Enum):
            DEBUG = "debug"
            INFO = "info"
            ERROR = "error"

        @ConfigurationProperties("app.logging")
        @dataclass
        class LogConfig:
            level: LogLevel = LogLevel.INFO

        @Component
        class Service:
            config: LogConfig

        app = Application("enum_config")
        app.load_config({"app": {"logging": {"level": "DEBUG"}}}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.level == LogLevel.DEBUG

    def test_enum_case_insensitive(self, reset_container_manager):
        """Enum 대소문자 무시"""

        class Status(Enum):
            ACTIVE = "active"
            INACTIVE = "inactive"

        @ConfigurationProperties("app.status")
        @dataclass
        class StatusConfig:
            status: Status = Status.INACTIVE

        @Component
        class Service:
            config: StatusConfig

        app = Application("enum_case")
        app.load_config({"app": {"status": {"status": "active"}}}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.status == Status.ACTIVE


class TestEmptyConfig:
    """빈 설정 테스트"""

    def test_empty_prefix(self, reset_container_manager):
        """빈 prefix"""

        @ConfigurationProperties("")
        @dataclass
        class RootConfig:
            name: str = "root"

        @Component
        class Service:
            config: RootConfig

        app = Application("empty_prefix")
        app.load_config({"name": "custom_root"}, source_type="dict")
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.name == "custom_root"

    def test_no_config_loaded(self, reset_container_manager):
        """설정 파일 로드 안 함"""

        @ConfigurationProperties("app")
        @dataclass
        class AppConfig:
            name: str = "default_app"

        @Component
        class Service:
            config: AppConfig

        app = Application("no_config")
        # load_config 호출 안 함
        app.scan(Service).ready()

        service = app.manager.get_instance(Service)
        assert service.config.name == "default_app"
