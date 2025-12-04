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

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from pathlib import Path

if TYPE_CHECKING:
    from .task import TaskApp
    from .task.broker import TaskBroker
    from .task.backend import TaskBackend


logger = logging.getLogger(__name__)


class _LifespanASGIWrapper:
    """ASGI Lifespan 이벤트를 처리하는 Wrapper"""

    def __init__(self, asgi_app: Any, application: "Application"):
        self._asgi_app = asgi_app
        self._application = application

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        else:
            await self._asgi_app(scope, receive, send)

    async def _handle_lifespan(self, scope: dict, receive: Any, send: Any) -> None:
        """ASGI Lifespan 이벤트 처리"""
        app = self._application
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    logger.info(f"Starting {app.name}...")
                    # Application 초기화 (모든 SINGLETON 생성)
                    await app.ready_async()

                    # 브로커/백엔드 연결 (ready 이후에 queue 접근)
                    if app._queue and app._queue.broker:
                        await app._queue.broker.connect()
                    if app._queue and app._queue.backend:
                        await app._queue.backend.connect()

                    logger.info(f"{app.name} ready!")
                    await send({"type": "lifespan.startup.complete"})
                except Exception as e:
                    logger.error(f"Startup failed: {e}")
                    import traceback

                    traceback.print_exc()
                    await send({"type": "lifespan.startup.failed", "message": str(e)})
                    return
            elif message["type"] == "lifespan.shutdown":
                logger.info(f"Shutting down {app.name}...")
                await app.shutdown_async()
                await send({"type": "lifespan.shutdown.complete"})
                return


