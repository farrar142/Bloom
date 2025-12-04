"""bloom.core.manager - 컨테이너 관리자"""

from __future__ import annotations

from typing import Any, TypeVar, overload

from .container import Container
from .scope import ScopeEnum
from .scope_manager import ScopeManager
from .exceptions import (
    ComponentNotFoundError,
    DuplicateComponentError,
    RequestScopeError,
    CallScopeError,
)


T = TypeVar("T")


class ContainerManager:
    """
    전역 컨테이너 관리자.

    모든 컴포넌트의 Container를 관리하고,
    스코프에 따른 인스턴스 생성/조회를 담당.
    """

    def __init__(self) -> None:
        # type → Container 매핑
        self._containers: dict[type, Container[Any]] = {}
        # name → Container 매핑 (동일 타입 여러 빈 구분용)
        self._named_containers: dict[str, Container[Any]] = {}
        # 스코프 관리자
        self._scope_manager = ScopeManager()
        # 초기화 완료 여부
        self._initialized = False

    @property
    def scope_manager(self) -> ScopeManager:
        """ScopeManager 접근"""
        return self._scope_manager

    # === Container 등록 ===

    def register[T](
        self,
        container: Container[T],
        *,
        allow_override: bool = False,
    ) -> None:
        """
        컨테이너 등록.

        Args:
            container: 등록할 컨테이너
            allow_override: 중복 등록 허용 여부
        """
        cls = container.target

        if cls in self._containers and not allow_override:
            raise DuplicateComponentError(cls)

        self._containers[cls] = container

        # 이름이 있으면 named 등록도
        if container.name:
            self._named_containers[container.name] = container

    def unregister(self, cls: type) -> bool:
        """
        컨테이너 등록 해제.

        Returns:
            해제 성공 여부
        """
        container = self._containers.pop(cls, None)
        if container and container.name:
            self._named_containers.pop(container.name, None)
        return container is not None

    # === Container 조회 ===

    def get_container[T](self, cls: type[T]) -> Container[T] | None:
        """타입으로 컨테이너 조회"""
        return self._containers.get(cls)

    def get_container_by_name(self, name: str) -> Container[Any] | None:
        """이름으로 컨테이너 조회"""
        return self._named_containers.get(name)

    def has_container(self, cls: type) -> bool:
        """컨테이너 존재 여부"""
        return cls in self._containers

    def get_all_containers(self) -> list[Container[Any]]:
        """모든 컨테이너 목록"""
        return list(self._containers.values())

    def get_containers_by_scope(self, scope: Scope) -> list[Container[Any]]:
        """특정 스코프의 컨테이너 목록"""
        return [c for c in self._containers.values() if c.scope == scope]

    # === 인스턴스 획득 ===

    @overload
    def get_instance[T](self, cls: type[T]) -> T: ...

    @overload
    def get_instance[T](self, cls: type[T], *, required: bool = True) -> T | None: ...

    def get_instance[T](self, cls: type[T], *, required: bool = True) -> T | None:
        """
        인스턴스 획득.

        스코프에 따라:
        - SINGLETON: 캐시된 인스턴스 반환 (없으면 생성)
        - REQUEST: 현재 요청의 인스턴스 반환 (없으면 생성)
        - CALL: 현재 호출의 인스턴스 반환 (없으면 생성)

        Args:
            cls: 컴포넌트 타입
            required: 필수 여부 (False면 없을 때 None 반환)

        Returns:
            인스턴스

        Raises:
            ComponentNotFoundError: 컴포넌트가 없고 required=True일 때
            RequestScopeError: REQUEST 스코프인데 요청 컨텍스트 밖일 때
            CallScopeError: CALL 스코프인데 핸들러 컨텍스트 밖일 때
        """
        container = self._containers.get(cls)

        if container is None:
            if required:
                raise ComponentNotFoundError(cls)
            return None

        return self._resolve_instance(container)

    def get_instance_by_name[T](self, name: str, cls: type[T] | None = None) -> T:
        """이름으로 인스턴스 획득"""
        container = self._named_containers.get(name)
        if container is None:
            raise ComponentNotFoundError(cls or type(None))
        return self._resolve_instance(container)

    def _resolve_instance[T](self, container: Container[T]) -> T:
        """컨테이너에서 인스턴스 resolve"""
        scope = container.scope
        cls = container.target

        # 이미 생성된 인스턴스가 있는지 확인
        existing = self._scope_manager.get_instance(cls, scope)
        if existing is not None:
            return existing

        # 스코프별 컨텍스트 확인
        if (
            scope == ScopeEnum.REQUEST
            and not self._scope_manager.is_in_request_context()
        ):
            raise RequestScopeError(cls)

        if scope == ScopeEnum.CALL and not self._scope_manager.is_in_call_context():
            raise CallScopeError(cls)

        # 새 인스턴스 생성 (동기 래퍼 - 실제론 async create_instance 호출 필요)
        import asyncio

        try:
            asyncio.get_running_loop()
            # 이미 이벤트 루프가 실행 중이면 async 메서드 사용 필요
            raise RuntimeError("Use async get_instance_async in async context")
        except RuntimeError as e:
            if "no running event loop" in str(e):
                # 이벤트 루프가 없으면 새로 실행
                instance = asyncio.run(self._create_and_cache_instance(container))
                return instance
            raise

    async def get_instance_async[T](
        self, cls: type[T], *, required: bool = True
    ) -> T | None:
        """
        비동기 인스턴스 획득.
        """
        container = self._containers.get(cls)

        if container is None:
            if required:
                raise ComponentNotFoundError(cls)
            return None

        return await self._resolve_instance_async(container)

    async def _resolve_instance_async[T](self, container: Container[T]) -> T:
        """비동기로 컨테이너에서 인스턴스 resolve"""
        scope = container.scope
        cls = container.target

        # 이미 생성된 인스턴스가 있는지 확인
        existing = self._scope_manager.get_instance(cls, scope)
        if existing is not None:
            return existing

        # 스코프별 컨텍스트 확인
        if (
            scope == ScopeEnum.REQUEST
            and not self._scope_manager.is_in_request_context()
        ):
            raise RequestScopeError(cls)

        if scope == ScopeEnum.CALL and not self._scope_manager.is_in_call_context():
            raise CallScopeError(cls)

        return await self._create_and_cache_instance(container)

    async def _create_and_cache_instance[T](self, container: Container[T]) -> T:
        """인스턴스 생성 및 캐싱"""
        instance = await container.create_instance(self)
        self._scope_manager.set_instance(container.target, instance, container.scope)
        return instance

    # === 초기화 / 종료 ===

    async def initialize(self) -> None:
        """
        모든 SINGLETON 컴포넌트 초기화.
        의존성 순서대로 생성.
        """
        if self._initialized:
            return

        # 토폴로지 정렬된 순서로 SINGLETON 생성
        from .resolver import DependencyResolver

        resolver = DependencyResolver(self)
        sorted_containers = resolver.topological_sort()

        for container in sorted_containers:
            if container.scope == ScopeEnum.SINGLETON:
                await self._create_and_cache_instance(container)

        self._initialized = True

    async def shutdown(self) -> None:
        """
        모든 SINGLETON 컴포넌트 정리.
        생성 역순으로 @PreDestroy 호출.
        """
        await self._scope_manager.destroy_singletons()
        self._initialized = False

    # === 유틸리티 ===

    def clear(self) -> None:
        """모든 컨테이너 및 인스턴스 초기화 (테스트용)"""
        self._containers.clear()
        self._named_containers.clear()
        self._scope_manager = ScopeManager()
        self._initialized = False

    def __repr__(self) -> str:
        return f"ContainerManager(containers={len(self._containers)})"


# === 전역 인스턴스 ===

_global_manager: ContainerManager | None = None


def get_container_manager() -> ContainerManager:
    """전역 ContainerManager 획득"""
    global _global_manager
    if _global_manager is None:
        _global_manager = ContainerManager()
    return _global_manager


def set_container_manager(manager: ContainerManager) -> None:
    """전역 ContainerManager 설정"""
    global _global_manager
    _global_manager = manager


def reset_container_manager() -> None:
    """전역 ContainerManager 초기화 (테스트용)"""
    global _global_manager
    if _global_manager:
        _global_manager.clear()
    _global_manager = None
