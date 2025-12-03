"""STOMP 메시지 핸들러

메시지 라우팅, 파라미터 리졸빙, 핸들러 실행을 담당합니다.
HTTP ParameterResolver와 동일한 패턴을 사용합니다.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar, get_origin, get_args, TYPE_CHECKING

from .stomp import StompFrame, StompCommand, StompProtocol, StompError
from .websocket import WebSocketSession
from .broker import MessageBroker, SimpleBroker, Message
from .decorators import (
    MessageMappingInfo,
    SubscribeMappingInfo,
    SendToInfo,
    MessageControllerInfo,
    get_message_controller_info,
    get_send_to_info,
    _match_destination,
)
from .params import (
    DestinationVariableMarker,
    MessagePayloadMarker,
    MessageHeadersMarker,
    PrincipalMarker,
    SessionIdMarker,
    WebSocketSessionMarker,
    get_message_param_marker,
    get_message_param_type,
)

if TYPE_CHECKING:
    from bloom.core import ContainerManager


T = TypeVar("T")


# =============================================================================
# Message Context (HTTP의 Request 역할)
# =============================================================================


@dataclass
class MessageContext:
    """메시지 컨텍스트

    HTTP의 Request와 동일한 역할을 하며, 메시지 처리에 필요한 모든 정보를 담습니다.
    """

    session: WebSocketSession
    frame: StompFrame
    destination: str
    destination_variables: dict[str, str] = field(default_factory=dict)
    principal: Any = None  # 인증된 사용자 정보

    @property
    def headers(self) -> dict[str, str]:
        """STOMP 헤더"""
        return self.frame.headers

    @property
    def body(self) -> str:
        """메시지 본문"""
        return self.frame.body

    @property
    def session_id(self) -> str:
        """WebSocket 세션 ID"""
        return self.session.session_id

    def body_as_json(self) -> Any:
        """본문을 JSON으로 파싱"""
        if not self.body:
            return {}
        return json.loads(self.body)


# =============================================================================
# Parameter Info (HTTP 버전과 유사)
# =============================================================================


@dataclass
class MessageParameterInfo:
    """메시지 핸들러 파라미터 정보"""

    name: str
    annotation: Any
    actual_type: Any
    marker: Any | None
    default: Any
    has_default: bool
    is_optional: bool

    @classmethod
    def from_parameter(cls, param: inspect.Parameter) -> "MessageParameterInfo":
        """inspect.Parameter에서 생성"""
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            annotation = Any

        # Annotated[T, Marker] 형태에서 마커와 실제 타입 추출
        marker = get_message_param_marker(annotation)
        actual_type = get_message_param_type(annotation) or Any

        # Optional[T] 처리
        is_opt = False
        origin = get_origin(actual_type)
        if origin is type(None):
            is_opt = True
        # Python 3.10+ Union handling
        import sys

        if sys.version_info >= (3, 10):
            import types

            if origin is types.UnionType:
                args = get_args(actual_type)
                if type(None) in args:
                    is_opt = True
                    actual_type = [a for a in args if a is not type(None)][0]

        has_default = param.default is not inspect.Parameter.empty
        default = param.default if has_default else None

        return cls(
            name=param.name,
            annotation=annotation,
            actual_type=actual_type,
            marker=marker,
            default=default,
            has_default=has_default,
            is_optional=is_opt,
        )


# =============================================================================
# Message Parameter Resolver Interface
# =============================================================================


class MessageParameterResolver(ABC, Generic[T]):
    """메시지 파라미터 리졸버 인터페이스

    HTTP ParameterResolver와 동일한 패턴으로 메시지 파라미터를 추출합니다.
    """

    @abstractmethod
    def supports(self, param: MessageParameterInfo) -> bool:
        """이 리졸버가 해당 파라미터를 처리할 수 있는지 확인"""
        pass

    @abstractmethod
    async def resolve(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> T:
        """파라미터 값을 추출"""
        pass


# =============================================================================
# Built-in Message Resolvers
# =============================================================================


class WebSocketSessionResolver(MessageParameterResolver[WebSocketSession]):
    """WebSocketSession 객체 자체를 주입"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return (
            param.actual_type is WebSocketSession
            or param.name == "session"
            or isinstance(param.marker, WebSocketSessionMarker)
        )

    async def resolve(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> WebSocketSession:
        return context.session


class MessageContextResolver(MessageParameterResolver[MessageContext]):
    """MessageContext 객체 자체를 주입"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return param.actual_type is MessageContext or param.name == "context"

    async def resolve(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> MessageContext:
        return context


class DestinationVariableResolver(MessageParameterResolver[Any]):
    """destination 경로 변수 리졸버

    /chat/{room} 에서 room 값을 추출합니다.
    """

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, DestinationVariableMarker)

    async def resolve(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> Any:
        # 마커에 name이 있으면 그 이름 사용, 없으면 파라미터 이름
        name = param.name
        if isinstance(param.marker, DestinationVariableMarker) and param.marker.name:
            name = param.marker.name

        value = context.destination_variables.get(name)
        if value is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError(f"Destination variable '{name}' not found")

        return self._convert_type(value, param.actual_type)

    def _convert_type(self, value: str, target_type: type) -> Any:
        """문자열을 타겟 타입으로 변환"""
        if target_type is str or target_type is Any:
            return value
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        if target_type is bool:
            return value.lower() in ("true", "1", "yes")
        return value


class MessagePayloadResolver(MessageParameterResolver[Any]):
    """메시지 본문 리졸버

    STOMP 메시지의 body를 파싱하여 주입합니다.
    """

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, MessagePayloadMarker)

    async def resolve(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> Any:
        body = context.body
        if not body:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            return None

        # JSON 파싱
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = body

        # 타입 변환
        target_type = param.actual_type
        if target_type is str:
            return body
        if target_type is dict or target_type is Any:
            return data
        if isinstance(data, dict) and hasattr(target_type, "__dataclass_fields__"):
            # dataclass 변환
            return target_type(**data)
        if isinstance(data, dict) and hasattr(target_type, "model_validate"):
            # Pydantic 모델 변환
            return target_type.model_validate(data)

        return data


class MessageHeadersResolver(MessageParameterResolver[Any]):
    """메시지 헤더 리졸버"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, MessageHeadersMarker)

    async def resolve(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> Any:
        marker = param.marker
        if isinstance(marker, MessageHeadersMarker) and marker.name:
            # 특정 헤더
            value = context.headers.get(marker.name)
            if value is None:
                if param.has_default:
                    return param.default
                if param.is_optional:
                    return None
            return value
        else:
            # 전체 헤더
            return context.headers


class PrincipalResolver(MessageParameterResolver[Any]):
    """인증된 사용자 정보 리졸버"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, PrincipalMarker)

    async def resolve(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> Any:
        if context.principal is None:
            if param.has_default:
                return param.default
            if param.is_optional:
                return None
            raise ValueError("Principal not available")
        return context.principal


class SessionIdResolver(MessageParameterResolver[str]):
    """세션 ID 리졸버"""

    def supports(self, param: MessageParameterInfo) -> bool:
        return isinstance(param.marker, SessionIdMarker) or param.name == "session_id"

    async def resolve(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> str:
        return context.session_id


class ImplicitDestinationVariableResolver(MessageParameterResolver[Any]):
    """암시적 destination 변수 리졸버

    마커 없이 파라미터 이름이 destination 변수와 일치하면 추출합니다.
    """

    def supports(self, param: MessageParameterInfo) -> bool:
        # 다른 마커가 없고, 기본 타입인 경우
        return (
            param.marker is None
            and param.actual_type in (str, int, float, bool, Any)
            and param.name not in ("self", "cls")
        )

    async def resolve(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> Any:
        # destination 변수에서 찾기
        if param.name in context.destination_variables:
            value = context.destination_variables[param.name]
            return self._convert_type(value, param.actual_type)

        # 기본값
        if param.has_default:
            return param.default
        if param.is_optional:
            return None

        raise ValueError(f"Could not resolve parameter '{param.name}'")

    def _convert_type(self, value: str, target_type: type) -> Any:
        if target_type is str or target_type is Any:
            return value
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
        if target_type is bool:
            return value.lower() in ("true", "1", "yes")
        return value


# =============================================================================
# Message Dispatcher
# =============================================================================


class MessageDispatcher:
    """메시지 디스패처

    @MessageMapping 핸들러를 등록하고, 메시지를 적절한 핸들러로 라우팅합니다.
    """

    def __init__(
        self,
        broker: MessageBroker | None = None,
        container_manager: "ContainerManager | None" = None,
    ):
        self.broker = broker or SimpleBroker()
        self.container_manager = container_manager

        # 핸들러 등록
        self._message_mappings: list[
            tuple[MessageMappingInfo, type, Callable[..., Any]]
        ] = []
        self._subscribe_mappings: list[
            tuple[SubscribeMappingInfo, type, Callable[..., Any]]
        ] = []

        # 리졸버 등록 (순서 중요: 구체적인 것 먼저)
        self._resolvers: list[MessageParameterResolver[Any]] = [
            WebSocketSessionResolver(),
            MessageContextResolver(),
            DestinationVariableResolver(),
            MessagePayloadResolver(),
            MessageHeadersResolver(),
            PrincipalResolver(),
            SessionIdResolver(),
            ImplicitDestinationVariableResolver(),  # 가장 마지막 (폴백)
        ]

    def add_resolver(self, resolver: MessageParameterResolver[Any]) -> None:
        """커스텀 리졸버 추가 (우선순위 높음)"""
        self._resolvers.insert(0, resolver)

    def register_controller(self, controller_cls: type) -> None:
        """메시지 컨트롤러 등록"""
        info = get_message_controller_info(controller_cls)
        if not info:
            raise ValueError(f"{controller_cls.__name__} is not a @MessageController")

        for mapping in info.message_mappings:
            if mapping.method:
                self._message_mappings.append((mapping, controller_cls, mapping.method))

        for mapping in info.subscribe_mappings:
            if mapping.method:
                self._subscribe_mappings.append(
                    (mapping, controller_cls, mapping.method)
                )

    async def dispatch_message(self, context: MessageContext) -> Any:
        """SEND 메시지 디스패치"""
        destination = context.destination

        for mapping, controller_cls, method in self._message_mappings:
            match_vars = _match_destination(
                mapping.pattern, mapping.variables, destination
            )
            if match_vars is not None:
                context.destination_variables = match_vars
                return await self._invoke_handler(controller_cls, method, context)

        raise StompError(f"No handler for destination: {destination}")

    async def dispatch_subscribe(self, context: MessageContext) -> Any:
        """SUBSCRIBE 핸들러 디스패치 (초기 데이터 전송)"""
        destination = context.destination

        for mapping, controller_cls, method in self._subscribe_mappings:
            match_vars = _match_destination(
                mapping.pattern, mapping.variables, destination
            )
            if match_vars is not None:
                context.destination_variables = match_vars
                return await self._invoke_handler(controller_cls, method, context)

        return None  # 핸들러 없으면 무시

    async def _invoke_handler(
        self,
        controller_cls: type,
        method: Callable[..., Any],
        context: MessageContext,
    ) -> Any:
        """핸들러 실행"""
        # 컨트롤러 인스턴스 획득
        if self.container_manager:
            controller = await self.container_manager.get_instance_async(controller_cls)
        else:
            controller = controller_cls()

        if not controller:
            raise StompError(
                f"Could not get controller instance: {controller_cls.__name__}"
            )

        # 파라미터 리졸빙
        sig = inspect.signature(method)
        kwargs: dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_info = MessageParameterInfo.from_parameter(param)
            value = await self._resolve_parameter(param_info, context)
            kwargs[param_name] = value

        # 핸들러 실행
        bound_method = getattr(controller, method.__name__)
        result = bound_method(**kwargs)

        if asyncio.iscoroutine(result):
            result = await result

        return result

    async def _resolve_parameter(
        self,
        param: MessageParameterInfo,
        context: MessageContext,
    ) -> Any:
        """파라미터 리졸빙"""
        for resolver in self._resolvers:
            if resolver.supports(param):
                return await resolver.resolve(param, context)

        # 기본값 반환
        if param.has_default:
            return param.default
        if param.is_optional:
            return None

        raise ValueError(f"No resolver found for parameter: {param.name}")

    async def handle_send_to(
        self,
        context: MessageContext,
        method: Callable[..., Any],
        result: Any,
    ) -> None:
        """@SendTo 처리"""
        send_to_list = get_send_to_info(method)

        for send_to in send_to_list:
            for dest_pattern in send_to.destinations:
                # destination 변수 치환
                destination = dest_pattern
                for var_name, var_value in context.destination_variables.items():
                    destination = destination.replace(f"{{{var_name}}}", var_value)

                if send_to.broadcast:
                    # 모든 구독자에게
                    await self.broker.publish(destination, result)
                else:
                    # 요청자에게만
                    await self.broker.send_to_session(
                        context.session_id, destination, result
                    )


# =============================================================================
# STOMP Message Handler (ASGI WebSocket Handler)
# =============================================================================


class StompMessageHandler:
    """STOMP 메시지 핸들러

    WebSocket 연결을 처리하고 STOMP 프로토콜을 해석합니다.

    Examples:
        handler = StompMessageHandler(dispatcher, broker)

        # ASGI 앱으로 사용
        async def websocket_app(scope, receive, send):
            await handler(scope, receive, send)
    """

    def __init__(
        self,
        dispatcher: MessageDispatcher,
        broker: MessageBroker | None = None,
        server_name: str = "bloom-stomp/1.0",
    ):
        self.dispatcher = dispatcher
        self.broker = broker or dispatcher.broker
        self.server_name = server_name
        self._protocol = StompProtocol()

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Any],
        send: Callable[[dict[str, Any]], Any],
    ) -> None:
        """ASGI WebSocket 핸들러"""
        session = WebSocketSession(
            scope=scope,
            receive=receive,
            send=send,
            session_id=str(uuid.uuid4()),
        )

        await session.accept(subprotocol="stomp")
        await self.broker.register_session(session)

        try:
            await self._handle_session(session)
        finally:
            await self.broker.unsubscribe_all(session.session_id)
            await self.broker.unregister_session(session.session_id)

    async def _handle_session(self, session: WebSocketSession) -> None:
        """세션 처리 루프"""
        protocol = StompProtocol()
        connected = False

        async for data in session:
            try:
                frame = protocol.parse(data)
                if frame is None:
                    continue

                # CONNECT/STOMP 먼저 처리
                if frame.command in (StompCommand.CONNECT, StompCommand.STOMP):
                    await self._handle_connect(session, frame)
                    connected = True
                    continue

                if not connected:
                    error_frame = StompProtocol.create_error(
                        "Not connected",
                        "Please send CONNECT frame first",
                    )
                    await session.send_text(error_frame.serialize())
                    continue

                # 명령 처리
                await self._handle_frame(session, frame)

            except StompError as e:
                error_frame = StompProtocol.create_error(e.message, e.details)
                await session.send_text(error_frame.serialize())
            except Exception as e:
                error_frame = StompProtocol.create_error(
                    "Internal error",
                    str(e),
                )
                await session.send_text(error_frame.serialize())

    async def _handle_connect(
        self,
        session: WebSocketSession,
        frame: StompFrame,
    ) -> None:
        """CONNECT 처리"""
        # 버전 협상
        accept_version = frame.headers.get("accept-version", "1.0")
        versions = accept_version.split(",")
        selected_version = "1.2" if "1.2" in versions else versions[0]

        # CONNECTED 응답
        connected_frame = StompProtocol.create_connected(
            version=selected_version,
            session=session.session_id,
            server=self.server_name,
        )
        await session.send_text(connected_frame.serialize())

    async def _handle_frame(
        self,
        session: WebSocketSession,
        frame: StompFrame,
    ) -> None:
        """프레임 처리"""
        if frame.command == StompCommand.SEND:
            await self._handle_send(session, frame)

        elif frame.command == StompCommand.SUBSCRIBE:
            await self._handle_subscribe(session, frame)

        elif frame.command == StompCommand.UNSUBSCRIBE:
            await self._handle_unsubscribe(session, frame)

        elif frame.command == StompCommand.DISCONNECT:
            await self._handle_disconnect(session, frame)

        elif frame.command == StompCommand.ACK:
            pass  # ACK 처리 (구현 시 추가)

        elif frame.command == StompCommand.NACK:
            pass  # NACK 처리 (구현 시 추가)

        else:
            raise StompError(f"Unsupported command: {frame.command.value}")

    async def _handle_send(
        self,
        session: WebSocketSession,
        frame: StompFrame,
    ) -> None:
        """SEND 명령 처리"""
        destination = frame.destination
        if not destination:
            raise StompError("Missing destination header")

        # 컨텍스트 생성
        context = MessageContext(
            session=session,
            frame=frame,
            destination=destination,
            principal=session.user_id,
        )

        # 핸들러 디스패치
        result = await self.dispatcher.dispatch_message(context)

        # @SendTo 처리
        for mapping, _, method in self.dispatcher._message_mappings:
            match_vars = _match_destination(
                mapping.pattern, mapping.variables, destination
            )
            if match_vars is not None:
                context.destination_variables = match_vars
                await self.dispatcher.handle_send_to(context, method, result)
                break

        # receipt 처리
        receipt_id = frame.headers.get("receipt")
        if receipt_id:
            receipt_frame = StompProtocol.create_receipt(receipt_id)
            await session.send_text(receipt_frame.serialize())

    async def _handle_subscribe(
        self,
        session: WebSocketSession,
        frame: StompFrame,
    ) -> None:
        """SUBSCRIBE 명령 처리"""
        destination = frame.destination
        subscription_id = frame.id

        if not destination:
            raise StompError("Missing destination header")
        if not subscription_id:
            raise StompError("Missing id header")

        # 구독 등록
        ack_mode = frame.headers.get("ack", "auto")
        await self.broker.subscribe(destination, subscription_id, session, ack_mode)

        # @SubscribeMapping 핸들러 호출 (초기 데이터)
        context = MessageContext(
            session=session,
            frame=frame,
            destination=destination,
            principal=session.user_id,
        )

        initial_data = await self.dispatcher.dispatch_subscribe(context)

        if initial_data is not None:
            # 초기 데이터 전송
            body = (
                json.dumps(initial_data, ensure_ascii=False, default=str)
                if not isinstance(initial_data, str)
                else initial_data
            )
            message_frame = StompProtocol.create_message(
                destination=destination,
                body=body,
                message_id=str(uuid.uuid4()),
                subscription=subscription_id,
            )
            await session.send_text(message_frame.serialize())

        # receipt 처리
        receipt_id = frame.headers.get("receipt")
        if receipt_id:
            receipt_frame = StompProtocol.create_receipt(receipt_id)
            await session.send_text(receipt_frame.serialize())

    async def _handle_unsubscribe(
        self,
        session: WebSocketSession,
        frame: StompFrame,
    ) -> None:
        """UNSUBSCRIBE 명령 처리"""
        subscription_id = frame.id
        if not subscription_id:
            raise StompError("Missing id header")

        await self.broker.unsubscribe(subscription_id, session.session_id)

        # receipt 처리
        receipt_id = frame.headers.get("receipt")
        if receipt_id:
            receipt_frame = StompProtocol.create_receipt(receipt_id)
            await session.send_text(receipt_frame.serialize())

    async def _handle_disconnect(
        self,
        session: WebSocketSession,
        frame: StompFrame,
    ) -> None:
        """DISCONNECT 명령 처리"""
        # receipt 처리
        receipt_id = frame.headers.get("receipt")
        if receipt_id:
            receipt_frame = StompProtocol.create_receipt(receipt_id)
            await session.send_text(receipt_frame.serialize())

        # 연결 종료
        await session.close()
