"""@Controller에서 메시징 데코레이터 사용 테스트"""

import pytest

from bloom import Application, Controller
from bloom.web import RequestMapping
from bloom.web.messaging import (
    MessageMapping,
    SendTo,
    SendToUser,
    SubscribeMapping,
    MessageExceptionHandler,
    StompProtocolHandler,
    SimpleBroker,
    WebSocketSessionManager,
)


class TestControllerWithMessaging:
    """@Controller에서 @MessageMapping, @SendTo 등 사용 테스트"""

    @pytest.mark.asyncio
    async def test_controller_with_message_mapping(self):
        """@Controller에서 @MessageMapping 사용 가능"""

        @Controller
        class ApiController:
            @MessageMapping("/api/echo")
            @SendTo("/topic/echo")
            def echo(self, msg: dict) -> dict:
                return {"echo": msg}

        app = Application("test").scan(__name__).ready()
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)
        handler.collect_handlers(app.manager)

        # MessageMapping 핸들러가 수집되었는지 확인
        echo_handler = next(
            (
                h
                for h in handler._message_handlers
                if h.destination_pattern == "/api/echo"
            ),
            None,
        )
        assert echo_handler is not None
        assert echo_handler.send_to == "/topic/echo"

    @pytest.mark.asyncio
    async def test_controller_request_mapping_does_not_affect_stomp_path(self):
        """
        @Controller의 @RequestMapping path는 STOMP path에 영향을 주지 않음

        HTTP path와 WebSocket STOMP path는 별개의 라우팅 체계
        """

        @Controller
        @RequestMapping("/api/v1")  # HTTP path prefix
        class ApiV1Controller:
            @MessageMapping("/chat.send")  # STOMP path (prefix 영향 없음)
            @SendTo("/topic/messages")
            def send_message(self, msg: dict) -> dict:
                return msg

        app = Application("test").scan(__name__).ready()
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)
        handler.collect_handlers(app.manager)

        # STOMP path는 @RequestMapping의 영향을 받지 않음
        chat_handler = next(
            (
                h
                for h in handler._message_handlers
                if h.destination_pattern == "/chat.send"
            ),
            None,
        )
        assert chat_handler is not None
        # /api/v1/chat.send가 아니라 /chat.send여야 함
        assert chat_handler.destination_pattern == "/chat.send"

    @pytest.mark.asyncio
    async def test_controller_with_all_messaging_decorators(self):
        """@Controller에서 모든 메시징 데코레이터 사용 가능"""

        @Controller
        @RequestMapping("/api")  # HTTP path (STOMP와 무관)
        class NotificationController:
            @MessageMapping("/notify")
            @SendToUser("/queue/notifications")
            def send_notification(self, msg: dict) -> dict:
                return {"notification": msg}

            @SubscribeMapping("/topic/updates")
            def on_subscribe(self) -> dict:
                return {"message": "Subscribed to updates"}

            @MessageExceptionHandler(ValueError)
            def handle_error(self, error: ValueError) -> dict:
                return {"error": str(error)}

        app = Application("test").scan(__name__).ready()
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)
        handler.collect_handlers(app.manager)

        # SendToUser 핸들러 확인
        notify_handler = next(
            (
                h
                for h in handler._message_handlers
                if h.destination_pattern == "/notify"
            ),
            None,
        )
        assert notify_handler is not None
        assert notify_handler.send_to_user == "/queue/notifications"

        # SubscribeMapping 핸들러 확인
        subscribe_handler = next(
            (
                h
                for h in handler._subscribe_handlers
                if h.destination_pattern == "/topic/updates"
            ),
            None,
        )
        assert subscribe_handler is not None

        # ExceptionHandler 확인
        assert ValueError in handler._exception_handlers

    @pytest.mark.asyncio
    async def test_message_controller_still_uses_prefix(self):
        """
        @MessageController는 여전히 prefix를 사용함

        @Controller와 달리 @MessageController의 prefix는 STOMP path에 적용됨
        """
        from bloom.web.messaging import MessageController

        @MessageController("/app")  # STOMP prefix
        class ChatController:
            @MessageMapping("/chat.send")  # 실제: /app/chat.send
            def send_message(self, msg: dict) -> dict:
                return msg

        app = Application("test").scan(__name__).ready()
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)
        handler.collect_handlers(app.manager)

        # @MessageController의 prefix는 적용됨
        chat_handler = next(
            (
                h
                for h in handler._message_handlers
                if h.destination_pattern == "/app/chat.send"
            ),
            None,
        )
        assert chat_handler is not None
        assert chat_handler.destination_pattern == "/app/chat.send"

    @pytest.mark.asyncio
    async def test_mixed_controller_and_message_controller(self):
        """@Controller와 @MessageController 혼용 시나리오"""

        @Controller
        @RequestMapping("/api/v1")  # HTTP path
        class RestApiController:
            @MessageMapping("/api.echo")  # STOMP path (HTTP prefix 무관)
            @SendTo("/topic/echo")
            def echo(self, msg: dict) -> dict:
                return msg

        from bloom.web.messaging import MessageController

        @MessageController("/app")  # STOMP prefix
        class ChatController:
            @MessageMapping("/chat.send")  # 실제: /app/chat.send
            @SendTo("/topic/messages")
            def send_message(self, msg: dict) -> dict:
                return msg

        app = Application("test").scan(__name__).ready()
        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)
        handler.collect_handlers(app.manager)

        # @Controller의 메시징 핸들러 (prefix 없음)
        echo_handler = next(
            (
                h
                for h in handler._message_handlers
                if h.destination_pattern == "/api.echo"
            ),
            None,
        )
        assert echo_handler is not None

        # @MessageController의 메시징 핸들러 (prefix 적용)
        chat_handler = next(
            (
                h
                for h in handler._message_handlers
                if h.destination_pattern == "/app/chat.send"
            ),
            None,
        )
        assert chat_handler is not None
