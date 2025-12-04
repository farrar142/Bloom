"""bloom.core.application.asgi - ASGI 애플리케이션 관리

ASGI 앱 생성 및 라우트 등록을 담당합니다.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager
    from .middleware import MiddlewareManager


logger = logging.getLogger(__name__)


class _LifespanASGIWrapper:
    """ASGI Lifespan 이벤트를 처리하는 Wrapper"""

    def __init__(
        self,
        asgi_app: Any,
        on_startup: Any,
        on_shutdown: Any,
        app_name: str,
    ):
        self._asgi_app = asgi_app
        self._on_startup = on_startup
        self._on_shutdown = on_shutdown
        self._app_name = app_name

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        else:
            await self._asgi_app(scope, receive, send)

    async def _handle_lifespan(self, scope: dict, receive: Any, send: Any) -> None:
        """ASGI Lifespan 이벤트 처리"""
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                try:
                    logger.info(f"Starting {self._app_name}...")
                    await self._on_startup()
                    logger.info(f"{self._app_name} ready!")
                    await send({"type": "lifespan.startup.complete"})
                except Exception as e:
                    logger.error(f"Startup failed: {e}")
                    import traceback

                    traceback.print_exc()
                    await send({"type": "lifespan.startup.failed", "message": str(e)})
                    return
            elif message["type"] == "lifespan.shutdown":
                logger.info(f"Shutting down {self._app_name}...")
                await self._on_shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return


class ASGIManager:
    """ASGI 애플리케이션 관리자

    ASGI 앱 생성, 라우트 등록, 미들웨어 적용을 관리합니다.
    """

    def __init__(self, app_name: str):
        self._app_name = app_name
        self._asgi: Any = None

    @property
    def asgi(self) -> Any:
        """캐시된 ASGI 앱"""
        return self._asgi

    def invalidate_cache(self) -> None:
        """ASGI 앱 캐시 무효화"""
        self._asgi = None

    def create_asgi_app(
        self,
        container_manager: "ContainerManager",
        middleware_manager: "MiddlewareManager",
        on_startup: Any,
        on_shutdown: Any,
    ) -> Any:
        """ASGI 앱 생성

        Args:
            container_manager: 컨테이너 관리자
            middleware_manager: 미들웨어 관리자
            on_startup: 시작 콜백
            on_shutdown: 종료 콜백

        Returns:
            ASGI 앱 (Lifespan wrapper 포함)
        """
        if self._asgi is not None:
            return self._asgi

        from bloom.web import ASGIApplication, Request
        from bloom.web.routing.decorators import get_controller_routes
        from bloom.web.routing.resolver import ResolverRegistry
        from bloom.web.routing.router import Route, RouteMatch
        from bloom.web.middleware import ErrorHandlerMiddleware

        asgi = ASGIApplication(debug=True)
        resolver_registry = ResolverRegistry()

        # 미들웨어 수집
        middleware_manager.collect_di_middlewares(container_manager)
        asgi_middlewares, di_middlewares, func_middlewares = (
            middleware_manager.classify_middlewares()
        )

        # ASGI 레벨 미들웨어 등록
        for entry in sorted(asgi_middlewares, key=lambda e: e.order):
            asgi.add_middleware(
                entry.middleware_cls,
                **entry.middleware_kwargs,
            )

        # ErrorHandlerMiddleware 등록
        error_middleware = ErrorHandlerMiddleware(debug=True)
        for exc_cls, handler in middleware_manager.exception_handlers.items():
            error_middleware.add_handler(exc_cls, handler)

        # @Controller 라우트 등록
        self._register_controller_routes(
            asgi,
            container_manager,
            middleware_manager,
            di_middlewares,
            func_middlewares,
            resolver_registry,
        )

        self._asgi = _LifespanASGIWrapper(
            asgi,
            on_startup,
            on_shutdown,
            self._app_name,
        )

        return self._asgi

    def _register_controller_routes(
        self,
        asgi: Any,
        container_manager: "ContainerManager",
        middleware_manager: "MiddlewareManager",
        di_middlewares: list,
        func_middlewares: list,
        resolver_registry: Any,
    ) -> None:
        """@Controller 라우트 등록

        Args:
            asgi: ASGI 앱
            container_manager: 컨테이너 관리자
            middleware_manager: 미들웨어 관리자
            di_middlewares: DI 미들웨어 목록
            func_middlewares: 함수 미들웨어 목록
            resolver_registry: 파라미터 리졸버 레지스트리
        """
        from bloom.web import Request
        from bloom.web.routing.decorators import get_controller_routes
        from bloom.web.routing.router import Route, RouteMatch

        for container in container_manager.get_all_containers():
            cls = container.target
            if not getattr(cls, "__bloom_controller__", False):
                continue

            for route in get_controller_routes(cls):
                path = route["path"]
                methods = route["methods"]
                method_name = route["name"]

                route_obj = Route(
                    path=path,
                    method=methods[0] if methods else "GET",
                    handler=lambda r: r,
                    name=method_name,
                )

                async def handler(
                    request: Request,
                    ctrl_cls: type = cls,
                    mname: str = method_name,
                    route_for_match: Route = route_obj,
                    _di_middlewares: list = di_middlewares,
                    _func_middlewares: list = func_middlewares,
                    _container_manager: "ContainerManager" = container_manager,
                    _middleware_manager: "MiddlewareManager" = middleware_manager,
                    _resolver_registry: Any = resolver_registry,
                ) -> Any:
                    scope_manager = _container_manager.scope_manager
                    frame_id, is_owner = scope_manager.start_call()

                    try:

                        async def final_handler(req: Request) -> Any:
                            controller = await _container_manager.get_instance_async(
                                ctrl_cls
                            )
                            method = getattr(controller, mname)
                            match = RouteMatch(
                                route=route_for_match,
                                path_params=req.path_params,
                            )
                            params = await _resolver_registry.resolve_parameters(
                                method, req, match
                            )
                            return await method(**params)

                        return await _middleware_manager.execute_chain(
                            request,
                            final_handler,
                            _di_middlewares,
                            _func_middlewares,
                            _container_manager,
                        )
                    finally:
                        await scope_manager.end_call(frame_id, is_owner=is_owner)

                for method in methods:
                    getattr(asgi, method.lower())(path)(handler)
