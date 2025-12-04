"""bloom.web.middleware.base - Middleware Base Classes"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Callable, Awaitable, TypeVar
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from ..types import ASGIApp, Scope, Receive, Send
    from ..request import Request
    from ..response import Response
    from ...core.manager import ContainerManager

T = TypeVar("T")


# =============================================================================
# Base Middleware Class (ASGI 레벨)
# =============================================================================


class Middleware(ABC):
    """
    ASGI 레벨 미들웨어 베이스 클래스.

    저수준 ASGI 인터페이스에서 동작합니다.

    사용 예:
        class LoggingMiddleware(Middleware):
            async def __call__(self, scope, receive, send):
                print(f"Request: {scope['path']}")
                await self.app(scope, receive, send)
                print("Response sent")
    """

    def __init__(self, app: "ASGIApp | None") -> None:
        self.app = app

    @abstractmethod
    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        """미들웨어 실행"""
        pass


# =============================================================================
# DI-aware Middleware (Request/Response 레벨)
# =============================================================================


# 미들웨어 메타데이터
MIDDLEWARE_METADATA_KEY = "__bloom_middleware__"


@dataclass
class MiddlewareMetadata:
    """미들웨어 메타데이터"""

    order: int = 0
    path_pattern: str | None = None  # None이면 모든 경로에 적용


def MiddlewareComponent(
    order: int = 0,
    path: str | None = None,
) -> Callable[[type[T]], type[T]]:
    """
    DI 연동 미들웨어 데코레이터.

    @Component처럼 DI 컨테이너에 등록되며, 생성자 의존성 주입을 지원합니다.

    Args:
        order: 실행 순서 (낮을수록 먼저 실행, 기본값: 0)
        path: 적용할 경로 패턴 (예: "/api/*"), None이면 모든 경로

    사용 예:
        @MiddlewareComponent(order=50)
        class AuthMiddleware:
            def __init__(self, auth_service: AuthService):
                self.auth_service = auth_service

            async def __call__(self, request: Request, call_next) -> Response:
                token = request.headers.get("Authorization")
                if token:
                    request.state.user = await self.auth_service.verify(token)
                return await call_next(request)

        # 특정 경로에만 적용
        @MiddlewareComponent(order=50, path="/api/*")
        class ApiAuthMiddleware:
            async def __call__(self, request: Request, call_next) -> Response:
                ...

    Note:
        생성자 파라미터를 통한 의존성 주입은 지원되지 않습니다.
        필드 주입(Field Injection)을 사용하세요:

        @MiddlewareComponent(order=50)
        class AuthMiddleware:
            auth_service: AuthService  # 필드 주입 (권장)

            async def __call__(self, request, call_next):
                ...
    """
    from ...core import Component

    def decorator(cls: type[T]) -> type[T]:
        # @Component로 DI 등록 (생성자 검사도 @Component에서 수행)
        Component(cls)

        # 미들웨어 메타데이터 저장
        metadata = MiddlewareMetadata(order=order, path_pattern=path)
        setattr(cls, MIDDLEWARE_METADATA_KEY, metadata)

        return cls

    return decorator


def is_middleware_component(cls: type) -> bool:
    """미들웨어 컴포넌트인지 확인"""
    return hasattr(cls, MIDDLEWARE_METADATA_KEY)


def get_middleware_metadata(cls: type) -> MiddlewareMetadata | None:
    """미들웨어 메타데이터 조회"""
    return getattr(cls, MIDDLEWARE_METADATA_KEY, None)


# =============================================================================
# Middleware Entry (order 정렬용)
# =============================================================================


@dataclass
class MiddlewareEntry:
    """미들웨어 엔트리 (정렬용)"""

    order: int
    middleware_cls: type[Middleware] | None = None  # ASGI 레벨 미들웨어
    middleware_kwargs: dict = field(default_factory=dict)
    di_middleware_cls: type | None = None  # DI 연동 미들웨어
    func_middleware: Callable | None = None  # 함수 미들웨어
    path_pattern: str | None = None

    def __lt__(self, other: "MiddlewareEntry") -> bool:
        return self.order < other.order


# =============================================================================
# Middleware Stack
# =============================================================================


class MiddlewareStack:
    """
    미들웨어 스택 관리.

    미들웨어를 order 기반으로 정렬하여 체인을 구성합니다.

    실행 순서:
        - order가 낮은 미들웨어가 먼저 실행 (가장 바깥쪽)
        - order가 높은 미들웨어가 나중에 실행 (가장 안쪽)

    사용 예:
        stack = MiddlewareStack(app)
        stack.add(CORSMiddleware, order=0)
        stack.add(ErrorHandlerMiddleware, order=100)
        stack.add(LoggingMiddleware, order=10)

        # 실행 순서: CORS(0) → Logging(10) → ErrorHandler(100) → app
        final_app = stack.build()
    """

    def __init__(self, app: "ASGIApp") -> None:
        self._app = app
        self._entries: list[MiddlewareEntry] = []
        self._built_app: "ASGIApp | None" = None

    def add(
        self,
        middleware_cls: type[Middleware],
        order: int = 0,
        **kwargs,
    ) -> "MiddlewareStack":
        """ASGI 레벨 미들웨어 추가"""
        entry = MiddlewareEntry(
            order=order,
            middleware_cls=middleware_cls,
            middleware_kwargs=kwargs,
        )
        self._entries.append(entry)
        self._built_app = None  # 캐시 무효화
        return self

    def add_di_middleware(
        self,
        middleware_cls: type,
        order: int = 0,
        path_pattern: str | None = None,
    ) -> "MiddlewareStack":
        """DI 연동 미들웨어 추가"""
        entry = MiddlewareEntry(
            order=order,
            di_middleware_cls=middleware_cls,
            path_pattern=path_pattern,
        )
        self._entries.append(entry)
        self._built_app = None
        return self

    def add_func_middleware(
        self,
        func: Callable,
        order: int = 0,
        path_pattern: str | None = None,
    ) -> "MiddlewareStack":
        """함수 미들웨어 추가"""
        entry = MiddlewareEntry(
            order=order,
            func_middleware=func,
            path_pattern=path_pattern,
        )
        self._entries.append(entry)
        self._built_app = None
        return self

    def build(self) -> "ASGIApp":
        """미들웨어 체인 빌드 (ASGI 레벨 미들웨어만)"""
        if self._built_app is not None:
            return self._built_app

        app = self._app

        # order로 정렬 (오름차순)
        sorted_entries = sorted(self._entries)

        # 역순으로 래핑 (order가 낮은 것이 가장 바깥쪽)
        for entry in reversed(sorted_entries):
            if entry.middleware_cls:
                app = entry.middleware_cls(app, **entry.middleware_kwargs)

        self._built_app = app
        return app

    def get_di_middlewares(self) -> list[MiddlewareEntry]:
        """DI 연동 미들웨어 목록 (order 정렬됨)"""
        return sorted(
            [e for e in self._entries if e.di_middleware_cls],
            key=lambda e: e.order,
        )

    def get_func_middlewares(self) -> list[MiddlewareEntry]:
        """함수 미들웨어 목록 (order 정렬됨)"""
        return sorted(
            [e for e in self._entries if e.func_middleware],
            key=lambda e: e.order,
        )

    def __len__(self) -> int:
        return len(self._entries)


# =============================================================================
# DI Middleware Wrapper (ASGI 레벨로 래핑)
# =============================================================================


class DIMiddlewareWrapper(Middleware):
    """
    DI 연동 미들웨어를 ASGI 레벨로 래핑.

    Request/Response 레벨의 미들웨어를 ASGI 인터페이스에 맞게 변환합니다.
    """

    def __init__(
        self,
        app: "ASGIApp",
        container_manager: "ContainerManager",
        di_middlewares: list[MiddlewareEntry],
        func_middlewares: list[MiddlewareEntry],
    ) -> None:
        super().__init__(app)
        self._container_manager = container_manager
        self._di_middlewares = di_middlewares
        self._func_middlewares = func_middlewares

    async def __call__(
        self,
        scope: "Scope",
        receive: "Receive",
        send: "Send",
    ) -> None:
        if scope["type"] != "http":
            if self.app is None:
                raise NotImplementedError("App is None in DIMiddlewareWrapper")
            await self.app(scope, receive, send)
            return

        from ..request import Request

        request = Request(scope, receive)

        # 미들웨어 체인 실행
        response = await self._execute_chain(request, 0)

        if response is not None:
            await response(scope, receive, send)
        else:
            # 미들웨어가 직접 응답을 보내지 않은 경우
            if self.app is None:
                raise NotImplementedError("App is None in DIMiddlewareWrapper")
            await self.app(scope, receive, send)

    async def _execute_chain(
        self,
        request: "Request",
        index: int,
    ) -> "Response | None":
        """미들웨어 체인 실행"""
        # 모든 미들웨어 합치고 정렬
        all_middlewares = sorted(
            self._di_middlewares + self._func_middlewares,
            key=lambda e: e.order,
        )

        if index >= len(all_middlewares):
            # 모든 미들웨어 통과 - 실제 핸들러로 전달
            return None

        entry = all_middlewares[index]

        # 경로 패턴 체크
        if entry.path_pattern and not self._match_path(
            request.path, entry.path_pattern
        ):
            # 이 미들웨어는 건너뜀
            return await self._execute_chain(request, index + 1)

        # call_next 생성
        async def call_next(req: "Request") -> "Response":
            result = await self._execute_chain(req, index + 1)
            if result is None:
                # 핸들러 실행 (실제로는 ASGI 앱으로 전달)
                # 여기서는 임시 응답 반환
                from ..response import Response

                return Response(status_code=200)
            return result

        # 미들웨어 실행
        if entry.di_middleware_cls:
            # DI 연동 미들웨어
            instance = await self._container_manager.get_instance_async(
                entry.di_middleware_cls
            )
            if instance is None:
                raise ValueError(
                    f"Cannot create instance of middleware {entry.di_middleware_cls}"
                )
            return await instance(request, call_next)
        elif entry.func_middleware:
            # 함수 미들웨어
            return await entry.func_middleware(request, call_next)

        return await self._execute_chain(request, index + 1)

    def _match_path(self, path: str, pattern: str) -> bool:
        """경로 패턴 매칭"""
        import fnmatch

        return fnmatch.fnmatch(path, pattern)
