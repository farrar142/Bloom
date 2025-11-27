"""
미들웨어 베이스 클래스

미들웨어는 요청/응답을 가로채어 공통 로직을 처리하는 컴포넌트입니다.
인증, 로깅, CORS, 에러 핸들링 등에 활용됩니다.

사용 예시 (기존 방식):
    ```python
    from bloom import Component
    from bloom.web import HttpRequest, HttpResponse
    from bloom.web.middleware import Middleware

    @Component
    class AuthMiddleware(Middleware):
        auth_service: AuthService  # 의존성 주입

        async def process_request(self, request: HttpRequest) -> HttpResponse | None:
            token = request.headers.get("Authorization")
            if not token:
                return HttpResponse.unauthorized("Token required")
            return None  # 다음으로 진행

        async def process_response(
            self, request: HttpRequest, response: HttpResponse
        ) -> HttpResponse:
            response.headers["X-Request-Id"] = request.headers.get("X-Request-Id", "")
            return response
    ```

예외 처리 (yield 방식 - _process_request 오버라이드):
    ```python
    @Component
    class ErrorHandlerMiddleware(Middleware):
        async def _process_request(self, request: HttpRequest):
            try:
                response = yield  # 핸들러 실행
            except Exception as e:
                yield HttpResponse.internal_error(str(e))
                return
            yield response
    ```

실행 순서:
    요청: A.process_request → B.process_request → C.process_request → 핸들러
    응답: 핸들러 → C.process_response → B.process_response → A.process_response
"""

from abc import ABC
from collections.abc import AsyncGenerator
from typing import Any, Optional

from ..http import HttpRequest, HttpResponse


class Middleware(ABC):
    """
    미들웨어 추상 클래스

    두 가지 방식으로 구현 가능:

    1. 기존 방식 (process_request/process_response 오버라이드):
        - process_request: 요청 전처리, early return 가능
        - process_response: 응답 후처리

    2. yield 방식 (_process_request 오버라이드):
        - 예외 처리가 필요한 경우 사용
        - try/except로 핸들러 예외를 잡을 수 있음

    사용 예시 (기존 방식):
        ```python
        @Component
        class LoggingMiddleware(Middleware):
            async def process_request(self, request: HttpRequest) -> None:
                print(f"Request: {request.method} {request.path}")
                return None

            async def process_response(
                self, request: HttpRequest, response: HttpResponse
            ) -> HttpResponse:
                print(f"Response: {response.status_code}")
                return response
        ```

    사용 예시 (yield 방식):
        ```python
        @Component
        class ErrorHandlerMiddleware(Middleware):
            async def _process_request(self, request: HttpRequest):
                try:
                    response = yield
                except Exception as e:
                    yield HttpResponse.internal_error(str(e))
                    return
                yield response
        ```
    """

    async def process_request(self, request: HttpRequest) -> Optional[Any]:
        """
        요청 처리 전 실행 (기존 방식)

        Args:
            request: HTTP 요청

        Returns:
            None: 다음 미들웨어/핸들러로 진행
            Any: 반환값이 있으면 early return (라우트 핸들러 스킵)
        """
        return None

    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """
        응답 처리 후 실행 (기존 방식)

        Args:
            request: HTTP 요청
            response: HTTP 응답

        Returns:
            HttpResponse: 수정된 응답
        """
        return response

    async def _process_request(
        self, request: HttpRequest, handler: Any = None
    ) -> AsyncGenerator[HttpResponse | None, HttpResponse]:
        """
        요청/응답 처리 (yield 기반 - 내부용)

        MiddlewareChain에서 호출됩니다.
        기본 구현은 process_request/process_response를 호출합니다.

        Args:
            request: HTTP 요청
            handler: 라우팅된 핸들러 (HttpMethodHandler) - Authorize 검사 등에 사용

        예외 처리가 필요한 미들웨어는 이 메서드를 오버라이드하세요:
            ```python
            async def _process_request(self, request, handler):
                try:
                    response = yield
                except Exception as e:
                    yield self.handle_exception(request, e)
                    return
                yield response
            ```
        """
        # 기존 process_request 호출
        early_result = await self.process_request(request)
        if early_result is not None:
            # early return
            if isinstance(early_result, HttpResponse):
                yield early_result
            else:
                yield HttpResponse.ok(early_result)
            return

        # 다음 미들웨어/핸들러 실행, 응답 받기
        response = yield

        # 기존 process_response 호출
        response = await self.process_response(request, response)
        yield response
