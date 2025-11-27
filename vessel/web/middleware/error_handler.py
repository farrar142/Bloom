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

    # 커스텀 예외 처리
    @Component
    class CustomErrorHandler(ErrorHandlerMiddleware):
        async def handle_exception(
            self, request: HttpRequest, exc: Exception
        ) -> HttpResponse:
            if isinstance(exc, ValidationError):
                return HttpResponse.bad_request(str(exc))
            if isinstance(exc, NotFoundError):
                return HttpResponse.not_found(str(exc))
            return await super().handle_exception(request, exc)
    ```
"""

import traceback
from typing import Any, Optional

from ..http import HttpRequest, HttpResponse
from .base import Middleware


class ErrorHandlerMiddleware(Middleware):
    """
    에러 핸들러 미들웨어

    요청 처리 중 발생하는 예외를 잡아서 HTTP 응답으로 변환합니다.
    Router.dispatch()에서 발생하는 예외는 이 미들웨어가 처리합니다.

    Attributes:
        debug: True이면 스택 트레이스를 응답에 포함 (기본: False)

    사용 예시:
        ```python
        @Component
        class ErrorHandler(ErrorHandlerMiddleware):
            debug = True  # 개발 환경에서 상세 에러 표시
        ```

    커스터마이징:
        `handle_exception` 메서드를 오버라이드하여 예외별 처리 가능:

        ```python
        @Component
        class CustomErrorHandler(ErrorHandlerMiddleware):
            async def handle_exception(self, request, exc):
                if isinstance(exc, AuthError):
                    return HttpResponse.unauthorized(str(exc))
                return await super().handle_exception(request, exc)
        ```
    """

    debug: bool = False
    _caught_exception: Exception | None = None

    async def process_request(self, request: HttpRequest) -> Optional[Any]:
        """
        요청 전처리 - 예외 컨텍스트 초기화

        실제 예외 처리는 process_response에서 수행됩니다.
        """
        self._caught_exception = None
        return None

    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """
        응답 후처리 - 예외가 있으면 에러 응답으로 변환

        참고: 현재 구현에서는 Router에서 예외를 잡기 때문에
        이 메서드가 직접 호출되지 않습니다.
        향후 Router 개선 시 활용됩니다.
        """
        return response

    async def handle_exception(
        self, request: HttpRequest, exc: Exception
    ) -> HttpResponse:
        """
        예외를 HTTP 응답으로 변환

        서브클래스에서 오버라이드하여 커스텀 예외 처리 가능

        Args:
            request: HTTP 요청
            exc: 발생한 예외

        Returns:
            에러 응답
        """
        error_body: dict[str, Any] = {
            "error": type(exc).__name__,
            "message": str(exc),
        }

        if self.debug:
            error_body["traceback"] = traceback.format_exc()

        return HttpResponse.internal_error(
            error_body.get("message", "Internal Server Error")
        )
