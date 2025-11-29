"""테스트 공통 fixture 및 컴포넌트"""

import pytest
from bloom.core import Component, Factory, Handler
from bloom.core.manager import ContainerManager, set_current_manager


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
class HandlerTestController:
    """Handler 메서드를 포함하는 컨트롤러 (테스트용)"""

    @Handler
    def get_users(self) -> list[str]:
        return ["user1", "user2"]

    @Handler
    def handle_error(self, e: ValueError) -> str:
        return str(e)

    @Handler
    def do_something(self) -> str:
        return "done"


# === Fixtures ===


@pytest.fixture(autouse=True)
def reset_container_manager():
    """각 테스트 전후로 ContainerManager 및 파라미터 리졸버 캐시 초기화"""
    from bloom.web.params import get_default_registry

    # 새로운 테스트용 manager 생성 및 설정
    manager = ContainerManager("test")
    set_current_manager(manager)
    # 파라미터 리졸버 캐시 초기화
    get_default_registry().clear_cache()
    yield manager
    # 테스트 후 정리
    set_current_manager(None)
    get_default_registry().clear_cache()
