"""RouteRegistry - 라우트 Registry

RouteEntry 리스트를 관리하고 RouteTrie를 통한 빠른 검색을 제공합니다.
"""

from typing import TYPE_CHECKING

from bloom.core.abstract import AbstractRegistry
from .trie import RouteTrie

if TYPE_CHECKING:
    from bloom.web.handler import HttpMethodHandlerContainer

from .entry import RouteEntry


class RouteRegistry(AbstractRegistry[RouteEntry]):
    """
    라우트 Registry

    RouteEntry 리스트를 관리하고, RouteTrie를 사용한 빠른 검색을 제공합니다.

    특징:
    - Entry 리스트 관리 (AbstractRegistry 기본 기능)
    - RouteTrie를 통한 O(log n) 라우트 검색
    - method + path로 핸들러 조회

    사용 예시:
        registry = RouteRegistry()
        registry.register(RouteEntry("GET", "/users", handler))

        # 핸들러 검색
        handler, params = registry.find("GET", "/users/123")
    """

    def __init__(self):
        super().__init__()
        self._trie = RouteTrie()

    def register(self, entry: RouteEntry) -> None:
        """Entry 등록 및 Trie에 삽입"""
        super().register(entry)
        self._trie.insert(entry.method, entry.path, entry.handler)

    def find(
        self, method: str, path: str
    ) -> tuple["HttpMethodHandlerContainer | None", dict[str, str]]:
        """
        요청에 맞는 핸들러 찾기

        Args:
            method: HTTP 메서드
            path: 요청 경로

        Returns:
            (핸들러, 경로 파라미터) 튜플
        """
        return self._trie.search(method, path)

    def get_all_routes(self) -> list[tuple[str, str, str]]:
        """
        등록된 모든 라우트 반환

        Returns:
            (method, path, handler_name) 리스트
        """
        return [
            (entry.method, entry.path, entry.handler.handler_method.__name__)
            for entry in self._entries
        ]

    def clear(self) -> None:
        """Registry 및 Trie 초기화"""
        super().clear()
        self._trie = RouteTrie()

    def __repr__(self) -> str:
        return f"RouteRegistry({len(self._entries)} routes)"
