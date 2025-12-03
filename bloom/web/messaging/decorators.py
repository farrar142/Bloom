"""메시징 데코레이터

@MessageMapping, @SubscribeMapping, @SendTo 등 메시징 엔드포인트 데코레이터를 제공합니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar
from functools import wraps

F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# Metadata Classes
# =============================================================================


@dataclass
class MessageMappingInfo:
    """메시지 매핑 정보"""

    destination: str
    pattern: re.Pattern[str]
    variables: list[str]  # 경로 변수 이름들
    method: Callable[..., Any] | None = None


@dataclass
class SubscribeMappingInfo:
    """구독 매핑 정보"""

    destination: str
    pattern: re.Pattern[str]
    variables: list[str]
    method: Callable[..., Any] | None = None


@dataclass
class SendToInfo:
    """응답 destination 정보"""

    destinations: list[str]
    broadcast: bool = False  # True면 모든 구독자에게, False면 요청자에게만


@dataclass
class MessageControllerInfo:
    """메시지 컨트롤러 정보"""

    destination_prefix: str = ""
    message_mappings: list[MessageMappingInfo] = field(default_factory=list)
    subscribe_mappings: list[SubscribeMappingInfo] = field(default_factory=list)


# =============================================================================
# Helper Functions
# =============================================================================


def _compile_destination_pattern(destination: str) -> tuple[re.Pattern[str], list[str]]:
    """destination 패턴을 정규식으로 변환

    Args:
        destination: "/chat/{room}" 형태의 패턴

    Returns:
        (컴파일된 패턴, 변수 이름 목록)
    """
    variables: list[str] = []

    # {var} 또는 {var:type} 패턴 추출
    pattern_str = destination
    var_pattern = re.compile(r"\{(\w+)(?::(\w+))?\}")

    def replace_var(match: re.Match[str]) -> str:
        var_name = match.group(1)
        var_type = match.group(2)  # 타입 힌트 (현재 미사용)
        variables.append(var_name)

        # 타입별 패턴 (확장 가능)
        if var_type == "int":
            return r"(\d+)"
        elif var_type == "path":
            return r"(.+)"
        else:
            return r"([^/]+)"

    pattern_str = var_pattern.sub(replace_var, pattern_str)
    pattern_str = f"^{pattern_str}$"

    return re.compile(pattern_str), variables


def _match_destination(
    pattern: re.Pattern[str],
    variables: list[str],
    destination: str,
) -> dict[str, str] | None:
    """destination과 패턴 매칭

    Returns:
        매칭된 변수 딕셔너리 또는 None
    """
    match = pattern.match(destination)
    if not match:
        return None

    return dict(zip(variables, match.groups()))


# =============================================================================
# Decorators
# =============================================================================


def MessageMapping(destination: str) -> Callable[[F], F]:
    """메시지 핸들러 데코레이터

    STOMP SEND 명령에 대한 핸들러를 등록합니다.

    Args:
        destination: 매칭할 destination 패턴 (예: "/chat/{room}")

    Examples:
        @MessageMapping("/chat/{room}")
        async def handle_chat(self, room: DestinationVariable[str], message: MessagePayload[ChatMessage]):
            ...
    """
    pattern, variables = _compile_destination_pattern(destination)

    def decorator(func: F) -> F:
        # 메타데이터 저장
        info = MessageMappingInfo(
            destination=destination,
            pattern=pattern,
            variables=variables,
            method=func,
        )

        if not hasattr(func, "__bloom_message_mappings__"):
            func.__bloom_message_mappings__ = []  # type: ignore
        func.__bloom_message_mappings__.append(info)  # type: ignore

        return func

    return decorator


def SubscribeMapping(destination: str) -> Callable[[F], F]:
    """구독 핸들러 데코레이터

    STOMP SUBSCRIBE 명령에 대한 핸들러를 등록합니다.
    클라이언트가 구독할 때 초기 데이터를 전송하는 데 사용됩니다.

    Args:
        destination: 매칭할 destination 패턴

    Examples:
        @SubscribeMapping("/topic/users/{room}")
        async def on_subscribe(self, room: DestinationVariable[str]) -> list[User]:
            return await self.get_room_users(room)
    """
    pattern, variables = _compile_destination_pattern(destination)

    def decorator(func: F) -> F:
        info = SubscribeMappingInfo(
            destination=destination,
            pattern=pattern,
            variables=variables,
            method=func,
        )

        if not hasattr(func, "__bloom_subscribe_mappings__"):
            func.__bloom_subscribe_mappings__ = []  # type: ignore
        func.__bloom_subscribe_mappings__.append(info)  # type: ignore

        return func

    return decorator


def SendTo(*destinations: str, broadcast: bool = True) -> Callable[[F], F]:
    """응답 destination 지정 데코레이터

    핸들러의 반환값을 지정된 destination으로 전송합니다.

    Args:
        destinations: 전송할 destination들
        broadcast: True면 해당 destination의 모든 구독자에게, False면 요청자에게만

    Examples:
        @MessageMapping("/chat/{room}")
        @SendTo("/topic/chat/{room}")
        async def handle_chat(self, message: MessagePayload[ChatMessage]) -> ChatResponse:
            return ChatResponse(...)
    """

    def decorator(func: F) -> F:
        info = SendToInfo(destinations=list(destinations), broadcast=broadcast)

        if not hasattr(func, "__bloom_send_to__"):
            func.__bloom_send_to__ = []  # type: ignore
        func.__bloom_send_to__.append(info)  # type: ignore

        return func

    return decorator


def MessageController(
    destination_prefix: str = "",
) -> Callable[[type], type]:
    """메시지 컨트롤러 데코레이터

    WebSocket/STOMP 메시지를 처리하는 컨트롤러를 정의합니다.
    DI 컨테이너에 자동 등록됩니다.

    Args:
        destination_prefix: destination 접두사 (예: "/app")

    Examples:
        @MessageController("/app")
        class ChatController:
            chat_service: ChatService  # DI 주입

            @MessageMapping("/chat/{room}")
            @SendTo("/topic/chat/{room}")
            async def send_message(
                self,
                room: DestinationVariable[str],
                message: MessagePayload[ChatMessage],
            ) -> ChatResponse:
                return await self.chat_service.process(room, message)
    """

    def decorator(cls: type) -> type:
        # 컨트롤러 메타데이터 수집
        message_mappings: list[MessageMappingInfo] = []
        subscribe_mappings: list[SubscribeMappingInfo] = []

        for name in dir(cls):
            if name.startswith("_"):
                continue

            method = getattr(cls, name, None)
            if not callable(method):
                continue

            # MessageMapping 수집
            if hasattr(method, "__bloom_message_mappings__"):
                for info in method.__bloom_message_mappings__:
                    # prefix 적용
                    full_dest = destination_prefix + info.destination
                    pattern, variables = _compile_destination_pattern(full_dest)
                    message_mappings.append(
                        MessageMappingInfo(
                            destination=full_dest,
                            pattern=pattern,
                            variables=variables,
                            method=method,
                        )
                    )

            # SubscribeMapping 수집
            if hasattr(method, "__bloom_subscribe_mappings__"):
                for info in method.__bloom_subscribe_mappings__:
                    full_dest = destination_prefix + info.destination
                    pattern, variables = _compile_destination_pattern(full_dest)
                    subscribe_mappings.append(
                        SubscribeMappingInfo(
                            destination=full_dest,
                            pattern=pattern,
                            variables=variables,
                            method=method,
                        )
                    )

        # 컨트롤러 정보 저장
        controller_info = MessageControllerInfo(
            destination_prefix=destination_prefix,
            message_mappings=message_mappings,
            subscribe_mappings=subscribe_mappings,
        )
        cls.__bloom_message_controller__ = controller_info  # type: ignore

        # DI 컨테이너에 등록
        from bloom.core.decorators import Component

        Component(cls)

        return cls

    return decorator


# =============================================================================
# Helper Functions for Runtime
# =============================================================================


def get_message_controller_info(cls: type) -> MessageControllerInfo | None:
    """클래스의 MessageController 정보 조회"""
    return getattr(cls, "__bloom_message_controller__", None)


def get_message_mappings(method: Callable[..., Any]) -> list[MessageMappingInfo]:
    """메서드의 MessageMapping 정보 조회"""
    return getattr(method, "__bloom_message_mappings__", [])


def get_subscribe_mappings(method: Callable[..., Any]) -> list[SubscribeMappingInfo]:
    """메서드의 SubscribeMapping 정보 조회"""
    return getattr(method, "__bloom_subscribe_mappings__", [])


def get_send_to_info(method: Callable[..., Any]) -> list[SendToInfo]:
    """메서드의 SendTo 정보 조회"""
    return getattr(method, "__bloom_send_to__", [])
