"""bloom Application - 통합 애플리케이션 클래스

Application은 DI 컨테이너, TaskApp(큐), 웹 라우팅 등을 통합 관리합니다.

Usage:
    from bloom import Application
    from bloom.task.backends import RedisBroker, RedisBackend

    # 애플리케이션 생성
    app = Application("my_app")

    # 태스크 큐 설정 (선택)
    app.configure_queue(
        broker=RedisBroker("redis://localhost:6379/0"),
        backend=RedisBackend("redis://localhost:6379/0"),
    )

    # 모듈 스캔 (@Service, @Controller 등)
    app.scan(my_services, my_controllers)

    # 초기화 (@PostConstruct, @Task 메서드 등록 등)
    await app.ready_async()

    # 워커 실행:
    # bloom queue -A my_module:app.queue worker -c 4
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from .core.application import (
    MiddlewareManager,
    QueueManager,
    ASGIManager,
    ScannerManager,
    LifecycleManager,
)

if TYPE_CHECKING:
    from .task import TaskApp
    from .task.broker import TaskBroker
    from .task.backend import TaskBackend


logger = logging.getLogger(__name__)


class Application:
    """
    bloom 통합 애플리케이션

    DI 컨테이너, 태스크 큐, 웹 라우팅을 통합 관리합니다.
    각 기능은 별도의 매니저 클래스로 분리되어 있으며,
    Application은 이들을 조합하여 사용합니다.

    Attributes:
        name: 애플리케이션 이름
        queue: 태스크 큐 앱 (TaskApp)

    Examples:
        app = Application("my_app")
        app.configure_queue(broker=RedisBroker(url), backend=RedisBackend(url))
        app.scan(services, controllers)
        await app.ready_async()

        # 워커 실행
        # bloom queue -A module:app.queue worker
    """

    def __init__(self, name: str):
        self.name = name

        # 매니저 인스턴스들
        self._middleware_manager = MiddlewareManager()
        self._queue_manager = QueueManager(name)
        self._asgi_manager = ASGIManager(name)
        self._scanner_manager = ScannerManager()
        self._lifecycle_manager = LifecycleManager(name)

        # ContainerManager (lazy import)
        self._container_manager: Any = None

    # =========================================================================
    # Internal Properties (하위 호환성)
    # =========================================================================

    @property
    def _middleware_entries(self) -> list:
        """미들웨어 엔트리 리스트 (하위 호환성)"""
        return self._middleware_manager._middleware_entries

    @property
    def _exception_handlers(self) -> dict:
        """예외 핸들러 딕셔너리 (하위 호환성)"""
        return self._middleware_manager._exception_handlers

    # =========================================================================
    # Middleware API (위임)
    # =========================================================================

    def add_middleware(
        self,
        middleware_cls: type,
        order: int = 0,
        path: str | None = None,
        **kwargs: Any,
    ) -> "Application":
        """미들웨어 추가

        ASGI 레벨 미들웨어 또는 DI 연동 미들웨어를 추가합니다.

        Args:
            middleware_cls: 미들웨어 클래스
            order: 실행 순서 (낮을수록 먼저 실행)
            path: 적용할 경로 패턴 (예: "/api/*")
            **kwargs: ASGI 미들웨어에 전달할 인자

        Returns:
            self (체이닝용)

        Examples:
            # ASGI 레벨 미들웨어
            app.add_middleware(CORSMiddleware, order=0, allow_origins=["*"])

            # DI 연동 미들웨어 (@MiddlewareComponent)
            app.add_middleware(AuthMiddleware, order=50)
        """
        self._middleware_manager.add_middleware(middleware_cls, order, path, **kwargs)
        self._asgi_manager.invalidate_cache()
        return self

    def middleware(
        self,
        order: int = 0,
        path: str | None = None,
    ) -> Callable:
        """함수 미들웨어 데코레이터

        Args:
            order: 실행 순서 (낮을수록 먼저 실행)
            path: 적용할 경로 패턴 (예: "/api/*")

        Examples:
            @app.middleware(order=10)
            async def logging_middleware(request, call_next):
                start = time.time()
                response = await call_next(request)
                print(f"Duration: {time.time() - start:.3f}s")
                return response
        """
        decorator = self._middleware_manager.middleware(order, path)
        self._asgi_manager.invalidate_cache()
        return decorator

    def exception_handler(self, exception_cls: type[Exception]) -> Callable:
        """예외 핸들러 데코레이터

        Args:
            exception_cls: 처리할 예외 타입

        Examples:
            @app.exception_handler(ValidationError)
            async def validation_error_handler(request, exc):
                return JSONResponse({"error": str(exc)}, status_code=400)
        """
        return self._middleware_manager.exception_handler(exception_cls)

    # =========================================================================
    # Queue API (위임)
    # =========================================================================

    @property
    def queue(self) -> "TaskApp":
        """태스크 큐 앱 (TaskApp)

        워커 실행 시 이 속성을 사용합니다:
            bloom queue -A module:app.queue worker

        TaskBroker, TaskBackend는 DI 컨테이너에서 @Factory로 주입받습니다.
        ready_async() 호출 후에 접근해야 합니다.
        """
        queue = self._queue_manager.queue
        if queue is not None:
            return queue
        return self._queue_manager.get_or_create_queue(self.container_manager)

    def configure_queue(
        self,
        *,
        broker: "TaskBroker | None" = None,
        backend: "TaskBackend | None" = None,
        name: str | None = None,
    ) -> "Application":
        """태스크 큐 설정

        Args:
            broker: 메시지 브로커 (예: RedisBroker)
            backend: 결과 백엔드 (예: RedisBackend)
            name: TaskApp 이름 (기본: Application 이름)

        Returns:
            self (체이닝용)

        Examples:
            app.configure_queue(
                broker=RedisBroker("redis://localhost:6379/0"),
                backend=RedisBackend("redis://localhost:6379/0"),
            )
        """
        self._queue_manager.configure(broker=broker, backend=backend, name=name)
        return self

    # =========================================================================
    # ASGI API (위임)
    # =========================================================================

    @property
    def asgi(self) -> Any:
        """ASGI 애플리케이션

        uvicorn에서 사용:
            uvicorn module:app.asgi --reload

        @Controller 클래스들의 라우트를 자동으로 등록합니다.
        """
        if self._asgi_manager.asgi is None:
            return self._asgi_manager.create_asgi_app(
                container_manager=self.container_manager,
                middleware_manager=self._middleware_manager,
                on_startup=self._on_startup,
                on_shutdown=self._on_shutdown,
            )
        return self._asgi_manager.asgi

    async def _on_startup(self) -> None:
        """ASGI 시작 콜백"""
        await self.ready_async()
        await self._queue_manager.connect()

    async def _on_shutdown(self) -> None:
        """ASGI 종료 콜백"""
        await self.shutdown_async()

    # =========================================================================
    # Scanner API (위임)
    # =========================================================================

    def scan(self, *modules: object) -> "Application":
        """모듈들을 스캔하여 컴포넌트 수집

        @Component, @Service, @Controller 등이 붙은 클래스를 스캔합니다.
        @Configuration 클래스의 @Factory 메서드도 등록됩니다.

        Args:
            modules: 스캔할 모듈들

        Returns:
            self (체이닝용)
        """
        self._scanner_manager.scan(*modules, container_manager=self.container_manager)
        return self

    def auto_scan(self, caller_file: str | None = None) -> "Application":
        """호출 파일 위치의 패키지와 하위 디렉토리를 자동 스캔

        caller_file 기준으로 같은 패키지와 모든 하위 패키지를 스캔합니다.
        import 문 없이도 컴포넌트를 자동으로 찾아 등록합니다.

        Args:
            caller_file: 호출 파일 경로 (__file__ 전달), 또는 패키지 이름 문자열.
                        None이면 자동으로 호출자의 __file__을 찾습니다.

        Returns:
            self (체이닝용)

        Examples:
            # app.py에서 호출 - 같은 디렉토리의 모든 하위 패키지 스캔
            application = Application("demo-app").auto_scan(__file__)

            # 패키지 이름으로 직접 지정
            application = Application("demo-app").auto_scan("examples.demo_app")

            # 또는 자동 감지
            application = Application("demo-app").auto_scan()
        """
        self._scanner_manager.auto_scan(
            caller_file, container_manager=self.container_manager
        )
        return self

    # =========================================================================
    # Lifecycle API (위임)
    # =========================================================================

    @property
    def container_manager(self) -> Any:
        """DI 컨테이너 관리자"""
        if self._container_manager is None:
            from .core import get_container_manager

            self._container_manager = get_container_manager()

        return self._container_manager

    async def ready_async(self, parallel: bool = False) -> "Application":
        """애플리케이션 초기화 완료 (비동기)

        1. ContainerManager 초기화
        2. 의존성 주입
        3. @Task 메서드 자동 등록
        4. @PostConstruct 실행

        Args:
            parallel: 병렬 초기화 여부

        Returns:
            self (체이닝용)
        """
        await self._lifecycle_manager.startup(
            container_manager=self.container_manager,
            queue_manager=self._queue_manager,
            invalidate_asgi_cache=self._asgi_manager.invalidate_cache,
        )
        return self

    def ready(self) -> "Application":
        """애플리케이션 초기화 완료 (동기)

        이미 이벤트 루프가 실행 중이면 ready_async()를 사용하세요.
        """
        self._lifecycle_manager.startup_sync(self.ready_async())
        return self

    async def shutdown_async(self, wait: bool = True) -> "Application":
        """애플리케이션 비동기 종료

        1. @PreDestroy 실행
        2. 브로커/백엔드 연결 해제

        Args:
            wait: 대기 여부

        Returns:
            self (체이닝용)
        """
        await self._lifecycle_manager.shutdown(
            container_manager=self.container_manager,
            queue_manager=self._queue_manager,
        )
        return self

    def shutdown(self) -> "Application":
        """애플리케이션 종료 (동기)"""
        self._lifecycle_manager.shutdown_sync(self.shutdown_async())
        return self

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def is_ready(self) -> bool:
        """초기화 완료 여부"""
        return self._lifecycle_manager.is_ready

    def __repr__(self) -> str:
        return f"<Application: {self.name}>"
