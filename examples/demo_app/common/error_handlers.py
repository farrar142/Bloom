"""Demo App - 예외 핸들러

전역 및 컨트롤러별 예외 처리 예제입니다.

Features:
- @ExceptionHandler 데코레이터
- HTTPException 및 커스텀 예외 처리
- 일관된 에러 응답 포맷
"""

from __future__ import annotations

import logging
import traceback

from bloom.core import Component
from bloom.web import (
    Controller,
    Request,
    JSONResponse,
)
from bloom.web.error import (
    ExceptionHandler,
    HTTPException,
    NotFoundError,
    ValidationError,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 커스텀 예외 정의
# =============================================================================


class BusinessError(Exception):
    """비즈니스 로직 예외"""

    def __init__(self, message: str, code: str = "BUSINESS_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class InsufficientStockError(BusinessError):
    """재고 부족 예외"""

    def __init__(self, product_id: int, requested: int, available: int):
        self.product_id = product_id
        self.requested = requested
        self.available = available
        super().__init__(
            f"Insufficient stock for product {product_id}: "
            f"requested {requested}, available {available}",
            code="INSUFFICIENT_STOCK",
        )


class DuplicateEmailError(BusinessError):
    """중복 이메일 예외"""

    def __init__(self, email: str):
        self.email = email
        super().__init__(f"Email already exists: {email}", code="DUPLICATE_EMAIL")


# =============================================================================
# 전역 예외 핸들러 컨트롤러
# =============================================================================


@Controller
class GlobalExceptionHandler:
    """전역 예외 핸들러

    모든 컨트롤러에서 발생하는 예외를 처리합니다.
    Application에 등록하면 자동으로 예외 핸들러로 동작합니다.
    """

    @ExceptionHandler(NotFoundError)
    async def handle_not_found(
        self, request: Request, exc: NotFoundError
    ) -> JSONResponse:
        """404 Not Found 처리"""
        logger.warning(f"Not found: {request.path} - {exc}")
        return JSONResponse(
            {
                "error": {
                    "status": 404,
                    "code": "NOT_FOUND",
                    "message": str(exc),
                    "path": request.path,
                }
            },
            status_code=404,
        )

    @ExceptionHandler(ValidationError, BadRequestError)
    async def handle_validation_error(
        self, request: Request, exc: HTTPException
    ) -> JSONResponse:
        """400 Bad Request 처리"""
        logger.warning(f"Validation error: {request.path} - {exc}")

        details = getattr(exc, "details", None)
        return JSONResponse(
            {
                "error": {
                    "status": 400,
                    "code": "VALIDATION_ERROR",
                    "message": str(exc),
                    "details": details,
                    "path": request.path,
                }
            },
            status_code=400,
        )

    @ExceptionHandler(UnauthorizedError)
    async def handle_unauthorized(
        self, request: Request, exc: UnauthorizedError
    ) -> JSONResponse:
        """401 Unauthorized 처리"""
        logger.warning(f"Unauthorized: {request.path}")
        return JSONResponse(
            {
                "error": {
                    "status": 401,
                    "code": "UNAUTHORIZED",
                    "message": "Authentication required",
                    "path": request.path,
                }
            },
            status_code=401,
        )

    @ExceptionHandler(ForbiddenError)
    async def handle_forbidden(
        self, request: Request, exc: ForbiddenError
    ) -> JSONResponse:
        """403 Forbidden 처리"""
        logger.warning(f"Forbidden: {request.path}")
        return JSONResponse(
            {
                "error": {
                    "status": 403,
                    "code": "FORBIDDEN",
                    "message": "Access denied",
                    "path": request.path,
                }
            },
            status_code=403,
        )

    @ExceptionHandler(BusinessError)
    async def handle_business_error(
        self, request: Request, exc: BusinessError
    ) -> JSONResponse:
        """비즈니스 로직 에러 처리"""
        logger.error(f"Business error: {exc.code} - {exc.message}")
        return JSONResponse(
            {
                "error": {
                    "status": 422,
                    "code": exc.code,
                    "message": exc.message,
                    "path": request.path,
                }
            },
            status_code=422,
        )

    @ExceptionHandler(InsufficientStockError)
    async def handle_insufficient_stock(
        self, request: Request, exc: InsufficientStockError
    ) -> JSONResponse:
        """재고 부족 에러 처리 (더 구체적인 핸들러)"""
        logger.warning(
            f"Insufficient stock: product={exc.product_id}, "
            f"requested={exc.requested}, available={exc.available}"
        )
        return JSONResponse(
            {
                "error": {
                    "status": 422,
                    "code": exc.code,
                    "message": exc.message,
                    "details": {
                        "product_id": exc.product_id,
                        "requested": exc.requested,
                        "available": exc.available,
                    },
                    "path": request.path,
                }
            },
            status_code=422,
        )

    @ExceptionHandler(Exception, order=100)
    async def handle_unexpected_error(
        self, request: Request, exc: Exception
    ) -> JSONResponse:
        """예상치 못한 에러 처리 (fallback)

        order=100으로 설정하여 다른 핸들러보다 늦게 실행됩니다.
        """
        logger.exception(f"Unexpected error: {request.path}")
        return JSONResponse(
            {
                "error": {
                    "status": 500,
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "path": request.path,
                    # 개발 모드에서만 traceback 포함
                    # "traceback": traceback.format_exc(),
                }
            },
            status_code=500,
        )
