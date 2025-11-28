"""bloom Application"""

import asyncio
import concurrent.futures
from typing import TYPE_CHECKING, Any
from pathlib import Path

if TYPE_CHECKING:
    from .core.container import Container, FactoryContainer
    from .web.messaging.manager import WebSocketManager

from .core.exceptions import CircularDependencyError
from .core.manager import ContainerManager, set_current_manager, try_get_current_manager
from .core.utils import topological_sort, group_by_dependency_level
from .web.router import Router
from .web.asgi import ASGIApplication
from .config.manager import ConfigManager


class Application:
    """
    bloom 애플리케이션 진입점

    사용 예시:
        app = Application("my_app")
        app.scan(MyModule)
        app.ready()

        # ASGI 서버로 실행
        # uvicorn main:app.asgi
    """

    def __init__(self, name: str, manager: "ContainerManager | None" = None):
        self.name = name
        # 외부에서 manager를 전달받거나, 현재 활성 manager 사용, 또는 새로 생성
        if manager is not None:
            self.manager = manager
        elif existing := try_get_current_manager():
            self.manager = existing
            self.manager.app_name = name  # 이름 업데이트
        else:
            self.manager = ContainerManager(name)
        self._router: Router | None = None
        self._asgi: ASGIApplication | None = None
        self._is_ready = False
        self._config_manager = ConfigManager()
        self._websocket_manager: "WebSocketManager | None" = None
        self._initialized_containers: list["Container"] = []
        # 생성 시점에 현재 매니저로 설정 (데코레이터 자동 등록 지원)
        set_current_manager(self.manager)

    @property
    def router(self) -> Router:
        """Router 인스턴스 반환"""
        if self._router is None:
            self._router = Router(self.manager)
        return self._router

    @property
    def asgi(self) -> ASGIApplication:
        """
        ASGI 애플리케이션 반환 (uvicorn 등에서 사용)

        멀티 워커 환경에서는 각 워커가 lifespan.startup 이벤트 시
        자동으로 Application.ready()를 호출합니다.

        사용 예시:
            app = Application("my_app").scan(module)
            # uvicorn main:app.asgi --workers 4
        """
        if self._asgi is None:
            self._asgi = ASGIApplication(self.router, application=self)
        return self._asgi

    @property
    def websocket_manager(self) -> "WebSocketManager":
        """
        WebSocketManager 인스턴스 반환

        @EnableWebSocket이 붙은 컴포넌트가 있으면 WebSocket이 활성화됩니다.
        """
        if self._websocket_manager is None:
            from .web.messaging.manager import WebSocketManager

            self._websocket_manager = WebSocketManager(self.manager)
        return self._websocket_manager

    def load_config(
        self,
        source: str | Path | dict[str, Any] | None = None,
        source_type: str = "auto",
    ) -> "Application":
        """
        설정 로드

        Args:
            source: 설정 소스 (파일 경로, dict 등)
            source_type: 소스 타입 ("yaml", "json", "env", "dict", "auto")

        Returns:
            self (메서드 체이닝 지원)

        사용 예시:
            app.load_config("config/application.yaml")
            app.load_config({"app": {"name": "MyApp"}}, source_type="dict")
            app.load_config(source_type="env")  # 환경 변수만 로드
        """
        self._config_manager.load_config(source, source_type)
        return self

    def scan(self, *modules: object) -> "Application":
        """
        모듈들을 스캔하여 컴포넌트 수집

        Args:
            *modules: 스캔할 모듈들

        Returns:
            self (메서드 체이닝 지원)
        """
        # 스캔 중 현재 매니저 설정
        set_current_manager(self.manager)
        for module in modules:
            self.manager.scan_components(module)
        return self

    def ready(self, parallel: bool = False) -> "Application":
        """
        애플리케이션 초기화 완료

        1. 컴포넌트 의존성 정렬 및 초기화
        2. 라우터에 핸들러 등록
        3. WebSocket 초기화 (@EnableWebSocket이 있는 경우)

        Args:
            parallel: True면 의존성 레벨별로 병렬 초기화 수행
                     같은 레벨의 컨테이너들을 동시에 초기화하여 시작 시간 단축

        Returns:
            self (메서드 체이닝 지원)
        """
        if self._is_ready:
            return self

        # 현재 매니저 설정
        set_current_manager(self.manager)

        # 1. ConfigurationProperties 바인딩
        self._bind_configuration_properties()

        # 2. 컨테이너 초기화
        if parallel:
            self._initialize_containers_parallel()
        else:
            self._initialize_containers()

        # 3. 라우터 초기화
        self.router.collect_routes()

        # 4. WebSocket 초기화 (@EnableWebSocket 감지)
        self._initialize_websocket()

        self._is_ready = True
        return self

    def _bind_configuration_properties(self) -> None:
        """ConfigurationProperties를 바인딩하여 인스턴스 생성"""
        self._config_manager.bind_configuration_properties(self.manager)

    def _initialize_websocket(self) -> None:
        """WebSocket 초기화 (@EnableWebSocket 컴포넌트가 있는 경우)"""
        self.websocket_manager.initialize(self.manager)

    def _validate_factory_chains(self, all_containers: list["Container"]) -> None:
        """
        Factory Chain 유효성 검증 및 중간 Factory 마킹

        1. Ambiguous Provider 패턴 감지 → 에러
        2. Factory Chain의 중간 Factory들을 마킹 (마지막 Factory만 PostConstruct 호출)
        """
        from bloom.core.container import FactoryContainer
        from bloom.core.utils import detect_factory_chains, validate_factory_chains

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

    def _initialize_containers(self) -> None:
        """모든 컨테이너를 토폴로지컬 순서로 초기화 (순차적)

        1. 모든 컨테이너를 의존성 그래프로 토폴로지 정렬
        2. 같은 타입의 Factory가 여러 개면 @Order 또는 의존성으로 순서 결정
        3. 정렬된 순서대로 초기화 - Factory Chain은 자동으로 처리됨

        순환 의존성이 감지되면 의존성 그래프를 파일로 저장합니다.
        """
        from bloom.core.lazy import is_lazy_component

        # 모든 컨테이너를 리스트로 변환
        all_containers: list["Container"] = []
        for containers in self.manager.get_all_containers().values():
            all_containers.extend(containers)

        # Factory Chain 유효성 검증 (Ambiguous Provider 감지)
        self._validate_factory_chains(all_containers)

        # 모든 컨테이너를 토폴로지컬 정렬 (Factory Chain 포함)
        # topological_sort가 같은 타입 내에서 @Order로 정렬
        try:
            sorted_containers = topological_sort(all_containers)
        except CircularDependencyError as e:
            # 순환 의존성 발생 시 그래프 저장
            self._save_circular_dependency_graph(e)
            raise

        # 정렬된 순서로 초기화 (초기화 순서 저장)
        self._initialized_containers = []

        for container in sorted_containers:
            # @Lazy 컴포넌트는 즉시 초기화하지 않음 (접근 시 LazyProxy가 초기화)
            if is_lazy_component(container):
                continue

            instance = container.initialize_instance()
            self.manager.set_instance(container.target, instance)
            self._initialized_containers.append(container)

    def _save_circular_dependency_graph(
        self, error: CircularDependencyError
    ) -> None:
        """순환 의존성 발생 시 의존성 그래프를 파일로 저장

        Args:
            error: CircularDependencyError 예외 객체
        """
        from datetime import datetime
        from bloom.logging.graph import generate_dependency_graph

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

    def _initialize_containers_parallel(self) -> None:
        """
        모든 컨테이너를 레벨별로 병렬 초기화

        의존성 레벨이 같은 컨테이너들을 ThreadPoolExecutor로 동시 초기화합니다.
        - Level 0: 의존성 없는 컨테이너들 (동시 초기화)
        - Level 1: Level 0 완료 후, Level 0에만 의존하는 컨테이너들 (동시 초기화)
        - ...

        Note: Factory Chain의 경우 같은 타입의 Factory들이 순차적으로 실행됩니다.
              병렬 초기화에서는 Factory Chain이 올바르게 동작하지 않을 수 있습니다.
              복잡한 Factory Chain이 있는 경우 순차 초기화(parallel=False)를 권장합니다.

        순환 의존성이 감지되면 의존성 그래프를 파일로 저장합니다.
        """
        from bloom.core.lazy import is_lazy_component

        # 모든 컨테이너를 리스트로 변환
        all_containers: list["Container"] = []
        for containers in self.manager.get_all_containers().values():
            all_containers.extend(containers)

        # Factory Chain 유효성 검증
        self._validate_factory_chains(all_containers)

        # 레벨별로 그룹화 (순환 의존성 시 그래프 저장)
        try:
            levels = group_by_dependency_level(all_containers)
        except CircularDependencyError as e:
            self._save_circular_dependency_graph(e)
            raise

        # 초기화 순서 저장 (PreDestroy용)
        self._initialized_containers = []

        def init_container(
            container: "Container",
        ) -> tuple["Container", Any] | None:
            """단일 컨테이너 초기화 (ThreadPool에서 실행)"""
            if is_lazy_component(container):
                return None
            instance = container.initialize_instance()
            return (container, instance)

        # 레벨별로 병렬 초기화
        for level_containers in levels:
            if not level_containers:
                continue

            # ThreadPoolExecutor로 같은 레벨 컨테이너들 동시 초기화
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(init_container, container): container
                    for container in level_containers
                }

                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        container, instance = result
                        self._initialized_containers.append(container)
                        self.manager.set_instance(container.target, instance)

    def shutdown(self) -> "Application":
        """
        애플리케이션 종료

        모든 컴포넌트의 @PreDestroy 메서드를 역순으로 호출합니다.
        (나중에 초기화된 컴포넌트부터 먼저 정리)

        Returns:
            self (메서드 체이닝 지원)
        """
        if not self._is_ready:
            return self

        # 현재 매니저 설정
        set_current_manager(self.manager)

        # LifecycleManager를 통해 역순으로 PreDestroy 호출
        if self._initialized_containers:
            self.manager.lifecycle.invoke_all_pre_destroy(self._initialized_containers)

        self._is_ready = False
        return self

    # 하위 호환성을 위한 메서드들
    def scan_components(self, module: object) -> None:
        """@deprecated: scan() 사용 권장"""
        self.scan(module)

    def initialize_components(self) -> None:
        """@deprecated: ready() 사용 권장"""
        self._initialize_containers()
