"""STOMP 메시징 파라미터 리졸버 레지스트리"""

from dataclasses import dataclass
from typing import Any, get_origin

from bloom.web.params.base import ParameterResolver
from bloom.web.params.context import MessageResolverContext


# 해석되지 않은 파라미터를 나타내는 센티널
class _Unresolved:
    pass


UNRESOLVED = _Unresolved()


@dataclass
class CachedResolverInfo:
    """캐시된 리졸버 정보"""

    param_name: str
    param_type: type
    resolvers: list[ParameterResolver]


class MessageParameterResolverRegistry:
    """
    STOMP 메시지 파라미터 리졸버 레지스트리

    리졸버들을 등록하고, 파라미터 타입에 맞는 리졸버를 찾아 값을 해석합니다.
    등록 순서대로 supports()를 확인하므로, 더 구체적인 리졸버를 먼저 등록해야 합니다.

    핸들러별 리졸버 매핑을 캐싱하여 성능을 최적화합니다.

    ParameterResolver를 기본 타입으로 사용하여 HTTP와 WebSocket 리졸버가 호환됩니다.
    HTTP 리졸버(ParameterResolver)와 WebSocket 리졸버(MessageParameterResolver) 모두 등록 가능합니다.
    """

    def __init__(self):
        self._resolvers: list[ParameterResolver] = []
        # 핸들러 → 파라미터별 리졸버 매핑 캐시
        self._resolver_cache: dict[int, list[CachedResolverInfo]] = {}

    def register(self, resolver: ParameterResolver) -> None:
        """리졸버 등록 (ParameterResolver 또는 MessageParameterResolver)"""
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

    async def resolve_with_context(
        self,
        handler_id: int,
        type_hints: dict[str, type],
        context: MessageResolverContext,
    ) -> dict[str, Any]:
        """
        통합 컨텍스트를 사용한 파라미터 해석

        HTTP의 ParameterResolverRegistry와 동일한 인터페이스를 제공합니다.

        Args:
            handler_id: 핸들러 고유 ID (id(handler))
            type_hints: 파라미터 이름 -> 타입 매핑
            context: 메시지 리졸버 컨텍스트

        Returns:
            파라미터 이름 -> 값 매핑
        """
        # 캐시에서 리졸버 매핑 조회 또는 생성
        cached_resolvers = self.build_resolver_cache(handler_id, type_hints)

        resolved: dict[str, Any] = {}

        for info in cached_resolvers:
            # 후보 리졸버들을 순서대로 시도
            for resolver in info.resolvers:
                value = await resolver.resolve_with_context(
                    info.param_name, info.param_type, context
                )
                if value is not UNRESOLVED:
                    resolved[info.param_name] = value
                    break

        return resolved

    async def resolve_parameters(
        self,
        handler_id: int,
        type_hints: dict[str, type],
        context: MessageResolverContext,
    ) -> dict[str, Any]:
        """
        캐시를 활용한 파라미터 해석 (하위 호환성)

        Args:
            handler_id: 핸들러 고유 ID (id(handler))
            type_hints: 파라미터 이름 -> 타입 매핑
            context: 메시지 리졸버 컨텍스트

        Returns:
            파라미터 이름 -> 값 매핑
        """
        return await self.resolve_with_context(handler_id, type_hints, context)

    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._resolver_cache.clear()


# 싱글톤 레지스트리
_default_registry: MessageParameterResolverRegistry | None = None


def get_default_message_registry() -> MessageParameterResolverRegistry:
    """기본 메시지 파라미터 리졸버 레지스트리 반환"""
    global _default_registry
    if _default_registry is None:
        _default_registry = MessageParameterResolverRegistry()
    return _default_registry
