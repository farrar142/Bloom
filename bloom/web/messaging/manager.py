"""
WebSocket Manager - Manager-Registry-Entry 패턴을 사용한 WebSocket 관리
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from bloom.core.abstract import AbstractManager
from bloom.core.container import ComponentContainer
from bloom.core.container.element import Element

from .entry import (
    MessageExceptionHandlerEntry,
    MessageHandlerEntry,
    StompEndpointEntry,
    SubscribeHandlerEntry,
)
from .registry import (
    MessageExceptionHandlerRegistry,
    MessageHandlerRegistry,
    MessageBrokerRegistry,
    StompEndpointRegistry,
    SubscribeHandlerRegistry,
)


if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager


class EnableWebSocketElement(Element):
    """EnableWebSocket 데코레이터의 메타데이터를 저장하는 Element"""

    key = "enable_websocket"

    def __init__(self, configurer_cls: type | None = None):
        super().__init__()
        self.metadata["configurer_cls"] = configurer_cls

    @property
    def configurer_cls(self) -> type | None:
        return self.metadata.get("configurer_cls")


def EnableWebSocket(cls_or_configurer: type | None = None):
    """
    WebSocket 설정을 활성화하는 데코레이터

    두 가지 사용법을 지원합니다:
    1. 인자 없이 사용:
        @Component
        @EnableWebSocket
        class WebSocketConfig:
            pass

    2. configurer 클래스와 함께 사용:
        @EnableWebSocket(MyWebSocketConfigurer)
        class MyApplication:
            pass
    """

    def apply_decorator(cls: type, configurer: type | None = None) -> type:
        container = ComponentContainer.get_or_create(cls)
        container.add_elements(EnableWebSocketElement(configurer))
        return cls

    # @EnableWebSocket (인자 없이 사용)
    if cls_or_configurer is not None and isinstance(cls_or_configurer, type):
        # 직접 클래스가 전달된 경우 - 인자 없이 사용한 것
        return apply_decorator(cls_or_configurer, None)

    # @EnableWebSocket(SomeConfigurer) 형태
    def decorator(cls: type) -> type:
        return apply_decorator(cls, cls_or_configurer)

    return decorator


def is_websocket_enabled(cls: type) -> bool:
    """클래스에 EnableWebSocket이 적용되었는지 확인"""
    container = ComponentContainer.get_container(cls)
    if container is None:
        return False
    return container.has_element(EnableWebSocketElement)


def get_websocket_configurer(cls: type) -> type | None:
    """EnableWebSocket에서 설정된 configurer 클래스 반환"""
    container = ComponentContainer.get_container(cls)
    if container is None:
        return None
    elements = [e for e in container.elements if isinstance(e, EnableWebSocketElement)]
    return elements[0].configurer_cls if elements else None


class WebSocketManager(AbstractManager):
    """
    WebSocket 관련 Registry들을 통합 관리하는 Manager

    4개의 Registry를 관리:
    - StompEndpointRegistry: STOMP 엔드포인트 관리
    - MessageHandlerRegistry: @MessageMapping 핸들러 관리
    - SubscribeHandlerRegistry: @SubscribeMapping 핸들러 관리
    - MessageExceptionHandlerRegistry: @MessageExceptionHandler 핸들러 관리
    """

    def __init__(self, container_manager: "ContainerManager | None" = None):
        super().__init__()
        self._container_manager = container_manager
        self._endpoint_registry = StompEndpointRegistry()
        self._message_handler_registry = MessageHandlerRegistry()
        self._subscribe_handler_registry = SubscribeHandlerRegistry()
        self._exception_handler_registry = MessageExceptionHandlerRegistry()

    @property
    def endpoint_registry(self) -> StompEndpointRegistry:
        """STOMP 엔드포인트 레지스트리"""
        return self._endpoint_registry

    @property
    def message_handler_registry(self) -> MessageHandlerRegistry:
        """메시지 핸들러 레지스트리"""
        return self._message_handler_registry

    @property
    def subscribe_handler_registry(self) -> SubscribeHandlerRegistry:
        """구독 핸들러 레지스트리"""
        return self._subscribe_handler_registry

    @property
    def exception_handler_registry(self) -> MessageExceptionHandlerRegistry:
        """예외 핸들러 레지스트리"""
        return self._exception_handler_registry

    @property
    def enabled(self) -> bool:
        """WebSocket이 활성화되어 있는지 확인 (엔드포인트가 하나라도 있으면 활성화)"""
        return len(self._endpoint_registry._entries) > 0

    @property
    def endpoints(self) -> list[StompEndpointEntry]:
        """등록된 모든 STOMP 엔드포인트 반환"""
        return list(self._endpoint_registry._entries)

    def is_websocket_path(self, path: str) -> bool:
        """주어진 경로가 WebSocket 엔드포인트와 매칭되는지 확인"""
        for entry in self._endpoint_registry._entries:
            if entry.is_path_match(path):
                return True
        return False

    def get_endpoint_for_path(self, path: str) -> StompEndpointEntry | None:
        """주어진 경로에 해당하는 엔드포인트 반환"""
        for entry in self._endpoint_registry._entries:
            if entry.is_path_match(path):
                return entry
        return None

    def get_endpoint_paths(self) -> list[str]:
        """등록된 모든 엔드포인트 경로 반환"""
        return [entry.path for entry in self._endpoint_registry._entries]

    def initialize(self, container_manager: "ContainerManager | None" = None) -> None:
        """
        WebSocketManager 초기화

        ContainerManager에서 Factory로 생성된 Registry들을 검색하여 사용하고,
        MessageController들의 핸들러를 수집합니다.

        Args:
            container_manager: 레지스트리와 핸들러를 검색할 ContainerManager (옵션)
        """
        if self._initialized:
            return

        if container_manager is not None:
            self._container_manager = container_manager

            # Factory로 생성된 StompEndpointRegistry 검색 (registry.py 버전)
            endpoint_registries = container_manager.get_sub_instances(
                StompEndpointRegistry
            )
            if endpoint_registries:
                self._endpoint_registry = endpoint_registries[0]

            # Factory로 생성된 MessageHandlerRegistry 검색
            message_registries = container_manager.get_sub_instances(
                MessageHandlerRegistry
            )
            if message_registries:
                self._message_handler_registry = message_registries[0]

            # Factory로 생성된 SubscribeHandlerRegistry 검색
            subscribe_registries = container_manager.get_sub_instances(
                SubscribeHandlerRegistry
            )
            if subscribe_registries:
                self._subscribe_handler_registry = subscribe_registries[0]

            # Factory로 생성된 MessageExceptionHandlerRegistry 검색
            exception_registries = container_manager.get_sub_instances(
                MessageExceptionHandlerRegistry
            )
            if exception_registries:
                self._exception_handler_registry = exception_registries[0]

        self._initialized = True

    def register_endpoint(
        self,
        path: str,
        allowed_origins: list[str] | None = None,
        sockjs_enabled: bool = False,
        heartbeat_send: int = 10000,
        heartbeat_receive: int = 10000,
    ) -> StompEndpointEntry:
        """STOMP 엔드포인트 등록"""
        entry = StompEndpointEntry(
            path=path,
            allowed_origins=allowed_origins or ["*"],
            sockjs_enabled=sockjs_enabled,
            heartbeat_send=heartbeat_send,
            heartbeat_receive=heartbeat_receive,
        )
        self._endpoint_registry._entries.append(entry)
        return entry

    def register_message_handler(
        self,
        destination_pattern: str,
        handler_container: Any,
        owner_cls: type | None = None,
        send_to: str | None = None,
        send_to_user: str | None = None,
    ) -> MessageHandlerEntry:
        """메시지 핸들러 등록"""
        return self._message_handler_registry.add(
            destination_pattern=destination_pattern,
            handler_container=handler_container,
            owner_cls=owner_cls,
            send_to=send_to,
            send_to_user=send_to_user,
        )

    def register_subscribe_handler(
        self,
        destination_pattern: str,
        handler_container: Any,
        owner_cls: type | None = None,
    ) -> SubscribeHandlerEntry:
        """구독 핸들러 등록"""
        return self._subscribe_handler_registry.add(
            destination_pattern=destination_pattern,
            handler_container=handler_container,
            owner_cls=owner_cls,
        )

    def register_exception_handler(
        self,
        exception_type: type[Exception],
        handler_container: Any,
        owner_cls: type | None = None,
    ) -> MessageExceptionHandlerEntry:
        """예외 핸들러 등록"""
        return self._exception_handler_registry.add(
            exception_type=exception_type,
            handler_container=handler_container,
            owner_cls=owner_cls,
        )

    def find_endpoint(self, path: str) -> StompEndpointEntry | None:
        """경로로 STOMP 엔드포인트 찾기"""
        return self._endpoint_registry.find_endpoint(path)

    def find_message_handler(
        self, destination: str
    ) -> tuple[MessageHandlerEntry, dict[str, str]] | None:
        """destination으로 메시지 핸들러 찾기"""
        return self._message_handler_registry.find_handler(destination)

    def find_subscribe_handler(
        self, destination: str
    ) -> tuple[SubscribeHandlerEntry, dict[str, str]] | None:
        """destination으로 구독 핸들러 찾기"""
        return self._subscribe_handler_registry.find_handler(destination)

    def find_exception_handler(
        self, exception: Exception
    ) -> MessageExceptionHandlerEntry | None:
        """예외 타입으로 예외 핸들러 찾기"""
        return self._exception_handler_registry.find_handler(exception)

    async def handle_message(
        self,
        destination: str,
        payload: Any,
        headers: dict[str, Any] | None = None,
    ) -> Any:
        """
        메시지 처리

        Args:
            destination: STOMP destination
            payload: 메시지 페이로드
            headers: STOMP 헤더

        Returns:
            핸들러 결과 (send_to가 있으면 해당 destination으로 전송)
        """
        result = self.find_message_handler(destination)
        if result is None:
            return None

        entry, path_vars = result
        try:
            handler = entry.handler_container
            # HandlerContainer에서 실제 메서드 호출
            if hasattr(handler, "invoke"):
                invoke_result = await handler.invoke(payload, headers or {}, path_vars)
            else:
                # 직접 callable인 경우
                invoke_result = handler(payload)
                if hasattr(invoke_result, "__await__"):
                    invoke_result = await invoke_result
            return invoke_result
        except Exception as e:
            # 예외 핸들러 찾기
            exc_entry = self.find_exception_handler(e)
            if exc_entry is not None:
                exc_handler = exc_entry.handler_container
                if hasattr(exc_handler, "invoke"):
                    return await exc_handler.invoke(e)
                else:
                    exc_result = exc_handler(e)
                    if hasattr(exc_result, "__await__"):
                        exc_result = await exc_result
                    return exc_result
            raise

    async def handle_subscribe(
        self,
        destination: str,
        headers: dict[str, Any] | None = None,
    ) -> Any:
        """
        구독 요청 처리

        Args:
            destination: 구독할 destination
            headers: STOMP 헤더

        Returns:
            초기 데이터 (있는 경우)
        """
        result = self.find_subscribe_handler(destination)
        if result is None:
            return None

        entry, path_vars = result
        handler = entry.handler_container
        if hasattr(handler, "invoke"):
            return await handler.invoke(headers or {}, path_vars)
        else:
            invoke_result = handler()
            if hasattr(invoke_result, "__await__"):
                invoke_result = await invoke_result
            return invoke_result

    def get_all_endpoints(self) -> list[StompEndpointEntry]:
        """모든 STOMP 엔드포인트 반환"""
        return list(self._endpoint_registry._entries)

    def get_all_message_handlers(self) -> list[MessageHandlerEntry]:
        """모든 메시지 핸들러 반환"""
        return list(self._message_handler_registry._entries)

    def get_all_subscribe_handlers(self) -> list[SubscribeHandlerEntry]:
        """모든 구독 핸들러 반환"""
        return list(self._subscribe_handler_registry._entries)

    def get_all_exception_handlers(self) -> list[MessageExceptionHandlerEntry]:
        """모든 예외 핸들러 반환"""
        return list(self._exception_handler_registry._entries)

    def clear(self) -> None:
        """모든 레지스트리 초기화"""
        self._endpoint_registry.clear()
        self._message_handler_registry.clear()
        self._subscribe_handler_registry.clear()
        self._exception_handler_registry.clear()
