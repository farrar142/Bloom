"""MiddlewareGroup - 미들웨어 그룹

EntryGroup[Middleware]를 상속하여 미들웨어들을 그룹화합니다.
그룹 단위로 활성화/비활성화가 가능합니다.
"""

from bloom.core.abstract import EntryGroup

from .base import Middleware


class MiddlewareGroup(EntryGroup[Middleware]):
    """
    미들웨어 그룹

    EntryGroup[Middleware]를 상속하여 미들웨어 전용 그룹 제공.
    기존 API(middlewares 속성)를 유지합니다.

    사용 예시:
        group = MiddlewareGroup("auth")
        group.add(jwt_middleware, session_middleware)
        group.disable()  # 그룹 전체 비활성화
    """

    @property
    def middlewares(self) -> list[Middleware]:
        """그룹에 속한 미들웨어 리스트 (하위 호환성)"""
        return self._items

    def get_active_middlewares(self) -> list[Middleware]:
        """활성화된 미들웨어 목록 반환"""
        return self.get_active_items()

    def __repr__(self) -> str:
        status = "enabled" if self._enabled else "disabled"
        return f"MiddlewareGroup(name={self.name}, middlewares={len(self._items)}, {status})"
