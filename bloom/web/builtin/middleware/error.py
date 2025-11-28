"""
에러 핸들러 미들웨어

요청 처리 중 발생하는 예외를 잡아서 적절한 HTTP 응답으로 변환합니다.

사용 예시:
    ```python
    from bloom import Component
    from bloom.web.error import ErrorHandlerMiddleware, ErrorHandler

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

import traceback
from typing import Any

from ...error.manager import ErrorHandlerManager
from ...http import HttpRequest, HttpResponse
from ...middleware.base import Middleware


class ErrorHandlerMiddleware(Middleware):
    """
    에러 핸들러 미들웨어

    요청 처리 중 발생하는 예외를 잡아서 HTTP 응답으로 변환합니다.
    ErrorHandlerManager를 통해 등록된 핸들러를 찾아 호출합니다.

    핸들러 우선순위:
        1. Controller 스코프의 정확한 예외 타입
        2. Controller 스코프의 부모 예외 타입
        3. 글로벌 스코프의 정확한 예외 타입
        4. 글로벌 스코프의 부모 예외 타입
        5. 기본 handle_exception 메서드

    Attributes:
        debug: True이면 스택 트레이스를 응답에 포함 (기본: False)
        _manager: ErrorHandlerManager 인스턴스
    """

    debug: bool = False
    _manager: ErrorHandlerManager | None = None

    def set_controller_prefixes(self, prefixes: dict[type, str]) -> None:
        """Controller prefix 매핑 설정 및 Manager 초기화 (Application에서 호출)"""
        self._manager = ErrorHandlerManager()
        self._manager.set_controller_prefixes(prefixes)
        self._manager.collect_handlers()

    async def _process_request(self, request: HttpRequest, handler: Any = None):
        """
        요청/응답 처리 (yield 기반)

        핸들러에서 발생하는 예외를 잡아서 적절한 에러 응답으로 변환합니다.
        """
        try:
            response = yield  # 다음 미들웨어/핸들러 실행
        except Exception as exc:
            # 예외 발생 시 에러 핸들러로 처리
            yield await self.handle_exception(request, exc)
            return

        yield response

    async def handle_exception(
        self, request: HttpRequest, exc: Exception
    ) -> HttpResponse:
        """
        예외를 HTTP 응답으로 변환

        1. ErrorHandlerManager에서 핸들러 찾기
        2. 없으면 기본 에러 응답 생성

        Args:
            request: HTTP 요청
            exc: 발생한 예외

        Returns:
            에러 응답
        """
        # Manager가 초기화되어 있으면 핸들러 찾기
        if self._manager:
            entry = self._manager.find_handler(exc, request.path)

            if entry:
                # 핸들러 호출
                result = await self._manager.call_handler(entry, exc, request)

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