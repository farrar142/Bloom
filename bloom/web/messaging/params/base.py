"""STOMP 메시징 파라미터 리졸버 베이스 클래스"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Union, get_origin, get_args, TYPE_CHECKING
from types import UnionType, NoneType

if TYPE_CHECKING:
    from ..session import WebSocketSession, Message


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


@dataclass
class MessageResolverContext:
    """
    메시지 핸들러 파라미터 해석을 위한 컨텍스트

    Attributes:
        session: WebSocket 세션
        message: STOMP 메시지 (없을 수도 있음, 예: @SubscribeMapping)
        path_params: 목적지 패턴에서 추출된 경로 파라미터
    """

    session: "WebSocketSession"
    message: "Message | None"
    path_params: dict[str, str]


class MessageParameterResolver(ABC):
    """
    STOMP 메시지 핸들러 파라미터를 해석하는 베이스 클래스

    web/params의 ParameterResolver와 유사하지만,
    HttpRequest 대신 WebSocketSession과 Message를 사용합니다.

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

    @abstractmethod
    async def resolve(
        self,
        param_name: str,
        param_type: type,
        context: MessageResolverContext,
    ) -> Any:
        """
        파라미터 값 해석

        Args:
            param_name: 파라미터 이름
            param_type: 파라미터 타입
            context: 메시지 리졸버 컨텍스트

        Returns:
            해석된 파라미터 값
        """
        ...
