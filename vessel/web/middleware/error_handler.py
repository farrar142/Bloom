"""
에러 핸들러 미들웨어

요청 처리 중 발생하는 예외를 잡아서 적절한 HTTP 응답으로 변환합니다.

사용 예시:
    ```python
    from vessel import Component
    from vessel.web.middleware import ErrorHandlerMiddleware

    # 기본 사용 (500 에러로 변환)
    @Component
    class MyErrorHandler(ErrorHandlerMiddleware):
        pass

    # 커스텀 예외 처리 - @ErrorHandler 데코레이터 사용
    @Component
    class GlobalErrorHandler:
        @ErrorHandler(ValueError)
        def handle_value_error(self, error: ValueError) -> HttpResponse:
            return HttpResponse.bad_request(str(error))

    # Controller 스코프 에러 핸들러
    @Controller
    @RequestMapping("/api/users")
    class UserController:
        @ErrorHandler(NotFoundException)
        def handle_not_found(self, error: NotFoundException) -> HttpResponse:
            return HttpResponse.not_found(error.message)
    ```
"""

import asyncio
import traceback
from typing import Any, Optional

from vessel.core import ContainerManager

from ..error_handler import ErrorHandlerContainer
from ..http import HttpRequest, HttpResponse
from .base import Middleware


class ErrorHandlerMiddleware(Middleware):
    """
    에러 핸들러 미들웨어

    요청 처리 중 발생하는 예외를 잡아서 HTTP 응답으로 변환합니다.
    ErrorHandlerContainer로 등록된 핸들러가 있으면 해당 핸들러를 호출합니다.

    핸들러 우선순위:
        1. Controller 스코프의 정확한 예외 타입
        2. Controller 스코프의 부모 예외 타입
        3. 글로벌 스코프의 정확한 예외 타입
        4. 글로벌 스코프의 부모 예외 타입
        5. 기본 handle_exception 메서드

    Attributes:
        debug: True이면 스택 트레이스를 응답에 포함 (기본: False)
        _controller_prefixes: Controller 클래스 -> RequestMapping prefix 매핑
    """

    debug: bool = False
    _caught_exception: Exception | None = None
    _controller_prefixes: dict[type, str] = {}

    def set_controller_prefixes(self, prefixes: dict[type, str]) -> None:
        """Controller prefix 매핑 설정 (Application에서 호출)"""
        self._controller_prefixes = prefixes

    async def process_request(self, request: HttpRequest) -> Optional[Any]:
        """요청 전처리 - 예외 컨텍스트 초기화"""
        self._caught_exception = None
        return None

    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """응답 후처리"""
        return response

    def _get_error_handlers(self) -> list[ErrorHandlerContainer]:
        """ContainerManager에서 모든 ErrorHandlerContainer 수집"""
        handlers: list[ErrorHandlerContainer] = []
        for qual_containers in ContainerManager.get_all_containers().values():
            for container in qual_containers.values():
                if isinstance(container, ErrorHandlerContainer):
                    handlers.append(container)
        return handlers

    def _find_handler(
        self, exc: Exception, request_path: str
    ) -> ErrorHandlerContainer | None:
        """
        예외와 요청 경로에 맞는 핸들러 찾기

        우선순위:
            1. Controller 스코프 + 정확한 예외 타입
            2. Controller 스코프 + 부모 예외 타입
            3. 글로벌 스코프 + 정확한 예외 타입
            4. 글로벌 스코프 + 부모 예외 타입
        """
        handlers = self._get_error_handlers()
        if not handlers:
            return None

        # Controller 스코프 핸들러 (request_path로 필터링)
        controller_handlers: list[ErrorHandlerContainer] = []
        # 글로벌 스코프 핸들러 (Component에 정의됨)
        global_handlers: list[ErrorHandlerContainer] = []

        for handler in handlers:
            if not handler.can_handle(exc):
                continue

            # owner_cls가 Controller인지 확인
            owner_cls = handler.owner_cls
            if owner_cls and owner_cls in self._controller_prefixes:
                prefix = self._controller_prefixes[owner_cls]
                # 요청 경로가 prefix로 시작하면 해당 Controller 스코프
                if request_path.startswith(prefix):
                    controller_handlers.append(handler)
            else:
                # Controller가 아니면 글로벌 스코프
                global_handlers.append(handler)

        # 정확한 예외 타입 우선
        def exact_match_first(h: ErrorHandlerContainer) -> tuple[int, int]:
            # (exact_match=0이면 우선, mro_index가 작을수록 우선)
            exc_type = type(exc)
            if h.exception_type == exc_type:
                return (0, 0)
            # MRO에서 위치 찾기 (더 가까운 부모가 우선)
            mro = exc_type.__mro__
            try:
                idx = mro.index(h.exception_type)
            except ValueError:
                idx = len(mro)
            return (1, idx)

        # Controller 스코프 먼저, 그 다음 글로벌
        if controller_handlers:
            controller_handlers.sort(key=exact_match_first)
            return controller_handlers[0]

        if global_handlers:
            global_handlers.sort(key=exact_match_first)
            return global_handlers[0]

        return None

    async def handle_exception(
        self, request: HttpRequest, exc: Exception
    ) -> HttpResponse:
        """
        예외를 HTTP 응답으로 변환

        1. ErrorHandlerContainer에서 핸들러 찾기
        2. 없으면 기본 에러 응답 생성

        Args:
            request: HTTP 요청
            exc: 발생한 예외

        Returns:
            에러 응답
        """
        # ErrorHandlerContainer에서 핸들러 찾기
        handler = self._find_handler(exc, request.path)

        if handler:
            # 핸들러 인스턴스 가져오기
            owner_instance = None
            if handler.owner_cls:
                owner_instance = ContainerManager.get_instance(
                    handler.owner_cls, raise_exception=False
                )

            # 핸들러 호출
            if owner_instance:
                result = handler.handler_method(owner_instance, exc)
            else:
                result = handler.handler_method(exc)

            # async 함수인 경우 await
            if asyncio.iscoroutine(result):
                result = await result

            # HttpResponse가 아니면 변환
            if isinstance(result, HttpResponse):
                return result
            return HttpResponse.ok(result)

        # 기본 에러 응답
        error_body: dict[str, Any] = {
            "error": type(exc).__name__,
            "message": str(exc),
        }

        if self.debug:
            error_body["traceback"] = traceback.format_exc()

        return HttpResponse.internal_error(
            error_body.get("message", "Internal Server Error")
        )
