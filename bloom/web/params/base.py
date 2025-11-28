"""파라미터 리졸버 베이스 클래스"""

from abc import ABC, abstractmethod
from typing import Any, Union, get_origin, get_args, TYPE_CHECKING
from types import UnionType, NoneType

if TYPE_CHECKING:
    from bloom.web.http import HttpRequest
    from .context import ResolverContext


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


class ParameterResolver(ABC):
    """
    핸들러 파라미터를 해석하는 베이스 클래스

    HTTP와 WebSocket/STOMP 양쪽에서 사용할 수 있는 통합 인터페이스입니다.
    각 리졸버는 특정 타입의 파라미터를 처리할 수 있는지 확인하고,
    컨텍스트로부터 해당 파라미터 값을 추출합니다.

    기존 HTTP 전용 resolve() 시그니처도 하위 호환성을 위해 지원합니다.
    """

    @abstractmethod
    def supports(self, param_name: str, param_type: type, origin: type | None) -> bool:
        """
        이 리졸버가 해당 파라미터를 처리할 수 있는지 확인

        Args:
            param_name: 파라미터 이름
            param_type: 파라미터 타입 (전체 타입, 예: RequestBody[UserData])
            origin: 제네릭 origin (예: RequestBody)

        Returns:
            처리 가능 여부
        """
        ...

    async def resolve_with_context(
        self,
        param_name: str,
        param_type: type,
        context: "ResolverContext",
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
        # 기본 구현: HTTP 컨텍스트인 경우 기존 resolve() 호출
        if context.is_http and context.http_request is not None:
            return await self.resolve(
                param_name, param_type, context.http_request, context.path_params
            )
        # WebSocket 컨텍스트인 경우 UNRESOLVED 반환 (서브클래스에서 오버라이드)
        from .registry import UNRESOLVED

        return UNRESOLVED

    @abstractmethod
    async def resolve(
        self,
        param_name: str,
        param_type: type,
        request: "HttpRequest",
        path_params: dict[str, str],
    ) -> Any:
        """
        파라미터 값 해석 (HTTP 전용, 하위 호환성)

        Args:
            param_name: 파라미터 이름
            param_type: 파라미터 타입
            request: HTTP 요청
            path_params: 경로 파라미터

        Returns:
            해석된 파라미터 값
        """
        ...


def get_type_info(param_type: type) -> tuple[type | None, tuple[type, ...]]:
    """
    타입 정보 추출

    Args:
        param_type: 파라미터 타입

    Returns:
        (origin, args) 튜플
        예: RequestBody[UserData] -> (RequestBody, (UserData,))
        예: list[Address] -> (list, (Address,))
        예: str -> (None, ())
    """
    origin = get_origin(param_type)
    args = get_args(param_type)
    return origin, args
