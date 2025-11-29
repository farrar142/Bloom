"""
미들웨어 체인 (GroupRegistry)

GroupRegistry[Middleware]를 상속하여 미들웨어들을 그룹 단위로 관리합니다.
Router에서 자동으로 수집되어 요청/응답 처리 시 실행됩니다.

설정 방법:
    MiddlewareChain은 @Factory를 통해 생성하고, *middlewares: Middleware로
    모든 Middleware 서브클래스 인스턴스를 자동 주입받습니다.

    ```python
    from bloom import Component
    from bloom.core.decorators import Factory
    from bloom.web.middleware import Middleware, MiddlewareChain

    @Component
    class MiddlewareConfiguration:
        @Factory
        def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
            chain = MiddlewareChain()
            # 모든 Middleware 서브클래스 인스턴스가 자동 주입됨
            chain.add_group_after(*middlewares)
            return chain
    ```

그룹 관리:
    미들웨어를 그룹으로 묶어 일괄 활성화/비활성화 가능

    ```python
    chain = MiddlewareChain()

    # 기본 그룹 뒤에 추가
    chain.add_group_after(auth_middleware, logging_middleware)

    # 특정 그룹 앞에 추가
    security_group = chain.add_group_before(cors_middleware, target_group=auth_group)

    # 그룹 비활성화
    security_group.disable()
    ```

개별 미들웨어 제어:
    ```python
    # 특정 미들웨어만 비활성화
    chain.disable(debug_middleware)

    # 다시 활성화
    chain.enable(debug_middleware)
    ```
"""

from dataclasses import dataclass, field
from typing import Any, Optional, overload

from bloom.core.abstract import EntryGroup, GroupRegistry
from bloom.web.handler import HttpMethodHandlerContainer

from ..http import HttpRequest, HttpResponse

from .base import Middleware
from .group import MiddlewareGroup


@dataclass
class MiddlewareContext:
    """미들웨어 실행 컨텍스트 - 응답을 설정하고 예외를 전달하는 역할"""

    _generators: list = field(default_factory=list)
    _response: HttpResponse | None = None
    _exception: Exception | None = None
    early_response: HttpResponse | None = None
    handler: Any = None  # 라우팅된 핸들러 (HttpMethodHandlerContainer)

    def set_response(self, response: HttpResponse) -> None:
        """핸들러 응답 설정"""
        self._response = response

    def set_exception(self, exc: Exception) -> None:
        """예외 설정 (핸들러에서 발생한 예외)"""
        self._exception = exc


class MiddlewareProcessContext:
    """
    미들웨어 체인 처리용 Async Context Manager

    contextlib.asynccontextmanager 대신 직접 구현하여 성능 최적화.
    __aenter__에서 미들웨어 전처리, __aexit__에서 후처리 수행.
    """

    __slots__ = ("chain", "request", "handler", "ctx")

    def __init__(
        self,
        chain: "MiddlewareChain",
        request: HttpRequest,
        handler: HttpMethodHandlerContainer | None,
    ):
        self.chain = chain
        self.request = request
        self.handler = handler
        self.ctx = MiddlewareContext()

    async def __aenter__(self) -> MiddlewareContext:
        """미들웨어 요청 단계 실행"""
        middlewares = self.chain.get_all_middlewares()
        self.ctx.handler = self.handler

        # 요청 단계: 모든 미들웨어의 첫 번째 yield까지 실행
        for middleware in middlewares:
            gen = middleware._process_request(self.request, self.handler)
            first_yield = await gen.asend(None)  # type: ignore

            self.ctx._generators.append(gen)

            # early return 확인
            if first_yield is not None:
                response = (
                    first_yield
                    if isinstance(first_yield, HttpResponse)
                    else HttpResponse.ok(first_yield)
                )
                self.ctx.early_response = response
                # early return 이전까지의 미들웨어만 응답 처리
                self.ctx._generators.pop()
                break

        return self.ctx

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """미들웨어 응답 단계 실행"""
        ctx = self.ctx
        request = self.request

        # 응답 단계: 역순으로 응답/예외 처리
        if ctx.early_response:
            ctx._response = await self.chain._finish_generators(
                ctx._generators, request, ctx.early_response
            )
        elif ctx._exception:
            ctx._response = await self.chain._handle_exception(
                ctx._generators, request, ctx._exception
            )
        elif ctx._response:
            ctx._response = await self.chain._finish_generators(
                ctx._generators, request, ctx._response
            )
        else:
            ctx._response = await self.chain._finish_generators(
                ctx._generators,
                request,
                HttpResponse.internal_error("No response set"),
            )

        return False  # 예외를 다시 raise


