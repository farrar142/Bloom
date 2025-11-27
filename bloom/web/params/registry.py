"""파라미터 리졸버 레지스트리"""

from typing import Any, get_origin

from bloom.web.http import HttpRequest

from .base import ParameterResolver


class ParameterResolverRegistry:
    """
    파라미터 리졸버 레지스트리

    리졸버들을 등록하고, 파라미터 타입에 맞는 리졸버를 찾아 값을 해석합니다.
    등록 순서대로 supports()를 확인하므로, 더 구체적인 리졸버를 먼저 등록해야 합니다.
    """

    def __init__(self):
        self._resolvers: list[ParameterResolver] = []

    def register(self, resolver: ParameterResolver) -> None:
        """리졸버 등록"""
        self._resolvers.append(resolver)

    def register_first(self, resolver: ParameterResolver) -> None:
        """리졸버를 맨 앞에 등록 (우선순위 높음)"""
        self._resolvers.insert(0, resolver)

    def find_resolver(
        self, param_name: str, param_type: type
    ) -> ParameterResolver | None:
        """파라미터에 맞는 리졸버 찾기"""
        origin = get_origin(param_type)

        for resolver in self._resolvers:
            if resolver.supports(param_name, param_type, origin):
                return resolver
        return None

    async def resolve_parameters(
        self,
        type_hints: dict[str, type],
        request: HttpRequest,
        path_params: dict[str, str],
    ) -> dict[str, Any]:
        """
        모든 파라미터 해석

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
