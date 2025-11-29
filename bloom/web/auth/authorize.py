"""Authorize 데코레이터"""

from typing import Any, Callable, TypeVar

from bloom.core.container.element import Element
from bloom.web.http import HttpRequest
from ..handler import HttpMethodHandlerContainer


T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class AuthorizeElement[T, U](Element[T]):
    """
    인가(Authorization) 검사를 위한 Element

    핸들러 실행 전에 주어진 조건을 검사하여 접근 권한을 확인합니다.

    Attributes:
        target_type: 검사할 대상 타입 (예: Authentication)
        predicate: 조건 검사 함수 (예: lambda auth: auth.is_authenticated())
    """

    def __init__(
        self,
        target_type: Callable[[HttpRequest], U] | type[U],
        predicate: Callable[[U], bool],
    ):
        super().__init__()
        self.metadata["authorize_target_type"] = target_type
        self.metadata["authorize_predicate"] = predicate

    def __repr__(self) -> str:
        return f"AuthorizeElement(target_type={self.metadata['authorize_target_type'].__name__})"


def Authorize(
    target_type: Callable[[HttpRequest], T] | type[T], predicate: Callable[[T], bool]
) -> Callable[[F], F]:
    """
    인가(Authorization) 검사 데코레이터

    핸들러 실행 전에 주어진 조건을 검사합니다.
    조건을 만족하지 않으면 403 Forbidden을 반환합니다.

    사용법:
        @Get("/admin")
        @Authorize(Authentication, lambda auth: auth.has_authority("ADMIN"))
        async def admin_only(self) -> str:
            return "admin"

        # 간단히 인증만 체크
        @Get("/protected")
        @Authorize(Authentication, lambda auth: auth.is_authenticated())
        async def protected(self) -> str:
            return "protected"

    Args:
        target_type: 검사할 대상 타입 (예: Authentication)
        predicate: 조건 검사 함수

    Returns:
        데코레이터 함수
    """

    def decorator(func: F) -> F:
        container = HttpMethodHandlerContainer.get_or_create(func)
        container.add_elements(AuthorizeElement(target_type, predicate))

        return func

    return decorator
