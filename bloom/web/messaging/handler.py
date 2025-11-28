"""STOMP 프로토콜 핸들러 (내부 사용)"""

from __future__ import annotations

import asyncio
import re
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager

from bloom.core.container import HandlerContainer, ComponentContainer

from .message import Message, StompFrame, StompCommand
from .broker import SimpleBroker
from .session import WebSocketSession, WebSocketDisconnect, WebSocketSessionManager
from .controller import is_message_controller, get_prefix


@dataclass
class MessageHandlerInfo:
    """메시지 핸들러 정보"""

    destination_pattern: str
    handler_container: HandlerContainer
    send_to: str | None = None
    send_to_user: str | None = None


@dataclass
class SubscribeHandlerInfo:
    """구독 핸들러 정보"""

    destination_pattern: str
    handler_container: HandlerContainer


class StompProtocolHandler:
    """
    STOMP 프로토콜 핸들러 (내부 사용)

    STOMP 프레임을 파싱하고 적절한 핸들러로 라우팅.
    개발자가 직접 사용하지 않고 내부적으로만 동작.

    주요 기능:
        - CONNECT/DISCONNECT 처리
        - SUBSCRIBE/UNSUBSCRIBE 처리
        - SEND → @MessageMapping 라우팅
        - 핸들러 반환값 → @SendTo/@SendToUser 발행
    """

    # 애플리케이션 목적지 프리픽스 (클라이언트 SEND 시 사용)
    APP_DESTINATION_PREFIX = "/app"

    def __init__(
        self,
        broker: SimpleBroker,
        session_manager: WebSocketSessionManager,
        container_manager: "ContainerManager | None" = None,
    ):
        self._broker = broker
        self._session_manager = session_manager
        self._container_manager = container_manager

        # 핸들러 레지스트리
        self._message_handlers: list[MessageHandlerInfo] = []
        self._subscribe_handlers: list[SubscribeHandlerInfo] = []
        self._exception_handlers: dict[type[Exception], HandlerContainer] = {}

    def collect_handlers(self, manager: "ContainerManager") -> None:
        """
        ContainerManager에서 메시지 핸들러 수집

        @MessageController 또는 @Controller로 등록된 클래스들의 핸들러 메서드들을 수집.

        주의: @Controller의 @RequestMapping path와 STOMP 메시징 path는 별개입니다.
        @MessageMapping, @SendTo 등은 @RequestMapping prefix의 영향을 받지 않습니다.
        """
        self._container_manager = manager

        # get_all_containers()는 dict[type, dict[str, Container]]를 반환
        for target_type, qualifier_containers in manager.get_all_containers().items():
            for qualifier, container in qualifier_containers.items():
                target = container.target

                # ComponentContainer 타입만 처리 (Component, Controller, MessageController 모두 포함)
                if not isinstance(container, ComponentContainer):
                    continue

                # prefix 결정: @MessageController만 prefix 사용
                # @Controller의 @RequestMapping은 HTTP path이므로 STOMP path에 영향 없음
                prefix = ""
                if is_message_controller(target):
                    prefix = get_prefix(target)

                # 메서드들에서 핸들러 찾기
                for name, method in inspect.getmembers(
                    target, predicate=inspect.isfunction
                ):
                    handler_container = HandlerContainer.get_container(method)
                    if not handler_container:
                        continue

                    # @MessageMapping
                    message_dest = handler_container.get_metadata(
                        "message_mapping", raise_exception=False
                    )
                    if message_dest is not None:
                        full_dest = prefix + message_dest if prefix else message_dest

                        send_to = handler_container.get_metadata(
                            "send_to", raise_exception=False
                        )
                        send_to_user = handler_container.get_metadata(
                            "send_to_user", raise_exception=False
                        )

                        self._message_handlers.append(
                            MessageHandlerInfo(
                                destination_pattern=full_dest,
                                handler_container=handler_container,
                                send_to=send_to,
                                send_to_user=send_to_user,
                            )
                        )

                    # @SubscribeMapping
                    subscribe_dest = handler_container.get_metadata(
                        "subscribe_mapping", raise_exception=False
                    )
                    if subscribe_dest is not None:
                        full_dest = (
                            prefix + subscribe_dest if prefix else subscribe_dest
                        )

                        self._subscribe_handlers.append(
                            SubscribeHandlerInfo(
                                destination_pattern=full_dest,
                                handler_container=handler_container,
                            )
                        )

                    # @MessageExceptionHandler
                    exc_type = handler_container.get_metadata(
                        "message_exception", raise_exception=False
                    )
                    if exc_type is not None:
                        self._exception_handlers[exc_type] = handler_container

    async def handle_session(self, session: WebSocketSession) -> None:
        """
        WebSocket 세션 처리 루프

        연결 수락 후 STOMP 프레임을 계속 수신하여 처리.
        """
        self._session_manager.add(session)

        try:
            # STOMP 연결 대기 (첫 CONNECT 프레임)
            await self._wait_for_connect(session)

            # 메시지 루프
            while session.is_connected:
                try:
                    text = await session.receive_text()
                    if not text:
                        continue

                    frame = StompFrame.parse(text)
                    await self._handle_frame(session, frame)

                except WebSocketDisconnect:
                    break
                except Exception as e:
                    await self._send_error(session, str(e))

        finally:
            # 정리
            await self._broker.disconnect(session.id)
            self._session_manager.remove(session.id)

    async def _wait_for_connect(self, session: WebSocketSession) -> None:
        """CONNECT 프레임 대기 및 처리"""
        # WebSocket 연결 수락 (STOMP 서브프로토콜)
        await session.accept(subprotocol="stomp")

        # CONNECT 프레임 대기
        text = await session.receive_text()
        frame = StompFrame.parse(text)

        if frame.command not in (StompCommand.CONNECT, StompCommand.STOMP):
            raise ValueError(f"Expected CONNECT, got {frame.command}")

        # 인증 처리 (선택적)
        # TODO: 인증 미들웨어와 통합

        # CONNECTED 응답
        connected_frame = StompFrame(
            command=StompCommand.CONNECTED,
            headers={
                "version": "1.2",
                "server": "bloom-stomp/1.0",
                "heart-beat": "0,0",
            },
        )
        await session.send_frame(connected_frame)

    async def _handle_frame(self, session: WebSocketSession, frame: StompFrame) -> None:
        """STOMP 프레임 처리"""
        match frame.command:
            case StompCommand.SUBSCRIBE:
                await self._handle_subscribe(session, frame)

            case StompCommand.UNSUBSCRIBE:
                await self._handle_unsubscribe(session, frame)

            case StompCommand.SEND:
                await self._handle_send(session, frame)

            case StompCommand.DISCONNECT:
                await self._handle_disconnect(session, frame)

            case StompCommand.ACK | StompCommand.NACK:
                # ACK/NACK은 현재 무시 (auto-ack 모드)
                pass

            case _:
                await self._send_error(
                    session, f"Unsupported command: {frame.command.value}"
                )

    async def _handle_subscribe(
        self, session: WebSocketSession, frame: StompFrame
    ) -> None:
        """SUBSCRIBE 프레임 처리"""
        subscription_id = frame.headers.get("id", "")
        destination = frame.headers.get("destination", "")

        if not subscription_id or not destination:
            await self._send_error(session, "SUBSCRIBE requires 'id' and 'destination'")
            return

        # 구독 등록
        async def send_callback(message: Message) -> None:
            """메시지를 클라이언트에게 전송"""
            out_frame = message.to_stomp_frame()
            out_frame.headers["message-id"] = f"msg-{session.id}-{id(message)}"
            await session.send_frame(out_frame)

        await self._broker.subscribe(
            subscription_id=subscription_id,
            destination=destination,
            session_id=session.id,
            send_callback=send_callback,
            user=session.user,
        )

        # @SubscribeMapping 핸들러 호출
        for handler_info in self._subscribe_handlers:
            path_params = self._match_destination(
                handler_info.destination_pattern, destination
            )
            if path_params is not None:
                try:
                    result = await self._invoke_handler(
                        handler_info.handler_container,
                        session,
                        None,
                        path_params,
                    )
                    if result is not None:
                        # 결과를 구독자에게 전송
                        message = Message(
                            destination=destination,
                            payload=result,
                            subscription_id=subscription_id,
                        )
                        await send_callback(message)
                except Exception as e:
                    await self._handle_exception(session, e)
                break

        # RECEIPT 전송 (요청된 경우)
        if "receipt" in frame.headers:
            receipt_frame = StompFrame(
                command=StompCommand.RECEIPT,
                headers={"receipt-id": frame.headers["receipt"]},
            )
            await session.send_frame(receipt_frame)

    async def _handle_unsubscribe(
        self, session: WebSocketSession, frame: StompFrame
    ) -> None:
        """UNSUBSCRIBE 프레임 처리"""
        subscription_id = frame.headers.get("id", "")

        if not subscription_id:
            await self._send_error(session, "UNSUBSCRIBE requires 'id'")
            return

        await self._broker.unsubscribe(subscription_id, session.id)

    async def _handle_send(self, session: WebSocketSession, frame: StompFrame) -> None:
        """SEND 프레임 처리"""
        destination = frame.headers.get("destination", "")

        if not destination:
            await self._send_error(session, "SEND requires 'destination'")
            return

        # Message 생성
        message = Message.from_stomp_frame(frame, session.id, session.user)

        # /app/ 프리픽스 처리 (애플리케이션 핸들러로 라우팅)
        if destination.startswith(self.APP_DESTINATION_PREFIX):
            # /app/chat.send → /chat.send
            handler_dest = destination[len(self.APP_DESTINATION_PREFIX) :]
            await self._route_to_handler(session, handler_dest, message)
        else:
            # 직접 브로커로 발행
            await self._broker.publish(message)

    async def _handle_disconnect(
        self, session: WebSocketSession, frame: StompFrame
    ) -> None:
        """DISCONNECT 프레임 처리"""
        # RECEIPT 전송 (요청된 경우)
        if "receipt" in frame.headers:
            receipt_frame = StompFrame(
                command=StompCommand.RECEIPT,
                headers={"receipt-id": frame.headers["receipt"]},
            )
            await session.send_frame(receipt_frame)

        # 연결 종료
        await session.close()

    async def _route_to_handler(
        self,
        session: WebSocketSession,
        destination: str,
        message: Message,
    ) -> None:
        """메시지를 적절한 @MessageMapping 핸들러로 라우팅"""
        for handler_info in self._message_handlers:
            path_params = self._match_destination(
                handler_info.destination_pattern, destination
            )
            if path_params is not None:
                try:
                    result = await self._invoke_handler(
                        handler_info.handler_container,
                        session,
                        message,
                        path_params,
                    )

                    # 결과 발행
                    if result is not None:
                        await self._publish_result(
                            session, message, result, handler_info
                        )

                except Exception as e:
                    await self._handle_exception(session, e)

                return

        # 핸들러를 찾지 못함
        await self._send_error(session, f"No handler for destination: {destination}")

    async def _invoke_handler(
        self,
        handler_container: HandlerContainer,
        session: WebSocketSession,
        message: Message | None,
        path_params: dict[str, str],
    ) -> Any:
        """핸들러 메서드 호출"""
        if not self._container_manager:
            raise RuntimeError("ContainerManager not set")

        # owner 인스턴스 가져오기
        handler_container.manager = self._container_manager
        bound_method = handler_container.invoke

        # 파라미터 추론 및 바인딩
        type_hints = handler_container.get_type_hints()
        sig = inspect.signature(handler_container.handler_method)
        kwargs: dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_type = type_hints.get(param_name)

            # Message 타입
            if param_type == Message or (message and param_name == "message"):
                kwargs[param_name] = message

            # path parameter
            elif param_name in path_params:
                kwargs[param_name] = path_params[param_name]

            # 페이로드 (첫 번째 비-특수 파라미터)
            elif message and message.payload is not None:
                # Pydantic 모델이나 dataclass로 변환 시도
                if hasattr(param_type, "model_validate"):
                    kwargs[param_name] = param_type.model_validate(message.payload)
                elif hasattr(param_type, "__dataclass_fields__"):
                    kwargs[param_name] = param_type(**message.payload)
                else:
                    kwargs[param_name] = message.payload

        # 핸들러 호출
        result = bound_method(**kwargs)

        # 비동기 처리
        if asyncio.iscoroutine(result):
            result = await result

        return result

    async def _publish_result(
        self,
        session: WebSocketSession,
        original_message: Message,
        result: Any,
        handler_info: MessageHandlerInfo,
    ) -> None:
        """핸들러 결과를 발행"""
        if handler_info.send_to:
            # @SendTo: 지정된 목적지로 브로드캐스트
            destination = self._resolve_destination(
                handler_info.send_to, result, original_message
            )
            message = Message(destination=destination, payload=result)
            await self._broker.publish(message)

        elif handler_info.send_to_user:
            # @SendToUser: 발신자에게만 전송
            destination = handler_info.send_to_user
            message = Message(destination=destination, payload=result)
            if session.user:
                await self._broker.send_to_user(session.user, destination, message)

    def _resolve_destination(
        self,
        pattern: str,
        result: Any,
        original_message: Message,
    ) -> str:
        """
        동적 목적지 패턴 해석

        예: "/topic/chat.{room_id}" → "/topic/chat.room1"
        """
        # {xxx} 패턴 찾기
        placeholders = re.findall(r"\{(\w+)\}", pattern)
        destination = pattern

        for placeholder in placeholders:
            value = None

            # result에서 찾기
            if hasattr(result, placeholder):
                value = getattr(result, placeholder)
            elif isinstance(result, dict) and placeholder in result:
                value = result[placeholder]

            # original_message payload에서 찾기
            elif original_message.payload:
                payload = original_message.payload
                if hasattr(payload, placeholder):
                    value = getattr(payload, placeholder)
                elif isinstance(payload, dict) and placeholder in payload:
                    value = payload[placeholder]

            if value is not None:
                destination = destination.replace(f"{{{placeholder}}}", str(value))

        return destination

    def _match_destination(
        self, pattern: str, destination: str
    ) -> dict[str, str] | None:
        """
        목적지 패턴 매칭

        Args:
            pattern: 패턴 (예: "/chat.{room_id}")
            destination: 실제 목적지 (예: "/chat.room1")

        Returns:
            매칭 시 path params dict, 미매칭 시 None
        """
        # {xxx} → (?P<xxx>[^./]+)
        regex_pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^./]+)", pattern)
        regex_pattern = f"^{regex_pattern}$"

        match = re.match(regex_pattern, destination)
        if match:
            return match.groupdict()
        return None

    async def _handle_exception(
        self, session: WebSocketSession, error: Exception
    ) -> None:
        """예외 처리"""
        # @MessageExceptionHandler 찾기
        for exc_type, handler in self._exception_handlers.items():
            if isinstance(error, exc_type):
                try:
                    result = await self._invoke_handler(handler, session, None, {})
                    if result is not None:
                        # 에러 응답 전송
                        message = Message(
                            destination="/user/queue/errors",
                            payload=result,
                        )
                        if session.user:
                            await self._broker.send_to_user(
                                session.user, "/queue/errors", message
                            )
                    return
                except Exception:
                    pass

        # 기본 에러 처리
        await self._send_error(session, str(error))

    async def _send_error(self, session: WebSocketSession, message: str) -> None:
        """ERROR 프레임 전송"""
        error_frame = StompFrame(
            command=StompCommand.ERROR,
            headers={"message": message},
            body=message,
        )
        await session.send_frame(error_frame)
