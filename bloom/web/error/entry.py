"""ErrorHandlerEntry - 에러 핸들러 Entry

개별 에러 핸들러를 나타내는 Entry 클래스입니다.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from bloom.web.http import HttpRequest, HttpResponse


@dataclass
class ErrorHandlerEntry:
    """
    에러 핸들러 Entry

    개별 에러 핸들러의 정보를 담는 불변 데이터 클래스입니다.

    Attributes:
        exception_type: 처리할 예외 타입
        handler_method: 핸들러 메서드
        owner_cls: 핸들러를 소유한 클래스 (Controller 또는 Component)
        scope_prefix: Controller 스코프인 경우 RequestMapping prefix (없으면 글로벌)
    """

    exception_type: type[Exception]
    handler_method: Callable[..., Any]
    owner_cls: type | None = None
    scope_prefix: str | None = None

    def can_handle(self, exception: Exception) -> bool:
        """이 핸들러가 주어진 예외를 처리할 수 있는지 확인"""
        return isinstance(exception, self.exception_type)

    def is_exact_match(self, exception: Exception) -> bool:
        """예외 타입이 정확히 일치하는지 확인"""
        return type(exception) == self.exception_type

    def get_mro_distance(self, exception: Exception) -> int:
        """
        예외 타입과의 MRO 거리 반환

        정확한 타입이면 0, 부모 타입이면 MRO에서의 위치 반환.
        처리할 수 없으면 큰 값 반환.
        """
        exc_type = type(exception)
        if self.exception_type == exc_type:
            return 0
        try:
            return exc_type.__mro__.index(self.exception_type)
        except ValueError:
            return 9999

    def is_controller_scope(self) -> bool:
        """Controller 스코프인지 확인"""
        return self.scope_prefix is not None

    def matches_path(self, request_path: str) -> bool:
        """
        요청 경로가 이 핸들러의 스코프에 해당하는지 확인

        - 글로벌 스코프: 항상 True
        - Controller 스코프: 요청 경로가 prefix로 시작하면 True
        """
        if self.scope_prefix is None:
            return True  # 글로벌 스코프
        return request_path.startswith(self.scope_prefix)

    def __repr__(self) -> str:
        owner = self.owner_cls.__name__ if self.owner_cls else "global"
        scope = f"prefix={self.scope_prefix}" if self.scope_prefix else "global"
        return (
            f"ErrorHandlerEntry("
            f"exception={self.exception_type.__name__}, "
            f"method={self.handler_method.__name__}, "
            f"owner={owner}, {scope})"
        )
