"""bloom.web.routing.router - URL Router with path parameter support"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, TYPE_CHECKING

from .trie import PathTrie, TrieMatch

from ..request import HttpRequest
from ..response import HttpResponse


# Type alias for route handlers
RouteHandler = Callable[[HttpRequest], Awaitable[Any] | Any]


@dataclass
class RouteMatch:
    """라우트 매칭 결과"""

    route: "Route"
    path_params: dict[str, str] = field(default_factory=dict)

    @property
    def handler(self) -> RouteHandler:
        return self.route.handler


@dataclass
class Route:
    """단일 라우트 정의"""

    path: str
    method: str
    handler: RouteHandler
    name: str | None = None

    # 컴파일된 패턴 (지연 초기화) - 하위 호환성을 위해 유지
    _pattern: re.Pattern[str] | None = field(default=None, repr=False)
    _param_names: list[str] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self._compile_pattern()

    def _compile_pattern(self) -> None:
        """경로 패턴을 정규식으로 컴파일

        지원 패턴:
        - /users/{id} → /users/(?P<id>[^/]+)
        - /users/{id:int} → /users/(?P<id>[0-9]+)
        - /files/{path:path} → /files/(?P<path>.+)
        """
        pattern = self.path
        param_names: list[str] = []

        # {param} 또는 {param:type} 패턴 찾기
        param_pattern = re.compile(r"\{(\w+)(?::(\w+))?\}")

        def replace_param(match: re.Match[str]) -> str:
            name = match.group(1)
            param_type = match.group(2) or "str"
            param_names.append(name)

            # 타입별 정규식
            type_patterns = {
                "int": r"[0-9]+",
                "str": r"[^/]+",
                "path": r".+",
                "uuid": r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                "slug": r"[a-zA-Z0-9_-]+",
            }

            regex = type_patterns.get(param_type, r"[^/]+")
            return f"(?P<{name}>{regex})"

        pattern = param_pattern.sub(replace_param, pattern)

        # 전체 경로 매칭
        self._pattern = re.compile(f"^{pattern}$")
        self._param_names = param_names

    def match(self, path: str, method: str) -> RouteMatch | None:
        """경로와 메서드가 이 라우트와 매칭되는지 확인"""
        if self.method != method and self.method != "*":
            return None

        if self._pattern is None:
            return None

        m = self._pattern.match(path)
        if m is None:
            return None

        return RouteMatch(
            route=self,
            path_params=m.groupdict(),
        )


class Router:

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix.rstrip("/")
        self.routes: list[Route] = []
        self._sub_routers: list[tuple[str, Router]] = []
        # HTTP 메서드별 PathTrie
        self._tries: dict[str, PathTrie[Route]] = {}

    def _get_trie(self, method: str) -> PathTrie[Route]:
        """HTTP 메서드별 Trie 가져오기 (없으면 생성)"""
        method = method.upper()
        if method not in self._tries:
            self._tries[method] = PathTrie()
        return self._tries[method]

    def add_route(
        self,
        path: str,
        method: str,
        handler: RouteHandler,
        name: str | None = None,
    ) -> Route:
        """라우트 추가"""
        full_path = self.prefix + path if not path.startswith(self.prefix) else path
        route = Route(
            path=full_path,
            method=method.upper(),
            handler=handler,
            name=name or handler.__name__,
        )
        self.routes.append(route)
        # Trie에 추가
        self._get_trie(method).insert(route)
        return route

    def route(
        self,
        path: str,
        methods: list[str] | None = None,
        name: str | None = None,
    ) -> Callable[[RouteHandler], RouteHandler]:
        """라우트 데코레이터 (여러 메서드 지원)"""
        methods = methods or ["GET"]

        def decorator(handler: RouteHandler) -> RouteHandler:
            for method in methods:
                self.add_route(path, method, handler, name)
            return handler

        return decorator

    def get(
        self, path: str, name: str | None = None
    ) -> Callable[[RouteHandler], RouteHandler]:
        """GET 라우트 데코레이터"""
        return self.route(path, methods=["GET"], name=name)

    def post(
        self, path: str, name: str | None = None
    ) -> Callable[[RouteHandler], RouteHandler]:
        """POST 라우트 데코레이터"""
        return self.route(path, methods=["POST"], name=name)

    def put(
        self, path: str, name: str | None = None
    ) -> Callable[[RouteHandler], RouteHandler]:
        """PUT 라우트 데코레이터"""
        return self.route(path, methods=["PUT"], name=name)

    def delete(
        self, path: str, name: str | None = None
    ) -> Callable[[RouteHandler], RouteHandler]:
        """DELETE 라우트 데코레이터"""
        return self.route(path, methods=["DELETE"], name=name)

    def patch(
        self, path: str, name: str | None = None
    ) -> Callable[[RouteHandler], RouteHandler]:
        """PATCH 라우트 데코레이터"""
        return self.route(path, methods=["PATCH"], name=name)

    def include_router(self, router: "Router", prefix: str = "") -> None:
        """서브 라우터 추가

        서브 라우터의 모든 라우트를 현재 라우터의 Trie에 병합합니다.
        """
        self._sub_routers.append((prefix, router))

        # 서브 라우터의 라우트들을 현재 라우터의 Trie에 병합
        for route in router.routes:
            # prefix 적용 (서브 라우터의 prefix는 이미 적용되어 있음)
            full_path = prefix + route.path if prefix else route.path
            merged_route = Route(
                path=full_path,
                method=route.method,
                handler=route.handler,
                name=route.name,
            )
            self._get_trie(route.method).insert(merged_route)

    def match(self, path: str, method: str) -> RouteMatch | None:
        """경로와 메서드로 라우트 찾기 (PathTrie 사용)"""
        method = method.upper()

        # Trie에서 검색
        trie = self._tries.get(method)
        if trie:
            result = trie.find(path)
            if result:
                return RouteMatch(
                    route=result.item,
                    path_params=result.path_params,
                )

        # wildcard (*) 메서드 검색
        wildcard_trie = self._tries.get("*")
        if wildcard_trie:
            result = wildcard_trie.find(path)
            if result:
                return RouteMatch(
                    route=result.item,
                    path_params=result.path_params,
                )

        return None

    def get_routes(self) -> list[Route]:
        """모든 라우트 목록 (서브 라우터 포함)"""
        all_routes = list(self.routes)
        for prefix, router in self._sub_routers:
            for route in router.get_routes():
                # 서브 라우터의 라우트에 prefix 추가
                full_path = prefix + route.path if prefix else route.path
                all_routes.append(
                    Route(
                        path=full_path,
                        method=route.method,
                        handler=route.handler,
                        name=route.name,
                    )
                )
        return all_routes
