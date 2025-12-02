"""Container Orchestrator - 컨테이너 초기화 오케스트레이션"""

import asyncio
import concurrent.futures
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .container import Container
    from .manager import ContainerManager

from .exceptions import CircularDependencyError
from .utils import topological_sort, group_by_dependency_level


class ContainerOrchestrator:
    """
    컨테이너 초기화 오케스트레이터

    컨테이너들을 토폴로지컬 순서로 정렬하고 초기화합니다.
    Factory Chain 검증, 순환 의존성 감지, 병렬 초기화를 지원합니다.

    모든 초기화 흐름은 async로 통일:
    - initialize_async(): 동기/비동기 @PostConstruct 모두 처리
    - 동기 환경에서는 asyncio.run()으로 호출
    """

    def __init__(self, manager: "ContainerManager"):
        self.manager = manager
        self.initialized_containers: list["Container"] = []

    async def initialize_async(self, parallel: bool = False) -> list["Container"]:
        """
        모든 컨테이너를 초기화 (동기/비동기 @PostConstruct 모두 처리)

        동기 환경에서는 asyncio.run()으로 호출합니다.

        Args:
            parallel: True면 의존성 레벨별로 병렬 초기화 수행

        Returns:
            초기화된 컨테이너 목록 (PreDestroy 역순 호출용)
        """
        self.initialized_containers = []

        if parallel:
            await self._initialize_parallel_async()
        else:
            await self._initialize_sequential_async()

        self.manager.lifecycle._started = True
        return self.initialized_containers

    async def _initialize_sequential_async(self) -> None:
        """모든 컨테이너를 토폴로지컬 순서로 초기화 (순차적, 동기/비동기 @PostConstruct 모두 처리)

        1. 모든 컨테이너를 의존성 그래프로 토폴로지 정렬
        2. 같은 타입의 Factory가 여러 개면 @Order 또는 의존성으로 순서 결정
        3. 정렬된 순서대로 초기화 - Factory Chain은 자동으로 처리됨

        순환 의존성이 감지되면 의존성 그래프를 파일로 저장합니다.
        """
        all_containers = self._collect_all_containers()
        self._validate_factory_chains(all_containers)
        self._validate_singleton_only_handlers(all_containers)

        try:
            sorted_containers = topological_sort(all_containers)
        except CircularDependencyError as e:
            self._save_circular_dependency_graph(e)
            raise

        for container in sorted_containers:
            result = await self._initialize_single_container_async(container)
            if result:
                container, instance = result
                # PostConstruct에서 자기 자신의 Factory 메서드를 호출할 수 있도록
                # PostConstruct 실행 전에 인스턴스를 먼저 등록
                self._register_initialized_container(container, instance)

    async def _initialize_parallel_async(self) -> None:
        """
        모든 컨테이너를 레벨별로 병렬 초기화 (동기/비동기 @PostConstruct 모두 처리)

        의존성 레벨이 같은 컨테이너들을 asyncio.gather로 동시 초기화합니다.
        - Level 0: 의존성 없는 컨테이너들 (동시 초기화)
        - Level 1: Level 0 완료 후, Level 0에만 의존하는 컨테이너들 (동시 초기화)
        - ...

        Note: Factory Chain의 경우 같은 타입의 Factory들이 순차적으로 실행됩니다.
              병렬 초기화에서는 Factory Chain이 올바르게 동작하지 않을 수 있습니다.
              복잡한 Factory Chain이 있는 경우 순차 초기화(parallel=False)를 권장합니다.

        순환 의존성이 감지되면 의존성 그래프를 파일로 저장합니다.
        """
        all_containers = self._collect_all_containers()
        self._validate_factory_chains(all_containers)
        self._validate_singleton_only_handlers(all_containers)

        try:
            levels = group_by_dependency_level(all_containers)
        except CircularDependencyError as e:
            self._save_circular_dependency_graph(e)
            raise

        for level_containers in levels:
            if not level_containers:
                continue

            # asyncio.gather로 레벨별 병렬 초기화
            results = await asyncio.gather(
                *[
                    self._initialize_single_container_async(container)
                    for container in level_containers
                ]
            )

            for result in results:
                if result:
                    container, instance = result
                    self._register_initialized_container(container, instance)

    def _collect_all_containers(self) -> list["Container"]:
        """모든 컨테이너를 리스트로 수집"""
        all_containers: list["Container"] = []
        for containers in self.manager.get_all_containers().values():
            all_containers.extend(containers)
        return all_containers

    def _validate_factory_chains(self, all_containers: list["Container"]) -> None:
        """
        Factory Chain 유효성 검증 및 중간 Factory 마킹

        1. Ambiguous Provider 패턴 감지 → 에러
        2. Factory Chain의 중간 Factory들을 마킹 (마지막 Factory만 PostConstruct 호출)
        """
        from .utils import detect_factory_chains, validate_factory_chains

        # Factory Chain 감지
        chains = detect_factory_chains(all_containers)

        # Ambiguous Provider 검증 (에러 발생 가능)
        validate_factory_chains(chains)

        # Factory Chain의 중간 Factory들을 마킹
        # 마지막 Factory를 제외한 나머지는 intermediate
        for target_type, factory_chain in chains.items():
            if len(factory_chain) > 1:
                for factory in factory_chain[:-1]:
                    factory._is_chain_intermediate = True

    def _validate_singleton_only_handlers(
        self, all_containers: list["Container"]
    ) -> None:
        """
        SINGLETON-only 핸들러가 CALL/REQUEST 스코프에서 사용되는지 검증

        @Factory, @EventListener, @Task 등은 SINGLETON 스코프에서만 사용 가능합니다.
        CALL 또는 REQUEST 스코프 컴포넌트에서 사용되면 InvalidScopeError가 발생합니다.
        """
        from .container.callable import CallableContainer

        for container in all_containers:
            if isinstance(container, CallableContainer):
                container.validate_owner_scope()

    async def _initialize_single_container_async(
        self, container: "Container"
    ) -> tuple["Container", Any] | None:
        """단일 컨테이너 초기화 (동기/비동기 @PostConstruct 모두 처리)

        Returns:
            (container, instance) 튜플 또는 @Scope(CALL/REQUEST) 컴포넌트면 None
        """
        from .container.factory import FactoryContainer

        # CALL/REQUEST 스코프는 즉시 초기화하지 않음 (접근 시 생성)
        if self._is_lazy_scope(container):
            return None

        instance = container.initialize_instance()

        # Factory Chain 중간 Factory는 @PostConstruct 호출하지 않음
        # (마지막 Factory만 호출)
        if isinstance(container, FactoryContainer) and container._is_chain_intermediate:
            return (container, instance)

        # @PostConstruct에서 자기 자신의 Factory 메서드를 호출할 수 있도록
        # PostConstruct 실행 전에 인스턴스를 먼저 등록
        self.manager.set_instance(container.target, instance)

        # @PostConstruct 호출 (동기/비동기 모두 처리)
        await self.manager.lifecycle.invoke_post_construct_async(container, instance)

        return (container, instance)

    async def finalize_async(
        self, initialized_containers: list["Container"] | None = None
    ) -> None:
        """
        모든 SINGLETON 컨테이너의 @PreDestroy 메서드들을 역순으로 호출

        Application.shutdown_async()에서 호출됩니다.

        Args:
            initialized_containers: 초기화 순서대로 정렬된 컨테이너 리스트
                                   (None이면 self.initialized_containers 사용)
        """
        containers = initialized_containers or self.initialized_containers
        if not containers:
            return

        await self.manager.lifecycle.invoke_all_pre_destroy_async(containers)
        self.manager.lifecycle._started = False

    def _is_lazy_scope(self, container: "Container") -> bool:
        """컨테이너가 CALL 또는 REQUEST 스코프인지 확인

        이 스코프들은 ready() 시점에 초기화되지 않고, 필드 접근 시점에 초기화됩니다.
        Container는 Element를 담기만 하고, 해석은 Manager에서 합니다.
        """
        from .container.element import Scope

        scope, _ = self.manager.get_container_scope(container)
        return scope in (Scope.CALL, Scope.REQUEST)

    def _register_initialized_container(
        self, container: "Container", instance: Any
    ) -> None:
        """초기화된 컨테이너를 등록

        Note: 인스턴스는 이미 _initialize_single_container_async에서 등록됨
              (PostConstruct에서 자기 Factory 호출 지원)
        """
        # 이미 등록되어 있지 않으면 등록 (중복 방지)
        if not self.manager.get_instances(container.target):
            self.manager.set_instance(container.target, instance)
        self.initialized_containers.append(container)

    def _save_circular_dependency_graph(self, error: CircularDependencyError) -> None:
        """순환 의존성 발생 시 의존성 그래프를 파일로 저장

        Args:
            error: CircularDependencyError 예외 객체
        """
        from datetime import datetime
        from bloom.log.graph import generate_dependency_graph

        # 파일명 생성: circular-dependency-{timestamp}.txt
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"circular-dependency-{timestamp}.txt"

        # 그래프 생성
        graph_content = generate_dependency_graph(
            self.manager, filename, include_cycle_info=True, cycle_error=error
        )

        # 파일 저장
        with open(filename, "w", encoding="utf-8") as f:
            f.write(graph_content)

        # 예외에 저장 경로 기록
        error.graph_saved_path = filename

        print(f"\n{'=' * 60}")
        print("⚠️  CIRCULAR DEPENDENCY DETECTED")
        print("=" * 60)
        print(f"\nDependency graph saved to: {filename}")
        print("\n" + error.get_cycle_info())
        print("=" * 60 + "\n")
