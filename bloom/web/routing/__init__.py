"""라우팅 모듈

Manager → Registry 패턴을 사용한 HTTP 라우팅 시스템

- RouteEntry: 라우트 정보 값 객체 (method, path, handler)
- RouteRegistry: RouteEntry 리스트 관리
- RouteManager: 라우트 수집 및 관리
"""

from .entry import RouteEntry
from .registry import RouteRegistry
from .manager import RouteManager

__all__ = [
    "RouteEntry",
    "RouteRegistry",
    "RouteManager",
]
