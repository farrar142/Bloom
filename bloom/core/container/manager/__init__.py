"""
Container Manager 모듈

컨테이너와 인스턴스를 관리하는 중앙 관리자입니다.

구조:
- ContainerManager (Facade) - 단일 진입점
  - registry: ContainerRegistry - 조회 담당
  - factory: ContainerFactory - 생성/분석 담당
  - lifecycle: ContainerLifecycle - 라이프사이클 담당
"""

from contextvars import ContextVar
from typing import Callable, TypeGuard, TYPE_CHECKING, overload

from .types import COMPONENT_ID, containers, get_container_registry
from .registry import ContainerRegistry
from .factory import ContainerFactory
from .lifecycle import ContainerLifecycle

if TYPE_CHECKING:
    from ..base import Container
    from ..factory import ConfigurationContainer


def is_container_registered[T](container_type: type[T]) -> TypeGuard[type[T]]:
    """타입이 컨테이너로 등록되어 있는지 확인"""
    return container_type in containers


class ContainerManager:
    """컨테이너 매니저 (Facade)

    Container는 순수 데이터 홀더이고, 로직은 하위 매니저들이 담당합니다.

    하위 매니저:
    - registry: 컨테이너/인스턴스 조회
    - factory: 컨테이너 생성/의존성 분석
    - lifecycle: 초기화/종료 관리

    사용 예:
        manager = get_container_manager()

        # 조회 (shortcut 메서드)
        container = manager.registry.container(type=MyService)
        instance = manager.registry.instance(type=MyService)

        # 또는 하위 매니저 직접 접근
        container = manager.registry.container(type=MyService)
        instance = manager.registry.instance(type=MyService)

        # 의존성 분석
        deps = manager.registry.factory.analyze_dependencies(container)

        # 라이프사이클
        await manager.initialize()  # shortcut
        await manager.lifecycle.initialize()  # 또는 직접 접근
    """

    def __init__(self) -> None:
        self._instances = dict[COMPONENT_ID, object]()

        # 하위 매니저 초기화
        self._registry = ContainerRegistry(self._instances)
        self._factory = ContainerFactory(self._instances, self._registry)
        self._lifecycle = ContainerLifecycle(
            self._instances, self._registry, self._factory
        )

    @property
    def instances(self) -> dict[COMPONENT_ID, object]:
        """인스턴스 저장소"""
        return self._instances

    @property
    def registry(self) -> ContainerRegistry:
        """컨테이너/인스턴스 조회 매니저"""
        return self._registry

    @property
    def factory_manager(self) -> ContainerFactory:
        """컨테이너 생성/분석 매니저"""
        return self._factory

    @property
    def lifecycle(self) -> ContainerLifecycle:
        """라이프사이클 매니저"""
        return self._lifecycle

    # =========================================================================
    # Shortcut 메서드 - lifecycle 위임
    # =========================================================================

    async def initialize(self) -> None:
        """컨테이너 초기화 (lifecycle.initialize 위임)"""
        await self._lifecycle.initialize()

    async def shutdown(self) -> None:
        """컨테이너 종료 (lifecycle.shutdown 위임)"""
        await self._lifecycle.shutdown()


# =============================================================================
# 전역 함수
# =============================================================================

container_manager_contexts: ContextVar[ContainerManager | None] = ContextVar(
    "container_manager", default=None
)


def get_container_manager() -> ContainerManager:
    """현재 컨테이너 매니저 조회"""
    manager = container_manager_contexts.get()
    if manager is None:
        manager = ContainerManager()
        container_manager_contexts.set(manager)
    return manager


# Re-export for convenience
__all__ = [
    "COMPONENT_ID",
    "containers",
    "get_container_registry",
    "is_container_registered",
    "ContainerManager",
    "ContainerRegistry",
    "ContainerFactory",
    "ContainerLifecycle",
    "get_container_manager",
]
