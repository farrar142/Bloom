"""
미들웨어 베이스 클래스

미들웨어는 요청/응답을 가로채어 공통 로직을 처리하는 컴포넌트입니다.
인증, 로깅, CORS, 에러 핸들링 등에 활용됩니다.

사용 예시:
    ```python
    from vessel import Component
    from vessel.web import HttpRequest, HttpResponse
    from vessel.web.middleware import Middleware

    @Component
    class AuthMiddleware(Middleware):
        auth_service: AuthService  # 의존성 주입

        async def process_request(self, request: HttpRequest) -> HttpResponse | None:
            token = request.headers.get("Authorization")
            if not token:
                return HttpResponse.unauthorized("Token required")

            # 인증 성공 - None 반환하면 다음 미들웨어/핸들러로 진행
            return None

        async def process_response(
            self, request: HttpRequest, response: HttpResponse
        ) -> HttpResponse:
            # 응답에 헤더 추가
            response.headers["X-Request-Id"] = request.headers.get("X-Request-Id", "")
            return response
    ```

실행 순서:
    요청 시: A.process_request → B.process_request → C.process_request → 핸들러
    응답 시: C.process_response → B.process_response → A.process_response
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..http import HttpRequest, HttpResponse


class Middleware(ABC):
    """
    미들웨어 추상 클래스

    모든 미들웨어는 이 클래스를 상속받아 구현합니다.
    @Component 데코레이터와 함께 사용하면 의존성 주입이 가능합니다.

    주요 메서드:
        - process_request: 요청 전처리 (인증, 검증 등)
        - process_response: 응답 후처리 (헤더 추가, 로깅 등)

    사용 예시:
        ```python
        @Component
        class LoggingMiddleware(Middleware):
            logger: LoggerService

            async def process_request(self, request: HttpRequest) -> None:
                self.logger.info(f"Request: {request.method} {request.path}")
                return None

            async def process_response(
                self, request: HttpRequest, response: HttpResponse
            ) -> HttpResponse:
                self.logger.info(f"Response: {response.status_code}")
                return response
        ```
    """

    @abstractmethod
    async def process_request(self, request: HttpRequest) -> Optional[Any]:
        """
        요청 처리 전 실행

        Args:
            request: HTTP 요청

        Returns:
            None: 다음 미들웨어/핸들러로 진행
            Any: 반환값이 있으면 early return (라우트 핸들러 스킵)

        Examples:
            # 정상 진행
            return None

            # 인증 실패 시 early return
            return HttpResponse.unauthorized("Invalid token")
        """
        pass

    @abstractmethod
    async def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        """
        응답 처리 후 실행

        Args:
            request: HTTP 요청
            response: HTTP 응답

        Returns:
            HttpResponse: 수정된 응답 (또는 원본 응답)

        Examples:
            # 응답 헤더 추가
            response.headers["X-Custom"] = "value"
            return response

            # 원본 응답 그대로 반환
            return response
        """
        pass
