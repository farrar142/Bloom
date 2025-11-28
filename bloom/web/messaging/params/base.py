"""STOMP 메시징 파라미터 리졸버 베이스 클래스"""

from abc import abstractmethod
from typing import Any, Union, get_origin, get_args, TYPE_CHECKING
from types import UnionType, NoneType

# 공통 베이스 클래스와 컨텍스트 import
from bloom.web.params.base import ParameterResolver
from bloom.web.params.context import (
    ResolverContext,
    MessageResolverContext,
)

if TYPE_CHECKING:
    from bloom.web.http import HttpRequest


def is_optional(param_type: type) -> bool:
    """타입이 Optional인지 확인 (T | None 또는 Optional[T])"""
    origin = get_origin(param_type)
    if origin is Union or origin is UnionType:
        args = get_args(param_type)
        return NoneType in args or type(None) in args
    return False


def unwrap_optional(param_type: type) -> type:
    """Optional[T]에서 T를 추출, Optional이 아니면 그대로 반환"""
    if not is_optional(param_type):
        return param_type

    args = get_args(param_type)
    # None이 아닌 첫 번째 타입 반환
    for arg in args:
        if arg is not NoneType and arg is not type(None):
            return arg
    return param_type


class MessageParameterResolver(ParameterResolver):
    """
    STOMP 메시지 핸들러 파라미터를 해석하는 베이스 클래스

    ParameterResolver를 상속받아 HTTP와 WebSocket 양쪽에서 사용 가능합니다.
    기본적으로 WebSocket/STOMP 컨텍스트에서 동작하며,
    HTTP 컨텍스트에서는 UNRESOLVED를 반환합니다.

    각 리졸버는 특정 타입의 파라미터를 처리할 수 있는지 확인하고,
    컨텍스트로부터 해당 파라미터 값을 추출합니다.
    """

    @abstractmethod
    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        """
        이 리졸버가 해당 파라미터를 처리할 수 있는지 확인

        Args:
            param_name: 파라미터 이름
            param_type: 파라미터 타입 (전체 타입)
            origin: 제네릭 origin

        Returns:
            처리 가능 여부
        """
        ...

    async def resolve_with_context(
        self,
        param_name: str,
        param_type: type,
        context: ResolverContext,
    ) -> Any:
        """
        통합 컨텍스트를 사용한 파라미터 값 해석

        Args:
            param_name: 파라미터 이름
            param_type: 파라미터 타입
            context: 통합 리졸버 컨텍스트 (HTTP 또는 WebSocket)

        Returns:
            해석된 파라미터 값
        """
        # WebSocket 컨텍스트인 경우 resolve_message() 호출
        if context.is_websocket and isinstance(context, MessageResolverContext):
            return await self.resolve_message(param_name, param_type, context)
        # HTTP 컨텍스트인 경우 UNRESOLVED 반환 (서브클래스에서 오버라이드 가능)
        from .registry import UNRESOLVED

        return UNRESOLVED

    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: "HttpRequest",
        path_params: dict[str, str],
    ) -> Any:
        """
        HTTP 전용 파라미터 값 해석 (하위 호환성)

        MessageParameterResolver는 기본적으로 HTTP를 지원하지 않으므로
        UNRESOLVED를 반환합니다.
        """
        from .registry import UNRESOLVED

        return UNRESOLVED

    @abstractmethod
    async def resolve_message(
        self,
        param_name: str,
        param_type: type,
        context: MessageResolverContext,
    ) -> Any:
        """
        STOMP 메시지 컨텍스트에서 파라미터 값 해석

        Args:
            param_name: 파라미터 이름
            param_type: 파라미터 타입
            context: 메시지 리졸버 컨텍스트

        Returns:
            해석된 파라미터 값
        """
        ...


# MessageResolverContext re-export for backward compatibility
__all__ = [
    "MessageParameterResolver",
    "MessageResolverContext",
    "is_optional",
    "unwrap_optional",
]
