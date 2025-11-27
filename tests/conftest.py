"""테스트 공통 fixture 및 컴포넌트"""

from typing import Callable, TypeVar

import pytest
from bloom.core import Component, Factory, Handler
from bloom.core.manager import ContainerManager, set_current_manager

T = TypeVar("T", bound=type)


class FakeModule:
    """테스트용 가짜 모듈"""

    pass


def Module(module: type) -> Callable[[T], T]:
    """
    테스트용 모듈 데코레이터.
    클래스를 지정된 모듈에 자동으로 등록합니다.

    사용 예시:
        class MyModule:
            pass

        @Module(MyModule)
        @Component
        class ServiceA:
            pass

        @Module(MyModule)
        @Component
        class ServiceB:
            a: ServiceA

        app.scan_components(MyModule)
    """

    def decorator(cls: T) -> T:
        setattr(module, cls.__name__, cls)
        return cls

    return decorator


# === 공통 테스트용 컴포넌트 (모듈 레벨에서 정의) ===


@Component
class Repository:
    """테스트용 Repository"""

    pass


@Component
class Service:
    """Repository 의존성이 있는 Service"""

    repository: Repository


class ExternalService:
    """Factory로 생성되는 외부 서비스"""

    def __init__(self, repo: Repository):
        self.repo = repo


@Component
class Configuration:
    """Factory 메서드를 포함하는 설정 클래스"""

    @Factory
    def create_external_service(self, repo: Repository) -> ExternalService:
        return ExternalService(repo)


@Component
class Controller:
    """Handler 메서드를 포함하는 컨트롤러"""

    @Handler(("GET", "/users"))
    def get_users(self) -> list[str]:
        return ["user1", "user2"]

    @Handler(ValueError)
    def handle_error(self, e: ValueError) -> str:
        return str(e)

    @Handler("test_key")
    def do_something(self) -> str:
        return "done"


# === Fixtures ===


@pytest.fixture(autouse=True)
def reset_container_manager():
    """각 테스트 전후로 ContainerManager 초기화"""
    # 새로운 테스트용 manager 생성 및 설정
    manager = ContainerManager("test")
    set_current_manager(manager)
    yield manager
    # 테스트 후 정리
    set_current_manager(None)
