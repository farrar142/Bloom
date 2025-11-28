"""파라미터 리졸버 레지스트리"""

from dataclasses import dataclass
from typing import Any, Callable, get_origin

from bloom.web.http import HttpRequest

from .base import ParameterResolver


@dataclass
class CachedResolverInfo:
    """캐시된 리졸버 정보 (다중 후보 지원)"""

    param_name: str
    param_type: type
    # supports()가 True인 모든 리졸버 (우선순위 순서)
    resolvers: list[ParameterResolver]


class ParameterResolverRegistry:
    """
    파라미터 리졸버 레지스트리

    리졸버들을 등록하고, 파라미터 타입에 맞는 리졸버를 찾아 값을 해석합니다.
    등록 순서대로 supports()를 확인하므로, 더 구체적인 리졸버를 먼저 등록해야 합니다.

    핸들러별 리졸버 매핑을 캐싱하여 성능을 최적화합니다.
    """

    def __init__(self):
        self._resolvers: list[ParameterResolver] = []
        # 핸들러 → 파라미터별 리졸버 매핑 캐시
        self._resolver_cache: dict[int, list[CachedResolverInfo]] = {}

    def register(self, resolver: ParameterResolver) -> None:
        """리졸버 등록"""
        self._resolvers.append(resolver)

    def find_resolver(
        self, param_name: str, param_type: type
    ) -> ParameterResolver | None:
        """파라미터에 맞는 리졸버 찾기"""
        origin = get_origin(param_type)

        for resolver in self._resolvers:
            if resolver.supports(param_name, param_type, origin):
                return resolver
        return None

    def build_resolver_cache(
        self, handler_id: int, type_hints: dict[str, type]
    ) -> list[CachedResolverInfo]:
        """
        핸들러의 파라미터별 리졸버 매핑을 캐시에 저장

        Args:
            handler_id: 핸들러 고유 ID (id(handler))
            type_hints: 파라미터 이름 -> 타입 매핑

        Returns:
            캐시된 리졸버 정보 리스트
        """
        if handler_id in self._resolver_cache:
            return self._resolver_cache[handler_id]

        cached_resolvers: list[CachedResolverInfo] = []

        for param_name, param_type in type_hints.items():
            # self, return 등 스킵
            if param_name in ("self", "return"):
                continue

            origin = get_origin(param_type)

            # supports()가 True인 모든 리졸버 수집 (우선순위 순서)
            matching_resolvers: list[ParameterResolver] = []
            for resolver in self._resolvers:
                if resolver.supports(param_name, param_type, origin):
                    matching_resolvers.append(resolver)

            if matching_resolvers:
                cached_resolvers.append(
                    CachedResolverInfo(
                        param_name=param_name,
                        param_type=param_type,
                        resolvers=matching_resolvers,
                    )
                )

        self._resolver_cache[handler_id] = cached_resolvers
        return cached_resolvers

    async def resolve_parameters_cached(
        self,
        handler_id: int,
        type_hints: dict[str, type],
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> dict[str, Any]:
        """
        캐시를 활용한 파라미터 해석 (최적화된 버전)

        Args:
            handler_id: 핸들러 고유 ID (id(handler))
            type_hints: 파라미터 이름 -> 타입 매핑
            request: HTTP 요청
            path_params: 경로 파라미터

        Returns:
            파라미터 이름 -> 값 매핑
        """
        # 캐시에서 리졸버 매핑 조회 또는 생성
        cached_resolvers = self.build_resolver_cache(handler_id, type_hints)

        resolved: dict[str, Any] = {}

        for info in cached_resolvers:
            # 후보 리졸버들을 순서대로 시도, UNRESOLVED면 다음 리졸버로
            for resolver in info.resolvers:
                value = await resolver.resolve(
                    info.param_name, info.param_type, request, path_params
                )
                if value is not UNRESOLVED:
                    resolved[info.param_name] = value
                    break

        return resolved

    async def resolve_parameters(
        self,
        type_hints: dict[str, type],
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> dict[str, Any]:
        """
        모든 파라미터 해석 (비캐싱 버전 - 하위 호환성)

        Args:
            type_hints: 파라미터 이름 -> 타입 매핑
            request: HTTP 요청
            path_params: 경로 파라미터

        Returns:
            파라미터 이름 -> 값 매핑
        """
        resolved: dict[str, Any] = {}

        for param_name, param_type in type_hints.items():
            # self, return 등 스킵
            if param_name in ("self", "return"):
                continue

            origin = get_origin(param_type)

            # 여러 리졸버 시도 (UNRESOLVED 반환 시 다음으로)
            for resolver in self._resolvers:
                if resolver.supports(param_name, param_type, origin):
                    value = await resolver.resolve(
                        param_name, param_type, request, path_params
                    )
                    if value is not UNRESOLVED:
                        resolved[param_name] = value
                        break

        return resolved

    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._resolver_cache.clear()


# 해석 불가 마커
class _Unresolved:
    """리졸버가 값을 해석하지 못함을 나타내는 마커"""

    pass


UNRESOLVED = _Unresolved()


# 글로벌 레지스트리 인스턴스
_default_registry = ParameterResolverRegistry()


def get_default_registry() -> ParameterResolverRegistry:
    """기본 레지스트리 반환"""
    return _default_registry


def register_resolver(resolver: ParameterResolver) -> None:
    """기본 레지스트리에 리졸버 등록"""
    _default_registry.register(resolver)


async def resolve_parameters(
    type_hints: dict[str, type],
    request: HttpRequest,
    path_params: dict[str, str],
) -> dict[str, Any]:
    """
    기본 레지스트리를 사용하여 파라미터 해석

    Args:
        type_hints: 파라미터 이름 -> 타입 매핑
        request: HTTP 요청
        path_params: 경로 파라미터

    Returns:
        파라미터 이름 -> 값 매핑
    """
    return await _default_registry.resolve_parameters(type_hints, request, path_params)


async def resolve_parameters_cached(
    handler_id: int,
    type_hints: dict[str, type],
    request: HttpRequest,
    path_params: dict[str, str],
) -> dict[str, Any]:
    """
    캐시를 활용한 파라미터 해석 (최적화 버전)

    Args:
        handler_id: 핸들러 고유 ID (id(handler))
        type_hints: 파라미터 이름 -> 타입 매핑
        request: HTTP 요청
        path_params: 경로 파라미터

    Returns:
        파라미터 이름 -> 값 매핑
    """
    return await _default_registry.resolve_parameters_cached(
        handler_id, type_hints, request, path_params
    )
