"""ErrorHandlerRegistry - 에러 핸들러 Registry

스코프별로 에러 핸들러를 관리하는 Registry 클래스입니다.
"""

from typing import TYPE_CHECKING

from bloom.core.abstract import AbstractRegistry

from .container import ErrorHandlerContainer

if TYPE_CHECKING:
    pass


class ErrorHandlerRegistry(AbstractRegistry[ErrorHandlerContainer]):
    """
    에러 핸들러 Registry

    ErrorHandlerContainer 컬렉션을 관리하고 예외 타입에 맞는 핸들러를 검색합니다.

    핸들러 우선순위:
        1. 정확한 예외 타입 (MRO 거리 = 0)
        2. 부모 예외 타입 (MRO 거리가 작을수록 우선)
    """

    def __init__(self, scope_name: str = "global"):
        """
        Args:
            scope_name: 스코프 이름 (디버깅용)
        """
        super().__init__()
        self.scope_name = scope_name

    def add(self, handler: ErrorHandlerContainer) -> None:
        """에러 핸들러 추가"""
        self._entries.append(handler)

    def find_handler(
        self,
        exception: Exception,
        request_path: str | None = None,
    ) -> ErrorHandlerContainer | None:
        """
        예외에 맞는 핸들러 찾기

        Args:
            exception: 발생한 예외
            request_path: 요청 경로 (Controller 스코프 필터링용)

        Returns:
            매칭되는 핸들러 또는 None
        """
        candidates: list[ErrorHandlerContainer] = []

        for handler in self._entries:
            if not handler.can_handle(exception):
                continue

            # 경로 매칭 확인 (request_path가 주어진 경우)
            if request_path is not None and not handler.matches_path(request_path):
                continue

            candidates.append(handler)

        if not candidates:
            return None

        # MRO 거리로 정렬 (작을수록 우선)
        candidates.sort(key=lambda h: h.get_mro_distance(exception))
        return candidates[0]

    def get_handlers_for_exception(
        self, exception_type: type[Exception]
    ) -> list[ErrorHandlerContainer]:
        """특정 예외 타입을 처리할 수 있는 모든 핸들러 반환"""
        return [
            handler
            for handler in self._entries
            if any(issubclass(exception_type, t) for t in handler.exception_types)
        ]

    def __repr__(self) -> str:
        return f"ErrorHandlerRegistry(scope={self.scope_name}, handlers={len(self._entries)})"
