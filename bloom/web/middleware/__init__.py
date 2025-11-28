"""
미들웨어 시스템

요청/응답을 가로채어 공통 로직을 처리하는 컴포넌트들입니다.
인증, 로깅, CORS, 에러 핸들링 등에 활용됩니다.

구성 요소:
    - Middleware: 미들웨어 추상 클래스 (상속하여 구현)
    - MiddlewareChain: 미들웨어 실행 순서 관리
    - MiddlewareGroup: 관련 미들웨어 그룹화

내장 미들웨어:
    - CorsMiddleware: CORS 헤더 처리
    - ErrorHandlerMiddleware: 예외를 HTTP 응답으로 변환

빠른 시작:
    1. Middleware 상속하여 미들웨어 구현:

        ```python
        from bloom import Component
        from bloom.web import HttpRequest, HttpResponse
        from bloom.web.middleware import Middleware

        @Component
        class LoggingMiddleware(Middleware):
            async def process_request(self, request: HttpRequest):
                print(f"Request: {request.method} {request.path}")
                return None  # 다음으로 진행

            async def process_response(self, request, response):
                print(f"Response: {response.status_code}")
                return response
        ```

    2. MiddlewareChain 설정 (Factory로 생성):

        ```python
        from bloom.core.decorators import Factory
        from bloom.web.middleware import Middleware, MiddlewareChain

        @Component
        class MiddlewareConfig:
            @Factory
            def middleware_chain(self, *middlewares: Middleware) -> MiddlewareChain:
                chain = MiddlewareChain()
                chain.add_group_after(*middlewares)
                return chain
        ```

    3. Application 초기화 시 자동으로 Router에 적용됨

    4. 내장 미들웨어 사용:

        ```python
        from bloom import Component
        from bloom.web.middleware import CorsMiddleware, ErrorHandlerMiddleware

        @Component
        class MyCors(CorsMiddleware):
            allow_origins = ["https://example.com"]
            allow_credentials = True

        @Component
        class MyErrorHandler(ErrorHandlerMiddleware):
            debug = True  # 개발 환경에서 스택 트레이스 표시
        ```

실행 순서:
    요청: Middleware A → B → C → 핸들러
    응답: 핸들러 → C → B → A (역순)

GroupRegistry 패턴:
    - EntryGroup[T]: 항목들을 그룹화
    - GroupRegistry[T]: EntryGroup들을 관리
    - MiddlewareGroup: EntryGroup[Middleware] 상속
    - MiddlewareChain: GroupRegistry[Middleware] 상속
"""

from .base import Middleware
from ..builtin.middleware import CorsMiddleware, ErrorHandlerMiddleware
from .group import MiddlewareGroup
from .registry import MiddlewareChain

__all__ = [
    "Middleware",
    "MiddlewareChain",
    "MiddlewareGroup",
    "CorsMiddleware",
    "ErrorHandlerMiddleware",
]
