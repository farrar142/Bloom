"""bloom Application"""

from typing import TYPE_CHECKING, Any
from pathlib import Path

if TYPE_CHECKING:
    from .core.container import Container
    from .core.advice import MethodInvocationManager
    from .web.messaging.manager import WebSocketManager
    from .task.queue_app import QueueApplication

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
        self._queue: "QueueApplication | None" = None
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
    def queue(self) -> "QueueApplication":
        """
        Queue Worker 애플리케이션 반환 (bloom worker에서 사용)

        DistributedTaskBackend가 등록되어 있어야 합니다.
        @Factory로 DistributedTaskBackend를 생성하세요.

        사용 예시:
            app = Application("my_app").scan(module).ready()
            # bloom worker main:app.queue --concurrency 4

            # 또는 직접 실행
            asyncio.run(app.queue.run())
        """
        if self._queue is None:
            from .task.queue_app import QueueApplication

            self._queue = QueueApplication(application=self)
        return self._queue

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

    def auto_import(
        self,
        base_path: str | Path | None = None,
        exclude: set[str] | None = None,
    ) -> "Application":
        """
        지정된 경로의 모든 Python 모듈을 자동으로 import하고 스캔합니다.

        Args:
            base_path: 스캔할 기본 경로 (기본값: 현재 작업 디렉토리)
            exclude: 제외할 디렉토리/파일 이름 집합 (기본값: 빈 집합)

        Returns:
            self (메서드 체이닝 지원)

        사용 예시:
            # 현재 디렉토리 전체 스캔
            app = Application("myapp").auto_import().ready()

            # 특정 경로 스캔
            app.auto_import("src/")

            # 제외 대상 지정
            app.auto_import(exclude={"application.py", "tests"})

            # scan과 조합
            app.scan(configure).auto_import(exclude={"application.py"}).ready()
        """
        import importlib
        import os
        import sys

        if base_path is None:
            base_path = Path(os.getcwd())
        else:
            base_path = Path(base_path).resolve()

        if exclude is None:
            exclude = set()

        # 항상 제외할 기본 패턴 (시스템 디렉토리)
        system_exclude = {"__pycache__", ".venv", "venv", ".git"}
        all_exclude = exclude | system_exclude

        # 기본 경로를 sys.path에 추가
        base_str = str(base_path)
        if base_str not in sys.path:
            sys.path.insert(0, base_str)

        # 현재 매니저 설정
        set_current_manager(self.manager)

        for path in base_path.rglob("*.py"):
            # 제외 대상 체크 (디렉토리 또는 파일 이름)
            if any(part in all_exclude for part in path.parts):
                continue
            if path.name in all_exclude:
                continue

            # 모듈 이름 계산
            if path.name == "__init__.py":
                rel_path = path.parent.relative_to(base_path)
                module_name = ".".join(rel_path.parts)
            else:
                rel_path = path.relative_to(base_path)
                module_name = ".".join(rel_path.with_suffix("").parts)

            if not module_name:
                continue

            try:
                module = importlib.import_module(module_name)
                self.manager.scan(module)
            except ImportError as e:
                # import 실패 시 경고만 출력
                import warnings

                warnings.warn(f"Could not import {module_name}: {e}")

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

    def ready(
        self, parallel: bool = False, run_async_init: bool = True
    ) -> "Application":
        """
        애플리케이션 초기화 완료

        1. 컴포넌트 의존성 정렬 및 초기화
        2. 라우터에 핸들러 등록
        3. WebSocket 초기화 (@EnableWebSocket이 있는 경우)

        Args:
            parallel: True면 의존성 레벨별로 병렬 초기화 수행
                     같은 레벨의 컨테이너들을 동시에 초기화하여 시작 시간 단축
            run_async_init: True면 비동기 @PostConstruct도 즉시 실행 (기본값)
                           이벤트 루프가 이미 실행 중이면 자동으로 스킵됨
                           (ASGI 환경에서는 lifespan의 start_async()에서 실행)

        Returns:
            self (메서드 체이닝 지원)
        """
        if self._is_ready:
            return self

        # 현재 매니저 설정
        set_current_manager(self.manager)

        # 1. 이벤트 버스 등록 (DI 컨테이너에 인스턴스로 등록)
        self._register_event_buses()

        # 2. ConfigurationProperties 바인딩
        self._bind_configuration_properties()

        # 3. 컨테이너 초기화 (Orchestrator 사용)
        #    run_async_init이 True면 비동기 @PostConstruct도 실행
        orchestrator = ContainerOrchestrator(self.manager)
        self._initialized_containers = orchestrator.initialize(
            parallel=parallel, run_async_init=run_async_init
        )

        # 4. @EventListener 바인딩
        self._bind_event_listeners()

        # 5. 메서드 프록시 적용 (Advice 체인 지원)
        self._apply_method_proxies()

        # 6. 라우터 초기화
        self.router.collect_routes()

        # 7. WebSocket 초기화 (@EnableWebSocket 감지)
        self._initialize_websocket()

        self._is_ready = True

        return self

    def _register_event_buses(self) -> None:
        """이벤트 버스들을 DI 컨테이너에 등록 (사용자 정의가 없는 경우에만)"""
        from .core.events import SystemEventBus, ApplicationEventBus

        # SystemEventBus - ContainerManager에서 가져와서 인스턴스 등록
        # (시스템 이벤트 버스는 항상 프레임워크가 관리)
        # 이미 등록되어 있으면 스킵
        if not self.manager.get_instances(SystemEventBus):
            self.manager.set_instance(SystemEventBus, self.manager.system_events)

        # ApplicationEventBus - 사용자가 @Factory/@Component로 등록했으면 스킵
        # 이미 인스턴스가 있거나 컨테이너가 있으면 스킵
        if self.manager.get_container(
            ApplicationEventBus
        ) is None and not self.manager.get_instances(ApplicationEventBus):
            app_event_bus = ApplicationEventBus()
            self.manager.set_instance(ApplicationEventBus, app_event_bus)

    def _bind_event_listeners(self) -> None:
        """@EventListener 데코레이터가 붙은 메서드들을 ApplicationEventBus에 바인딩"""
        from .core.events import (
            ApplicationEventBus,
            is_event_listener,
            get_event_listener_type,
        )

        # ApplicationEventBus 인스턴스 가져오기
        event_bus = self.manager.get_instance(
            ApplicationEventBus, raise_exception=False
        )
        if event_bus is None:
            return

        # 모든 인스턴스를 순회하며 @EventListener 메서드 찾기
        for instances in self.manager.get_all_instances().values():
            for instance in instances:
                self._bind_instance_event_listeners(instance, event_bus)

    def _bind_instance_event_listeners(self, instance: Any, event_bus: Any) -> None:
        """인스턴스의 @EventListener 메서드들을 이벤트 버스에 바인딩"""
        from .core.events import is_event_listener, get_event_listener_type

        cls = type(instance)

        for name in dir(cls):
            if name.startswith("_"):
                continue

            try:
                attr = getattr(cls, name)
            except AttributeError:
                continue

            if not callable(attr):
                continue

            if is_event_listener(attr):
                event_type = get_event_listener_type(attr)
                if event_type:
                    # 바운드 메서드로 구독
                    bound_method = getattr(instance, name)
                    event_bus.subscribe(event_type, bound_method)

    def _bind_configuration_properties(self) -> None:
        """ConfigurationProperties를 바인딩하여 인스턴스 생성"""
        self._config_manager.bind_configuration_properties(self.manager)

    def _apply_method_proxies(self) -> None:
        """
        HandlerContainer가 있는 모든 메서드에 프록시를 적용합니다.

        MethodInvocationManager를 생성하고, ContainerManager에서 Registry를 조회합니다.
        Registry가 없거나 Advice가 없으면 프록시를 적용하지 않습니다.
        """
        from .core.advice import MethodInvocationManager

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
        ProxyableDescriptor를 구현한 디스크립터도 처리합니다.

        MethodAdvice 및 관련 인프라 클래스는 무한 재귀 방지를 위해 제외됩니다.
        """
        from .core.advice import MethodProxy, MethodAdvice, MethodAdviceRegistry
        from .core.container import HandlerContainer
        from .core.abstract import ProxyableDescriptor
        from .core.events.base import EventBus

        # MethodAdvice/EventBus 및 관련 인프라 클래스는 프록시 적용 제외 (무한 재귀 방지)
        if isinstance(instance, (MethodAdvice, MethodAdviceRegistry, EventBus)):
            return

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

            # ProxyableDescriptor 처리 (@Task 등)
            if isinstance(attr, ProxyableDescriptor):
                original_handler = attr.get_original_handler()
                if original_handler is not None:
                    container = HandlerContainer.get_container(original_handler)
                    if container is not None:
                        # 프록시 생성
                        proxy = MethodProxy(
                            container=container,
                            instance=instance,
                            original=original_handler,
                            manager=invocation_manager,
                        )
                        # 디스크립터에 프록시 적용
                        bound_obj = attr.apply_proxy(instance, proxy)
                        setattr(instance, name, bound_obj)
                continue

            # 일반 메서드 처리
            container = HandlerContainer.get_container(attr)
            if container is None:
                # HandlerContainer가 없으면 자동 생성 (모든 메서드 추적 지원)
                # method 객체에서 원본 함수 추출 (__func__)
                original_func = getattr(attr, "__func__", attr)
                container = HandlerContainer.get_or_create(original_func)

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
        애플리케이션 종료 (동기 핸들러만)

        동기 @PreDestroy 메서드를 역순으로 호출합니다.
        비동기 @PreDestroy가 있으면 shutdown_async()를 사용하세요.

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

    async def start_async(self) -> "Application":
        """
        애플리케이션 비동기 시작

        지연된 async @PostConstruct 핸들러들을 실행합니다.
        ASGI lifespan startup에서 자동으로 호출되거나,
        asyncio.run() 내에서 직접 호출해야 합니다.

        Returns:
            self (메서드 체이닝 지원)

        사용 예시:
            async def main():
                app = Application("my_app").scan(module).ready()
                await app.start_async()  # async @PostConstruct 실행
                # ... 비즈니스 로직 ...
                await app.shutdown_async()

            asyncio.run(main())
        """
        await self.manager.lifecycle.start_async()
        return self

    async def shutdown_async(self, wait: bool = True) -> "Application":
        """
        애플리케이션 비동기 종료

        모든 컴포넌트의 @PreDestroy 메서드를 호출합니다.
        ASGI lifespan shutdown에서 자동으로 호출되거나,
        asyncio.run() 내에서 직접 호출해야 합니다.

        Args:
            wait: True이면 실행 중인 작업 완료 대기

        Returns:
            self (메서드 체이닝 지원)
        """
        if not self._is_ready:
            return self

        # 현재 매니저 설정
        set_current_manager(self.manager)

        # 비동기 PreDestroy 실행
        await self.manager.lifecycle.shutdown_async()

        # 동기 PreDestroy 실행
        if self._initialized_containers:
            self.manager.lifecycle.invoke_all_pre_destroy(self._initialized_containers)

        self._is_ready = False
        return self
