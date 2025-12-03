"""bloom.web.error - 에러 처리"""

from __future__ import annotations

import json
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, TYPE_CHECKING
from collections.abc import Awaitable

if TYPE_CHECKING:
    from .request import Request
    from .response import Response


# === HTTP Exceptions ===


class HTTPException(Exception):
    """
    HTTP 예외 기본 클래스.

    HTTP 상태 코드와 함께 예외를 발생시킵니다.

    사용 예:
        raise HTTPException(status_code=404, detail="User not found")
        raise NotFoundError("User not found")
    """

    def __init__(
        self,
        status_code: int = 500,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail or self._default_detail()
        self.headers = headers or {}
        super().__init__(self.detail)

    def _default_detail(self) -> str:
        """기본 상세 메시지"""
        return HTTP_STATUS_PHRASES.get(self.status_code, "Error")

    def to_dict(self) -> dict[str, Any]:
        """JSON 응답용 딕셔너리 변환"""
        return {
            "error": {
                "status": self.status_code,
                "message": self.detail,
            }
        }


# === Common HTTP Exceptions ===


class BadRequestError(HTTPException):
    """400 Bad Request"""

    def __init__(
        self, detail: str = "Bad Request", headers: dict[str, str] | None = None
    ):
        super().__init__(400, detail, headers)


class UnauthorizedError(HTTPException):
    """401 Unauthorized"""

    def __init__(
        self, detail: str = "Unauthorized", headers: dict[str, str] | None = None
    ):
        super().__init__(401, detail, headers)


class ForbiddenError(HTTPException):
    """403 Forbidden"""

    def __init__(
        self, detail: str = "Forbidden", headers: dict[str, str] | None = None
    ):
        super().__init__(403, detail, headers)


class NotFoundError(HTTPException):
    """404 Not Found"""

    def __init__(
        self, detail: str = "Not Found", headers: dict[str, str] | None = None
    ):
        super().__init__(404, detail, headers)


class MethodNotAllowedError(HTTPException):
    """405 Method Not Allowed"""

    def __init__(
        self, detail: str = "Method Not Allowed", headers: dict[str, str] | None = None
    ):
        super().__init__(405, detail, headers)


class ConflictError(HTTPException):
    """409 Conflict"""

    def __init__(self, detail: str = "Conflict", headers: dict[str, str] | None = None):
        super().__init__(409, detail, headers)


class ValidationError(HTTPException):
    """422 Unprocessable Entity (검증 실패)"""

    def __init__(
        self,
        detail: str = "Validation Error",
        errors: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(422, detail, headers)
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.errors:
            result["error"]["details"] = self.errors
        return result


class InternalServerError(HTTPException):
    """500 Internal Server Error"""

    def __init__(
        self,
        detail: str = "Internal Server Error",
        headers: dict[str, str] | None = None,
    ):
        super().__init__(500, detail, headers)


class ServiceUnavailableError(HTTPException):
    """503 Service Unavailable"""

    def __init__(
        self, detail: str = "Service Unavailable", headers: dict[str, str] | None = None
    ):
        super().__init__(503, detail, headers)


class UnprocessableEntityError(HTTPException):
    """422 Unprocessable Entity"""

    def __init__(
        self,
        detail: str = "Unprocessable Entity",
        headers: dict[str, str] | None = None,
    ):
        super().__init__(422, detail, headers)


class TooManyRequestsError(HTTPException):
    """429 Too Many Requests"""

    def __init__(
        self, detail: str = "Too Many Requests", headers: dict[str, str] | None = None
    ):
        super().__init__(429, detail, headers)


# === HTTP Status Phrases ===

HTTP_STATUS_PHRASES: dict[int, str] = {
    # 2xx
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    # 3xx
    301: "Moved Permanently",
    302: "Found",
    304: "Not Modified",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    # 4xx
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    409: "Conflict",
    410: "Gone",
    415: "Unsupported Media Type",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    # 5xx
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
    504: "Gateway Timeout",
}


# === Exception Handler ===


ExcT = TypeVar("ExcT", bound=Exception)
HandlerFunc = Callable[["Request", ExcT], "Response | Awaitable[Response] | Any"]


@dataclass
class ExceptionHandlerInfo:
    """예외 핸들러 정보"""

    exception_type: type[Exception]
    handler: HandlerFunc
    order: int = 0  # 낮을수록 먼저 (더 구체적인 예외 우선)


class ExceptionHandlerRegistry:
    """
    예외 핸들러 레지스트리.

    예외 타입별 핸들러를 등록하고 관리합니다.
    """

    def __init__(self) -> None:
        self._handlers: list[ExceptionHandlerInfo] = []

    def register(
        self,
        exception_type: type[Exception],
        handler: HandlerFunc,
        order: int = 0,
    ) -> None:
        """예외 핸들러 등록"""
        info = ExceptionHandlerInfo(
            exception_type=exception_type,
            handler=handler,
            order=order,
        )
        self._handlers.append(info)
        # order로 정렬 (낮은 값 우선)
        self._handlers.sort(key=lambda h: h.order)

    def find_handler(self, exc: Exception) -> HandlerFunc | None:
        """예외에 맞는 핸들러 찾기 (상속 계층 고려)"""
        exc_type = type(exc)

        # 가장 구체적인 타입 먼저 찾기 (MRO 순서)
        for handler_info in self._handlers:
            if isinstance(exc, handler_info.exception_type):
                return handler_info.handler

        return None

    def __len__(self) -> int:
        return len(self._handlers)


# === @ExceptionHandler Decorator ===


_controller_exception_handlers: dict[type, list[ExceptionHandlerInfo]] = {}


def ExceptionHandler(
    *exception_types: type[Exception],
    order: int = 0,
):
    """
    예외 핸들러 데코레이터.

    Controller 메서드에 적용하여 특정 예외를 처리합니다.

    사용 예:
        @Controller
        class UserController:
            @ExceptionHandler(NotFoundError)
            async def handle_not_found(self, request: Request, exc: NotFoundError):
                return JSONResponse({"error": str(exc)}, status_code=404)

            @ExceptionHandler(ValidationError, BadRequestError)
            async def handle_validation(self, request: Request, exc: Exception):
                return JSONResponse({"error": str(exc)}, status_code=400)
    """

    def decorator(func: Callable) -> Callable:
        # 메서드에 메타데이터 저장
        if not hasattr(func, "__bloom_exception_handlers__"):
            func.__bloom_exception_handlers__ = []  # type: ignore

        for exc_type in exception_types:
            func.__bloom_exception_handlers__.append(
                {  # type: ignore
                    "exception_type": exc_type,
                    "order": order,
                }
            )

        return func

    return decorator


def get_exception_handlers_from_controller(
    controller_class: type,
) -> list[ExceptionHandlerInfo]:
    """컨트롤러에서 @ExceptionHandler 메서드 추출"""
    handlers: list[ExceptionHandlerInfo] = []

    for name in dir(controller_class):
        if name.startswith("_"):
            continue

        method = getattr(controller_class, name, None)
        if not callable(method):
            continue

        exc_handlers = getattr(method, "__bloom_exception_handlers__", None)
        if not exc_handlers:
            continue

        for handler_meta in exc_handlers:
            handlers.append(
                ExceptionHandlerInfo(
                    exception_type=handler_meta["exception_type"],
                    handler=method,
                    order=handler_meta["order"],
                )
            )

    return handlers


# === Error Response Helpers ===


def create_error_response(
    exc: Exception,
    include_traceback: bool = False,
) -> dict[str, Any]:
    """예외를 JSON 응답용 딕셔너리로 변환"""
    from .response import JSONResponse

    if isinstance(exc, HTTPException):
        response_dict = exc.to_dict()
        status_code = exc.status_code
    else:
        response_dict = {
            "error": {
                "status": 500,
                "message": "Internal Server Error",
            }
        }
        status_code = 500

    if include_traceback:
        response_dict["error"]["traceback"] = traceback.format_exc()

    return response_dict


def json_error_response(
    exc: Exception,
    include_traceback: bool = False,
) -> "Response":
    """예외를 JSONResponse로 변환"""
    from .response import JSONResponse

    response_dict = create_error_response(exc, include_traceback)

    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        headers = exc.headers
    else:
        status_code = 500
        headers = None

    return JSONResponse(response_dict, status_code=status_code, headers=headers)
