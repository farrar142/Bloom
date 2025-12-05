"""Configuration properties decorator and element"""

from typing import Any, Callable, TypeVar, overload

T = TypeVar("T", bound=type)


@overload
def ConfigurationProperties(cls_or_prefix: T) -> T:
    """
    @ConfigurationProperties 형태 (prefix 없이 사용)

    사용 예시:
        @ConfigurationProperties
        @dataclass
        class AppConfig:
            name: str = "MyApp"
    """
    ...


@overload
def ConfigurationProperties(cls_or_prefix: str = "") -> Callable[[T], T]:
    """
    @ConfigurationProperties("app.database") 형태 (prefix 지정)

    사용 예시:
        @ConfigurationProperties("app.database")
        @dataclass
        class DatabaseConfig:
            host: str = "localhost"
    """
    ...


def ConfigurationProperties(cls_or_prefix: T | str = "") -> T | Callable[[T], T]:
    """
    설정 속성 클래스를 정의하는 데코레이터

    Spring Boot의 @ConfigurationProperties와 유사하게 동작합니다.
    dataclass와 Pydantic BaseModel 모두 지원합니다.

    사용 예시:
        # dataclass 사용
        @ConfigurationProperties("app.database")
        @dataclass
        class DatabaseConfig:
            host: str = "localhost"
            port: int = 5432
            username: str = ""
            password: str = ""

        # Pydantic 사용
        @ConfigurationProperties("app.redis")
        class RedisConfig(BaseModel):
            host: str = "localhost"
            port: int = 6379

        # Component에서 주입
        @Component
        class DatabaseService:
            config: DatabaseConfig  # 자동으로 app.database.* 설정 바인딩
    """
    # @ConfigurationProperties 형태 (prefix 없이 사용)
    if isinstance(cls_or_prefix, type):
        cls = cls_or_prefix
        return _apply_configuration_properties(cls, "")  # type: ignore

    # @ConfigurationProperties("prefix") 형태
    prefix = cls_or_prefix

    def decorator(cls: T) -> T:
        return _apply_configuration_properties(cls, prefix)  # type: ignore

    return decorator


def _apply_configuration_properties(cls: T, prefix: str) -> T:
    """ConfigurationProperties 데코레이터 적용

    클래스에 __bloom_configuration_properties__ 메타데이터를 추가합니다.
    """
    cls.__bloom_configuration_properties__ = True  # type: ignore
    cls.__bloom_configuration_properties_prefix__ = prefix  # type: ignore
    return cls


def is_configuration_properties(cls: type) -> bool:
    """주어진 클래스가 ConfigurationProperties인지 확인"""
    return getattr(cls, "__bloom_configuration_properties__", False)


def get_prefix(cls: type) -> str:
    """ConfigurationProperties의 prefix 반환"""
    return getattr(cls, "__bloom_configuration_properties_prefix__", "")
