"""bloom Application"""

from typing import TYPE_CHECKING, Any
from pathlib import Path

if TYPE_CHECKING:
    from .core.container import Container
    from .core.advice import MethodInvocationManager
    from .web.messaging.manager import WebSocketManager

from .core.manager import ContainerManager, set_current_manager, try_get_current_manager
from .core.orchestrator import ContainerOrchestrator
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
        self.manager = self._resolve_manager(name, manager)
        self._router: Router | None = None
        self._asgi: ASGIApplication | None = None
        self._is_ready = False
        self._config_manager = ConfigManager()
        self._websocket_manager: "WebSocketManager | None" = None
        self._initialized_containers: list["Container"] = []
        self._invocation_manager: "MethodInvocationManager | None" = None
        # 생성 시점에 현재 매니저로 설정 (데코레이터 자동 등록 지원)
        set_current_manager(self.manager)

    def _resolve_manager(
        self, name: str, manager: "ContainerManager | None"
    ) -> ContainerManager:
        """ContainerManager 결정: 전달받거나, 현재 활성 manager 사용, 또는 새로 생성"""
        if manager is not None:
            return manager
        if existing := try_get_current_manager():
            existing.app_name = name
            return existing
        return ContainerManager(name)

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
            self.manager.scan(module)
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

        # 2. 컨테이너 초기화 (Orchestrator 사용)
        orchestrator = ContainerOrchestrator(self.manager)
        self._initialized_containers = orchestrator.initialize(parallel=parallel)

        # 3. 메서드 프록시 적용 (Advice 체인 지원)
        self._apply_method_proxies()

        # 4. 라우터 초기화
        self.router.collect_routes()

        # 5. WebSocket 초기화 (@EnableWebSocket 감지)
        self._initialize_websocket()

        self._is_ready = True
        return self

    def _bind_configuration_properties(self) -> None:
        """ConfigurationProperties를 바인딩하여 인스턴스 생성"""
        self._config_manager.bind_configuration_properties(self.manager)

    def _apply_method_proxies(self) -> None:
        """
        HandlerContainer가 있는 모든 메서드에 프록시를 적용합니다.

        MethodInvocationManager를 생성하고, ContainerManager에서 Registry를 조회합니다.
        Registry가 없거나 Advice가 없으면 프록시를 적용하지 않습니다.
        """
        from .core.advice import MethodInvocationManager, MethodProxy
        from .core.container import HandlerContainer
        import inspect

        # MethodInvocationManager 생성 및 초기화 (ContainerManager에서 Registry 조회)
        self._invocation_manager = MethodInvocationManager()
        self._invocation_manager.initialize(self.manager)

        # Registry가 없거나 Advice가 없으면 프록시 적용 안 함
        if (
            self._invocation_manager._advice_registry is None
            or len(self._invocation_manager._advice_registry) == 0
        ):
            return

        # 모든 인스턴스를 순회하며 프록시 적용
        for instances in self.manager.get_all_instances().values():
            for instance in instances:
                self._apply_proxies_to_instance(instance, self._invocation_manager)

    def _apply_proxies_to_instance(
        self, instance: Any, invocation_manager: Any
    ) -> None:
        """
        인스턴스의 HandlerContainer 메서드들에 프록시를 적용합니다.
        """
        from .core.advice import MethodProxy
        from .core.container import HandlerContainer

        cls = type(instance)

        for name in dir(cls):
            if name.startswith("_"):
                continue

            try:
                attr = getattr(cls, name)
            except AttributeError:
                continue

            # 메서드인지 확인
            if not callable(attr):
                continue

            # HandlerContainer가 있는지 확인
            container = HandlerContainer.get_container(attr)
            if container is None:
                continue

            # 프록시 생성 및 적용
            proxy = MethodProxy(
                container=container,
                instance=instance,
                original=attr,
                manager=invocation_manager,
            )
            setattr(instance, name, proxy)

    def _initialize_websocket(self) -> None:
        """WebSocket 초기화 (@EnableWebSocket 컴포넌트가 있는 경우)"""
        self.websocket_manager.initialize(self.manager)

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