class MiddlewareChain(GroupRegistry[Middleware]):
    """
    미들웨어 체인 (GroupRegistry)

    GroupRegistry[Middleware]를 상속하여 그룹 기반 관리.
    여러 미들웨어 그룹을 관리하고 실행 순서를 제어합니다.
    Router.dispatch()에서 자동으로 실행됩니다.

    실행 순서:
        요청: groups[0] → groups[1] → ... → groups[n] → 핸들러
        응답: 핸들러 → groups[n] → ... → groups[1] → groups[0]

    사용 예시:
        ```python
        @Component
        class MiddlewareConfig:
            auth: AuthMiddleware
            logging: LoggingMiddleware
            cors: CorsMiddleware

            @Factory
            def middleware_chain(self) -> MiddlewareChain:
                chain = MiddlewareChain()

                # 순서: cors → auth → logging → 핸들러
                chain.add_group_after(self.cors)
                chain.add_group_after(self.auth)
                chain.add_group_after(self.logging)

                return chain
        ```

    또는 varargs 인젝션 사용:
        ```python
        @Component
        class MiddlewareConfig:
            @Factory
            def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.add_group_after(*middlewares)
                return chain
        ```
    """

    # MiddlewareGroup을 그룹 타입으로 사용
    group_type = MiddlewareGroup

    def __init__(self):
        super().__init__()
        from ..builtin.middleware import CorsMiddleware, ErrorHandlerMiddleware

        # 기본 그룹에 필수 미들웨어 추가
        self.default_group.add(CorsMiddleware())
        self.default_group.add(ErrorHandlerMiddleware())

    # ========================================
    # 하위 호환성 속성
    # ========================================

    @property
    def groups(self) -> list[MiddlewareGroup]:
        """그룹 리스트 (하위 호환성)"""
        return self._groups  # type: ignore

    @property
    def default_group(self) -> MiddlewareGroup:
        """기본 그룹 (하위 호환성)"""
        return self._default_group  # type: ignore

    # ========================================
    # 미들웨어 전용 API
    # ========================================

    @overload
    def get_middleware[T: Middleware](
        self, middleware_type: type[T], raise_exception: bool = True
    ) -> T: ...

    @overload
    def get_middleware[T: Middleware](
        self, middleware_type: type[T], raise_exception: bool = False
    ) -> T | None: ...

    def get_middleware[T: Middleware](
        self, middleware_type: type[T], raise_exception: bool = True
    ) -> T | None:
        """
        특정 타입의 미들웨어 인스턴스 반환

        Args:
            middleware_type: 찾을 미들웨어 타입
            raise_exception: True면 못 찾을 시 예외, False면 None 반환

        Returns:
            미들웨어 인스턴스 또는 None

        Raises:
            ValueError: 미들웨어를 찾을 수 없을 때 (raise_exception=True)

        사용 예시:
            ```python
            cors = chain.get_middleware(CorsMiddleware)
            chain.disable(cors)
            ```
        """
        for group in self._groups:
            for middleware in group.items:
                if isinstance(middleware, middleware_type):
                    return middleware

        if raise_exception:
            raise ValueError(f"Middleware {middleware_type.__name__} not found")
        return None

    def get_all_middlewares(self) -> list[Middleware]:
        """
        모든 활성화된 미들웨어를 순서대로 반환 (캐싱됨)

        Returns:
            미들웨어 리스트
        """
        return self.get_all_items()

    # ========================================
    # 미들웨어 체인 실행 로직
    # ========================================

    def process(
        self, request: HttpRequest, handler: HttpMethodHandlerContainer | None = None
    ) -> MiddlewareProcessContext:
        """
        미들웨어 체인 실행 (최적화된 async context manager)

        async with 문으로 사용하며, 요청 전처리 → 핸들러 → 응답 후처리 흐름을 제어합니다.
        contextlib.asynccontextmanager 대신 직접 구현하여 성능 최적화.

        사용법:
            ```python
            async with self.middleware_chain.process(request, handler) as ctx:
                if ctx.early_response:
                    return ctx.early_response

                try:
                    response = await call_handler()
                    ctx.set_response(response)
                except Exception as e:
                    ctx.set_exception(e)
            # with 블록을 나가면 자동으로 응답 후처리 및 예외 처리
            return ctx.get_final_response()
            ```

        Args:
            request: HTTP 요청
            handler: 라우팅된 핸들러 (HttpMethodHandlerContainer)

        Returns:
            MiddlewareProcessContext: async context manager
        """
        return MiddlewareProcessContext(self, request, handler)

    def get_final_response(self, ctx: MiddlewareContext) -> HttpResponse:
        """컨텍스트에서 최종 응답 반환"""
        if ctx._response:
            return ctx._response
        if ctx.early_response:
            return ctx.early_response
        return HttpResponse.internal_error("No response")

    async def _finish_generators(
        self,
        generators: list,
        request: HttpRequest,
        response: HttpResponse,
    ) -> HttpResponse:
        """
        미들웨어 generator들에 응답을 전달하고 마무리

        Args:
            generators: 미들웨어 generator 리스트
            request: HTTP 요청
            response: 현재 응답

        Returns:
            최종 응답
        """
        # 역순으로 응답 전달
        for gen in reversed(generators):
            try:
                result = await gen.asend(response)
                if result is not None and isinstance(result, HttpResponse):
                    response = result
            except StopAsyncIteration:
                pass

        return response

    async def _handle_exception(
        self,
        generators: list,
        request: HttpRequest,
        exc: Exception,
    ) -> HttpResponse:
        """
        예외를 미들웨어에 전달하여 처리

        역순으로 예외를 throw하여 미들웨어가 처리할 기회를 줍니다.

        Args:
            generators: 미들웨어 generator 리스트
            request: HTTP 요청
            exc: 발생한 예외

        Returns:
            에러 응답
        """
        response: HttpResponse | None = None

        # 역순으로 예외 전달
        for gen in reversed(generators):
            try:
                if response is None:
                    # 첫 번째 미들웨어에 예외 throw
                    result = await gen.athrow(exc)
                else:
                    # 이미 처리된 응답 전달
                    result = await gen.asend(response)

                if result is not None and isinstance(result, HttpResponse):
                    response = result
            except StopAsyncIteration:
                pass
            except Exception as new_exc:
                # 미들웨어가 예외를 다시 던지면 다음 미들웨어로 전달
                exc = new_exc

        # 아무 미들웨어도 예외를 처리하지 않으면 기본 에러 응답
        if response is None:
            return HttpResponse.internal_error(str(exc))

        return response

    def __repr__(self) -> str:
        active_count = len(self.get_all_middlewares())
        return f"MiddlewareChain(groups={len(self._groups)}, active_middlewares={active_count})"