class Application:
    """
    bloom 통합 애플리케이션

    DI 컨테이너, 태스크 큐, 웹 라우팅을 통합 관리합니다.

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
        self._is_ready = False
        self._scanned_modules: list[Any] = []

        # TaskApp (태스크 큐)
        self._queue: "TaskApp | None" = None

        # ASGI Application
        self._asgi: Any = None

        # ContainerManager (lazy import)
        self._container_manager: Any = None

        # 미들웨어 설정
        self._middleware_entries: list[Any] = []  # MiddlewareEntry 리스트
        self._exception_handlers: dict[type[Exception], Any] = {}

    # =========================================================================
    # Middleware API
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
        from .web.middleware.base import (
            MiddlewareEntry,
            Middleware,
            is_middleware_component,
        )

        if is_middleware_component(middleware_cls):
            # DI 연동 미들웨어
            entry = MiddlewareEntry(
                order=order,
                di_middleware_cls=middleware_cls,
                path_pattern=path,
            )
        elif issubclass(middleware_cls, Middleware):
            # ASGI 레벨 미들웨어
            entry = MiddlewareEntry(
                order=order,
                middleware_cls=middleware_cls,
                middleware_kwargs=kwargs,
            )
        else:
            # DI 연동 미들웨어로 간주 (프로토콜 기반)
            entry = MiddlewareEntry(
                order=order,
                di_middleware_cls=middleware_cls,
                path_pattern=path,
            )

        self._middleware_entries.append(entry)
        self._asgi = None  # 캐시 무효화
        return self

    def middleware(
        self,
        order: int = 0,
        path: str | None = None,
    ):
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
        from .web.middleware.base import MiddlewareEntry

        def decorator(func):
            entry = MiddlewareEntry(
                order=order,
                func_middleware=func,
                path_pattern=path,
            )
            self._middleware_entries.append(entry)
            self._asgi = None  # 캐시 무효화
            return func

        return decorator

    def exception_handler(self, exception_cls: type[Exception]):
        """예외 핸들러 데코레이터

        Args:
            exception_cls: 처리할 예외 타입

        Examples:
            @app.exception_handler(ValidationError)
            async def validation_error_handler(request, exc):
                return JSONResponse({"error": str(exc)}, status_code=400)
        """

        def decorator(func):
            self._exception_handlers[exception_cls] = func
            return func

        return decorator

    @property
    def queue(self) -> "TaskApp":
        """태스크 큐 앱 (TaskApp)

        워커 실행 시 이 속성을 사용합니다:
            bloom queue -A module:app.queue worker

        TaskBroker, TaskBackend는 DI 컨테이너에서 @Factory로 주입받습니다.
        ready_async() 호출 후에 접근해야 합니다.
        """
        if self._queue is not None:
            return self._queue

        # ready_async() 전에 호출된 경우 (CLI 등에서)
        # 동기적으로 TaskApp 생성 (Broker/Backend 없이)
        from .task import TaskApp
        from .task.broker import TaskBroker
        from .task.backend import TaskBackend

        # 이벤트 루프가 없는 경우에만 동기적으로 DI 조회
        import asyncio

        try:
            asyncio.get_running_loop()
            # async 컨텍스트에서는 ready_async()가 먼저 호출되어야 함
            # 임시로 Broker/Backend 없이 생성
            broker = None
            backend = None
        except RuntimeError:
            # 이벤트 루프가 없으면 동기적으로 조회
            broker = self.container_manager.get_instance(TaskBroker, required=False)
            backend = self.container_manager.get_instance(TaskBackend, required=False)

        self._queue = TaskApp(
            self.name,
            broker=broker,
            backend=backend,
        )

        if broker:
            logger.info(f"TaskApp created with broker: {type(broker).__name__}")
        if backend:
            logger.info(f"TaskApp created with backend: {type(backend).__name__}")

        return self._queue

    @property
    def asgi(self) -> Any:
        """ASGI 애플리케이션

        uvicorn에서 사용:
            uvicorn module:app.asgi --reload

        @Controller 클래스들의 라우트를 자동으로 등록합니다.
        """
        if self._asgi is None:
            self._asgi = self._create_asgi_app()
        return self._asgi

    def _create_asgi_app(self) -> Any:
        """ASGI 앱 생성 - @Controller 라우트 자동 등록"""
        from .web import ASGIApplication, Request
        from .web.routing.decorators import get_controller_routes
        from .web.routing.resolver import ResolverRegistry
        from .web.routing.router import Route, RouteMatch
        from .web.middleware.base import (
            MiddlewareEntry,
            Middleware,
            is_middleware_component,
            get_middleware_metadata,
        )
        from .web.middleware import ErrorHandlerMiddleware

        asgi = ASGIApplication(debug=True)
        app = self  # closure용
        resolver_registry = ResolverRegistry()

        # =================================================================
        # 미들웨어 수집 및 등록
        # =================================================================

        # 1. @MiddlewareComponent로 등록된 DI 미들웨어 자동 수집
        for container in self.container_manager.get_all_containers():
            cls = container.target
            metadata = get_middleware_metadata(cls)
            if metadata:
                entry = MiddlewareEntry(
                    order=metadata.order,
                    di_middleware_cls=cls,
                    path_pattern=metadata.path_pattern,
                )
                # 중복 방지
                if not any(
                    e.di_middleware_cls == cls for e in self._middleware_entries
                ):
                    self._middleware_entries.append(entry)

        # 2. 미들웨어 분류
        asgi_middlewares: list[MiddlewareEntry] = []
        di_middlewares: list[MiddlewareEntry] = []
        func_middlewares: list[MiddlewareEntry] = []

        for entry in self._middleware_entries:
            if entry.middleware_cls:
                asgi_middlewares.append(entry)
            elif entry.di_middleware_cls:
                di_middlewares.append(entry)
            elif entry.func_middleware:
                func_middlewares.append(entry)

        # 3. ASGI 레벨 미들웨어 등록 (MiddlewareStack으로)
        for entry in sorted(asgi_middlewares, key=lambda e: e.order):
            asgi.add_middleware(
                entry.middleware_cls,  # type: ignore
                **entry.middleware_kwargs,
            )

        # 4. ErrorHandlerMiddleware 등록 (가장 안쪽, 기본 등록)
        # 예외 핸들러 등록
        error_middleware = ErrorHandlerMiddleware(debug=True)
        for exc_cls, handler in self._exception_handlers.items():
            error_middleware.add_handler(exc_cls, handler)

        # =================================================================
        # @Controller 라우트 등록
        # =================================================================

        for container in self.container_manager.get_all_containers():
            cls = container.target
            if not getattr(cls, "__bloom_controller__", False):
                continue

            # 컨트롤러의 라우트 등록
            for route in get_controller_routes(cls):
                path = route["path"]
                methods = route["methods"]
                method_name = route["name"]

                # Route 객체 생성 (closure용)
                route_obj = Route(
                    path=path,
                    method=methods[0] if methods else "GET",
                    handler=lambda r: r,  # dummy
                    name=method_name,
                )

                # 핸들러 생성 (closure)
                async def handler(
                    request: Request,
                    ctrl_cls: type = cls,
                    mname: str = method_name,
                    route_for_match: Route = route_obj,
                    _di_middlewares: list = di_middlewares,
                    _func_middlewares: list = func_middlewares,
                ) -> Any:
                    # CALL 스코프 시작
                    scope_manager = app.container_manager.scope_manager
                    frame_id = scope_manager.start_call()

                    try:
                        # DI/함수 미들웨어 체인 실행
                        async def final_handler(req: Request) -> Any:
                            controller = await app.container_manager.get_instance_async(
                                ctrl_cls
                            )

                            # CALL 스코프 의존성은 AsyncProxy.resolve() 또는
                            # LazyProxy 접근 시점에 자동 생성됨

                            method = getattr(controller, mname)

                            # RouteMatch 생성 (path variables 추출)
                            match = RouteMatch(
                                route=route_for_match,
                                path_params=req.path_params,
                            )

                            # 파라미터 해결
                            params = await resolver_registry.resolve_parameters(
                                method, req, match
                            )

                            return await method(**params)

                        # 미들웨어 체인 실행
                        return await app._execute_middleware_chain(
                            request,
                            final_handler,
                            _di_middlewares,
                            _func_middlewares,
                        )
                    finally:
                        # CALL 스코프 종료 (정리)
                        await scope_manager.end_call(frame_id)

                # 라우트 등록
                for method in methods:
                    getattr(asgi, method.lower())(path)(handler)

        # Lifespan을 처리하는 ASGI wrapper 반환
        return _LifespanASGIWrapper(asgi, self)

    async def _execute_middleware_chain(
        self,
        request: Any,
        final_handler: Any,
        di_middlewares: list,
        func_middlewares: list,
        index: int = 0,
    ) -> Any:
        """DI/함수 미들웨어 체인 실행"""
        import fnmatch

        # 모든 미들웨어 합치고 정렬
        all_middlewares = sorted(
            di_middlewares + func_middlewares,
            key=lambda e: e.order,
        )

        if index >= len(all_middlewares):
            # 모든 미들웨어 통과 - 최종 핸들러 실행
            return await final_handler(request)

        entry = all_middlewares[index]

        # 경로 패턴 체크
        if entry.path_pattern and not fnmatch.fnmatch(request.path, entry.path_pattern):
            # 이 미들웨어는 건너뜀
            return await self._execute_middleware_chain(
                request, final_handler, di_middlewares, func_middlewares, index + 1
            )

        # call_next 생성
        async def call_next(req: Any) -> Any:
            return await self._execute_middleware_chain(
                req, final_handler, di_middlewares, func_middlewares, index + 1
            )

        # 미들웨어 실행
        if entry.di_middleware_cls:
            # DI 연동 미들웨어
            instance = await self.container_manager.get_instance_async(
                entry.di_middleware_cls
            )
            return await instance(request, call_next)
        elif entry.func_middleware:
            # 함수 미들웨어
            return await entry.func_middleware(request, call_next)

        return await self._execute_middleware_chain(
            request, final_handler, di_middlewares, func_middlewares, index + 1
        )

    @property
    def container_manager(self) -> Any:
        """DI 컨테이너 관리자"""
        if self._container_manager is None:
            from .core import get_container_manager

            self._container_manager = get_container_manager()

        return self._container_manager

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
        from .task import TaskApp

        self._queue = TaskApp(
            name or self.name,
            broker=broker,
            backend=backend,
        )

        logger.info(f"Configured TaskApp for {self.name}")
        return self

    def scan(self, *modules: object) -> "Application":
        """모듈들을 스캔하여 컴포넌트 수집

        @Component, @Service, @Controller 등이 붙은 클래스를 스캔합니다.
        @Configuration 클래스의 @Factory 메서드도 등록됩니다.

        Args:
            modules: 스캔할 모듈들

        Returns:
            self (체이닝용)
        """
        from .core.scanner import scan_modules

        for module in modules:
            self._scanned_modules.append(module)
            # 실제 스캔 수행 - @Component, @Configuration/@Factory 등록
            scan_modules(module, manager=self.container_manager)

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
        import sys
        import importlib
        import importlib.util

        # 패키지 이름 문자열인 경우 (파일 경로가 아닌 경우)
        if (
            caller_file
            and not caller_file.endswith((".py", ".pyc"))
            and "." in caller_file
        ):
            # 패키지 이름으로 직접 스캔
            package_name = caller_file
            try:
                package_module = importlib.import_module(package_name)
                if hasattr(package_module, "__file__") and package_module.__file__:
                    package_dir = Path(package_module.__file__).resolve().parent
                else:
                    raise ValueError(f"Package {package_name} has no __file__")
            except ImportError as e:
                raise ValueError(f"Could not import package {package_name}: {e}")
        else:
            # 호출자의 __file__ 자동 감지
            if caller_file is None:
                import inspect

                frame = inspect.currentframe()
                if frame and frame.f_back:
                    caller_file = frame.f_back.f_globals.get("__file__")
                if not caller_file:
                    raise ValueError(
                        "Could not detect caller file. Please pass __file__ explicitly."
                    )

            caller_path = Path(caller_file).resolve()
            package_dir = caller_path.parent

            # 패키지 이름 결정
            # caller_file의 모듈 이름에서 패키지 경로 추출
            caller_module_name = None
            for name, module in sys.modules.items():
                if hasattr(module, "__file__") and module.__file__:
                    try:
                        if Path(module.__file__).resolve() == caller_path:
                            caller_module_name = name
                            break
                    except (OSError, ValueError):
                        continue

            if caller_module_name:
                # "examples.demo_app.app" -> "examples.demo_app"
                package_name = (
                    caller_module_name.rsplit(".", 1)[0]
                    if "." in caller_module_name
                    else caller_module_name
                )
            else:
                # sys.modules에서 못 찾으면 디렉토리 이름 사용
                package_name = package_dir.name

        logger.info(f"Auto-scanning package: {package_name} from {package_dir}")

        # 하위 디렉토리만 스캔 (현재 디렉토리의 __init__.py는 이미 로드됨)
        scanned_modules = []

        def scan_directory(dir_path: Path, parent_package: str, is_root: bool = False):
            """디렉토리를 재귀적으로 스캔

            Args:
                dir_path: 스캔할 디렉토리 경로
                parent_package: 부모 패키지 이름
                is_root: 루트 디렉토리인지 (루트는 스캔하지 않음)
            """
            # __init__.py가 있는 디렉토리만 패키지로 취급
            init_file = dir_path / "__init__.py"
            if not init_file.exists():
                return

            # 루트 디렉토리가 아니면 현재 패키지 import
            if not is_root:
                try:
                    module = importlib.import_module(parent_package)
                    scanned_modules.append(module)
                except ImportError as e:
                    logger.warning(f"Could not import {parent_package}: {e}")
                    return

            # 하위 디렉토리 스캔
            for item in dir_path.iterdir():
                if item.is_dir() and not item.name.startswith(("_", ".")):
                    sub_init = item / "__init__.py"
                    if sub_init.exists():
                        sub_package = f"{parent_package}.{item.name}"
                        scan_directory(item, sub_package, is_root=False)

        # 현재 패키지부터 스캔 시작 (루트는 스킵, 하위 디렉토리만 스캔)
        scan_directory(package_dir, package_name, is_root=True)

        # 스캔된 모듈들 등록
        for module in scanned_modules:
            self.scan(module)

        logger.info(f"Auto-scanned {len(scanned_modules)} modules")
        return self

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
        if self._is_ready:
            return self

        # ContainerManager 초기화
        await self.container_manager.initialize()

        # TaskApp 초기화 (DI에서 Broker/Backend 가져오기)
        await self._initialize_queue()

        # @Task 메서드 자동 등록
        await self._register_task_methods()

        # ASGI 앱 캐시 무효화 (미들웨어 수집을 위해)
        self._asgi = None

        self._is_ready = True
        logger.info(f"Application {self.name} is ready")

        return self

    async def _initialize_queue(self) -> None:
        """TaskApp 초기화 - DI에서 Broker/Backend 가져오기"""
        if self._queue is not None:
            return

        from .task import TaskApp
        from .task.broker import TaskBroker
        from .task.backend import TaskBackend

        # DI에서 async로 Broker/Backend 조회
        broker = await self.container_manager.get_instance_async(
            TaskBroker, required=False
        )
        backend = await self.container_manager.get_instance_async(
            TaskBackend, required=False
        )

        self._queue = TaskApp(
            self.name,
            broker=broker,
            backend=backend,
        )

        if broker:
            logger.info(f"TaskApp created with broker: {type(broker).__name__}")
        if backend:
            logger.info(f"TaskApp created with backend: {type(backend).__name__}")

    async def _register_task_methods(self) -> None:
        """@Service 클래스의 @Task 메서드들을 TaskApp에 등록

        AOP 스타일로 모든 @Service 인스턴스를 스캔하여
        @Task 데코레이터가 붙은 메서드를 자동으로 TaskApp에 등록합니다.
        """
        from .task.decorators import scan_task_methods

        # 모든 컨테이너에서 @Task 메서드가 있는 컴포넌트 찾기
        for container in self.container_manager.get_all_containers():
            # 인스턴스 획득
            try:
                instance = self.container_manager.get_instance(
                    container.target, required=False
                )
                if instance is None:
                    continue
            except Exception:
                continue

            # @Task 메서드 스캔
            task_methods = scan_task_methods(instance)
            if not task_methods:
                continue

            # 각 메서드를 TaskApp에 등록
            for method_name, bound_method, task_model in task_methods:
                # 태스크 이름 설정
                task_name = task_model.name or (
                    f"{instance.__class__.__module__}."
                    f"{instance.__class__.__name__}.{method_name}"
                )

                # TaskApp에 등록
                bound_task = self.queue.register_task(
                    name=task_name,
                    func=bound_method,
                    queue=task_model.queue,
                    retry=task_model.retry,
                    retry_delay=task_model.retry_delay,
                    timeout=task_model.timeout,
                    priority=task_model.priority,
                )

                # 인스턴스의 메서드를 BoundTask로 교체
                # self.send_welcome_email.apply_async() 형태로 사용 가능
                setattr(instance, method_name, bound_task)

                logger.info(f"Registered task: {task_name}")

    def ready(self) -> "Application":
        """애플리케이션 초기화 완료 (동기)

        이미 이벤트 루프가 실행 중이면 ready_async()를 사용하세요.
        """
        try:
            loop = asyncio.get_running_loop()
            # 이미 이벤트 루프가 실행 중이면 예외 발생
            raise RuntimeError(
                "이미 실행 중인 이벤트 루프가 있습니다. "
                "await application.ready_async()를 사용하세요."
            )
        except RuntimeError as e:
            if "no running event loop" in str(e):
                # 이벤트 루프가 없으면 새로 생성
                return asyncio.run(self.ready_async())
            raise

    async def shutdown_async(self, wait: bool = True) -> "Application":
        """애플리케이션 비동기 종료

        1. @PreDestroy 실행
        2. 브로커/백엔드 연결 해제

        Args:
            wait: 대기 여부

        Returns:
            self (체이닝용)
        """
        if not self._is_ready:
            return self

        # ContainerManager 종료 (@PreDestroy 실행)
        await self.container_manager.shutdown()

        # TaskApp 연결 해제
        if self._queue:
            if self._queue.broker:
                await self._queue.broker.disconnect()
            if self._queue.backend:
                await self._queue.backend.disconnect()

        self._is_ready = False
        logger.info(f"Application {self.name} shutdown complete")

        return self

    def shutdown(self) -> "Application":
        """애플리케이션 종료 (동기)"""
        if not self._is_ready:
            return self
        asyncio.run(self.shutdown_async())
        return self

    def __repr__(self) -> str:
        return f"<Application: {self.name}>"
