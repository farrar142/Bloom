"""bloom.core.application.middleware - 미들웨어 관리

미들웨어 등록 및 체인 실행을 담당합니다.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager


class MiddlewareManager:
    """미들웨어 관리자

    ASGI 레벨 미들웨어와 DI 연동 미들웨어를 관리합니다.
    """

    def __init__(self):
        self._middleware_entries: list[Any] = []
        self._exception_handlers: dict[type[Exception], Any] = {}

    @property
    def middleware_entries(self) -> list[Any]:
        """등록된 미들웨어 엔트리 목록"""
        return self._middleware_entries

    @property
    def exception_handlers(self) -> dict[type[Exception], Any]:
        """등록된 예외 핸들러 목록"""
        return self._exception_handlers

    def add_middleware(
        self,
        middleware_cls: type,
        order: int = 0,
        path: str | None = None,
        **kwargs: Any,
    ) -> "MiddlewareManager":
        """미들웨어 추가

        Args:
            middleware_cls: 미들웨어 클래스
            order: 실행 순서 (낮을수록 먼저 실행)
            path: 적용할 경로 패턴 (예: "/api/*")
            **kwargs: ASGI 미들웨어에 전달할 인자

        Returns:
            self (체이닝용)
        """
        from bloom.web.middleware.base import (
            MiddlewareEntry,
            Middleware,
            is_middleware_component,
        )

        if is_middleware_component(middleware_cls):
            entry = MiddlewareEntry(
                order=order,
                di_middleware_cls=middleware_cls,
                path_pattern=path,
            )
        elif issubclass(middleware_cls, Middleware):
            entry = MiddlewareEntry(
                order=order,
                middleware_cls=middleware_cls,
                middleware_kwargs=kwargs,
            )
        else:
            entry = MiddlewareEntry(
                order=order,
                di_middleware_cls=middleware_cls,
                path_pattern=path,
            )

        self._middleware_entries.append(entry)
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

        Returns:
            데코레이터 함수
        """
        from bloom.web.middleware.base import MiddlewareEntry

        def decorator(func: Callable) -> Callable:
            entry = MiddlewareEntry(
                order=order,
                func_middleware=func,
                path_pattern=path,
            )
            self._middleware_entries.append(entry)
            return func

        return decorator

    def exception_handler(self, exception_cls: type[Exception]) -> Callable:
        """예외 핸들러 데코레이터

        Args:
            exception_cls: 처리할 예외 타입

        Returns:
            데코레이터 함수
        """

        def decorator(func: Callable) -> Callable:
            self._exception_handlers[exception_cls] = func
            return func

        return decorator

    def collect_di_middlewares(self, container_manager: "ContainerManager") -> None:
        """@MiddlewareComponent로 등록된 DI 미들웨어 자동 수집

        Args:
            container_manager: 컨테이너 관리자
        """
        from bloom.web.middleware.base import (
            MiddlewareEntry,
            get_middleware_metadata,
        )

        for container in container_manager.get_all_containers():
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

    def classify_middlewares(self) -> tuple[list, list, list]:
        """미들웨어 분류

        Returns:
            (asgi_middlewares, di_middlewares, func_middlewares) 튜플
        """
        asgi_middlewares: list[Any] = []
        di_middlewares: list[Any] = []
        func_middlewares: list[Any] = []

        for entry in self._middleware_entries:
            if entry.middleware_cls:
                asgi_middlewares.append(entry)
            elif entry.di_middleware_cls:
                di_middlewares.append(entry)
            elif entry.func_middleware:
                func_middlewares.append(entry)

        return asgi_middlewares, di_middlewares, func_middlewares

    async def execute_chain(
        self,
        request: Any,
        final_handler: Callable,
        di_middlewares: list,
        func_middlewares: list,
        container_manager: "ContainerManager",
        index: int = 0,
    ) -> Any:
        """DI/함수 미들웨어 체인 실행

        Args:
            request: 요청 객체
            final_handler: 최종 핸들러
            di_middlewares: DI 미들웨어 목록
            func_middlewares: 함수 미들웨어 목록
            container_manager: 컨테이너 관리자
            index: 현재 미들웨어 인덱스

        Returns:
            응답 객체
        """
        all_middlewares = sorted(
            di_middlewares + func_middlewares,
            key=lambda e: e.order,
        )

        if index >= len(all_middlewares):
            return await final_handler(request)

        entry = all_middlewares[index]

        # 경로 패턴 체크
        if entry.path_pattern and not fnmatch.fnmatch(request.path, entry.path_pattern):
            return await self.execute_chain(
                request,
                final_handler,
                di_middlewares,
                func_middlewares,
                container_manager,
                index + 1,
            )

        # call_next 생성
        async def call_next(req: Any) -> Any:
            return await self.execute_chain(
                req,
                final_handler,
                di_middlewares,
                func_middlewares,
                container_manager,
                index + 1,
            )

        # 미들웨어 실행
        if entry.di_middleware_cls:
            instance = await container_manager.get_instance_async(
                entry.di_middleware_cls
            )
            return await instance(request, call_next)
        elif entry.func_middleware:
            return await entry.func_middleware(request, call_next)

        return await self.execute_chain(
            request,
            final_handler,
            di_middlewares,
            func_middlewares,
            container_manager,
            index + 1,
        )

    def invalidate_cache(self) -> None:
        """캐시 무효화 (외부에서 호출용)"""
        # Application에서 _asgi = None 처리
        pass
