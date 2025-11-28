"""WebSocket 설정 레지스트리 테스트"""

import pytest
from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.web.messaging import (
    StompEndpointRegistry,
    StompEndpoint,
    MessageBrokerRegistry,
    MessageBrokerConfig,
    EnableWebSocket,
    is_websocket_enabled,
    WebSocketManager,
)


class TestStompEndpointRegistry:
    """StompEndpointRegistry 테스트"""

    def test_add_endpoint(self):
        """엔드포인트 추가 테스트"""
        registry = StompEndpointRegistry()

        endpoint = registry.add_endpoint("/ws")
        assert endpoint.path == "/ws"
        assert endpoint.allowed_origins == ["*"]
        assert endpoint.sockjs_enabled is False

    def test_endpoint_chaining(self):
        """엔드포인트 체이닝 테스트"""
        registry = StompEndpointRegistry()

        endpoint = (
            registry.add_endpoint("/ws")
            .set_allowed_origins("https://a.com", "https://b.com")
            .with_sockjs()
            .set_heartbeat(5000, 5000)
        )

        assert endpoint.path == "/ws"
        assert endpoint.allowed_origins == ["https://a.com", "https://b.com"]
        assert endpoint.sockjs_enabled is True
        assert endpoint.heartbeat_send == 5000
        assert endpoint.heartbeat_receive == 5000

    def test_multiple_endpoints(self):
        """다중 엔드포인트 테스트"""
        registry = StompEndpointRegistry()

        registry.add_endpoint("/ws").set_allowed_origins("*")
        registry.add_endpoint("/ws-sockjs").with_sockjs()

        endpoints = registry.endpoints
        assert len(endpoints) == 2
        assert endpoints[0].path == "/ws"
        assert endpoints[1].path == "/ws-sockjs"
        assert endpoints[1].sockjs_enabled is True


class TestMessageBrokerRegistry:
    """MessageBrokerRegistry 테스트"""

    def test_default_config(self):
        """기본 설정 테스트"""
        registry = MessageBrokerRegistry()
        config = registry.config

        assert config.simple_broker_destinations == []
        assert config.application_destination_prefixes == ["/app"]
        assert config.user_destination_prefix == "/user"

    def test_enable_simple_broker(self):
        """Simple Broker 활성화 테스트"""
        registry = MessageBrokerRegistry()

        registry.enable_simple_broker("/topic", "/queue")

        config = registry.config
        assert "/topic" in config.simple_broker_destinations
        assert "/queue" in config.simple_broker_destinations

    def test_chaining(self):
        """체이닝 테스트"""
        registry = MessageBrokerRegistry()

        registry.enable_simple_broker("/topic").set_application_destination_prefixes(
            "/app", "/api"
        ).set_user_destination_prefix("/private").set_cache_limit(2048)

        config = registry.config
        assert "/topic" in config.simple_broker_destinations
        assert "/app" in config.application_destination_prefixes
        assert "/api" in config.application_destination_prefixes
        assert config.user_destination_prefix == "/private"
        assert config.cache_limit == 2048


class TestFactoryRegistration:
    """@Factory를 통한 레지스트리 등록 테스트"""

    def test_factory_endpoint_registry(self, reset_container_manager):
        """@Factory로 StompEndpointRegistry 등록 테스트"""

        @Component
        class WebSocketConfig:
            @Factory
            def stomp_endpoint_registry(self) -> StompEndpointRegistry:
                registry = StompEndpointRegistry()
                registry.add_endpoint("/ws-custom").set_allowed_origins(
                    "https://example.com"
                )
                return registry

        app = Application("test").scan(__import__(__name__)).ready()

        # Factory로 등록된 레지스트리 가져오기
        registry = app.manager.get_instance(StompEndpointRegistry)
        assert registry is not None
        assert len(registry.endpoints) == 1
        assert registry.endpoints[0].path == "/ws-custom"
        assert registry.endpoints[0].allowed_origins == ["https://example.com"]

    def test_factory_broker_registry(self, reset_container_manager):
        """@Factory로 MessageBrokerRegistry 등록 테스트"""

        @Component
        class WebSocketConfig:
            @Factory
            def message_broker_registry(self) -> MessageBrokerRegistry:
                registry = MessageBrokerRegistry()
                registry.enable_simple_broker("/topic", "/queue", "/user")
                registry.set_application_destination_prefixes("/app", "/api")
                registry.set_user_destination_prefix("/private")
                return registry

        app = Application("test").scan(__import__(__name__)).ready()

        # Factory로 등록된 레지스트리 가져오기
        registry = app.manager.get_instance(MessageBrokerRegistry)
        assert registry is not None

        config = registry.config
        assert "/topic" in config.simple_broker_destinations
        assert "/user" in config.simple_broker_destinations
        assert "/app" in config.application_destination_prefixes
        assert "/api" in config.application_destination_prefixes
        assert config.user_destination_prefix == "/private"


class TestStompProtocolHandlerWithConfig:
    """StompProtocolHandler 설정 적용 테스트"""

    def test_apply_config(self, reset_container_manager):
        """설정 적용 테스트"""
        from bloom.web.messaging import (
            SimpleBroker,
            WebSocketSessionManager,
            StompProtocolHandler,
        )

        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        # 커스텀 설정
        broker_config = MessageBrokerConfig(
            simple_broker_destinations=["/topic", "/queue"],
            application_destination_prefixes=["/app", "/api"],
            user_destination_prefix="/private",
        )
        endpoints = [StompEndpoint(path="/ws-custom")]

        handler.apply_config(broker_config, endpoints)

        # 설정 적용 확인
        assert handler._app_destination_prefixes == ["/app", "/api"]
        assert handler._user_destination_prefix == "/private"
        assert handler._endpoints[0].path == "/ws-custom"

    def test_is_app_destination(self, reset_container_manager):
        """애플리케이션 목적지 확인 테스트"""
        from bloom.web.messaging import (
            SimpleBroker,
            WebSocketSessionManager,
            StompProtocolHandler,
        )

        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        # 기본 설정
        assert handler.is_app_destination("/app/chat") is True
        assert handler.is_app_destination("/topic/messages") is False

        # 커스텀 설정 적용
        broker_config = MessageBrokerConfig(
            application_destination_prefixes=["/app", "/api"]
        )
        handler.apply_config(broker_config, [])

        assert handler.is_app_destination("/app/chat") is True
        assert handler.is_app_destination("/api/users") is True
        assert handler.is_app_destination("/topic/messages") is False

    def test_strip_app_prefix(self, reset_container_manager):
        """애플리케이션 프리픽스 제거 테스트"""
        from bloom.web.messaging import (
            SimpleBroker,
            WebSocketSessionManager,
            StompProtocolHandler,
        )

        broker = SimpleBroker()
        session_manager = WebSocketSessionManager()
        handler = StompProtocolHandler(broker, session_manager)

        # 커스텀 설정 적용
        broker_config = MessageBrokerConfig(
            application_destination_prefixes=["/app", "/api"]
        )
        handler.apply_config(broker_config, [])

        assert handler.strip_app_prefix("/app/chat") == "/chat"
        assert handler.strip_app_prefix("/api/users") == "/users"
        assert handler.strip_app_prefix("/topic/messages") == "/topic/messages"


class TestEnableWebSocket:
    """@EnableWebSocket 데코레이터 테스트"""

    def test_enable_websocket_decorator(self, reset_container_manager):
        """@EnableWebSocket 데코레이터 기본 테스트"""

        @Component
        @EnableWebSocket
        class WebSocketConfig:
            pass

        assert is_websocket_enabled(WebSocketConfig) is True

    def test_not_enabled_without_decorator(self, reset_container_manager):
        """데코레이터 없으면 비활성화 상태"""

        @Component
        class SomeComponent:
            pass

        assert is_websocket_enabled(SomeComponent) is False

    def test_enable_websocket_with_factory(self, reset_container_manager):
        """@EnableWebSocket과 @Factory 함께 사용"""

        @Component
        @EnableWebSocket
        class WebSocketConfig:
            @Factory
            def stomp_endpoint_registry(self) -> StompEndpointRegistry:
                registry = StompEndpointRegistry()
                registry.add_endpoint("/ws").set_allowed_origins("*")
                return registry

            @Factory
            def message_broker_registry(self) -> MessageBrokerRegistry:
                registry = MessageBrokerRegistry()
                registry.enable_simple_broker("/topic", "/queue")
                registry.set_application_destination_prefixes("/app")
                return registry

        app = Application("test").scan(__import__(__name__)).ready()

        # WebSocketManager 확인
        ws_manager = app.websocket_manager
        assert ws_manager.enabled is True

        # 레지스트리 수집 확인
        assert len(ws_manager.endpoints) == 1
        assert ws_manager.endpoints[0].path == "/ws"

        # 경로 확인 메서드
        assert ws_manager.is_websocket_path("/ws") is True
        assert ws_manager.is_websocket_path("/ws/subpath") is True
        assert ws_manager.is_websocket_path("/api/other") is False


class TestWebSocketManager:
    """WebSocketManager 테스트"""

    def test_websocket_manager_disabled_by_default(self, reset_container_manager):
        """@EnableWebSocket 없으면 비활성화"""

        @Component
        class SomeService:
            pass

        app = Application("test").scan(__import__(__name__)).ready()

        ws_manager = app.websocket_manager
        assert ws_manager.enabled is False
        assert len(ws_manager.endpoints) == 0

    def test_websocket_manager_collects_registries(self, reset_container_manager):
        """WebSocketManager가 레지스트리 수집"""

        @Component
        @EnableWebSocket
        class WebSocketConfig:
            @Factory
            def stomp_endpoint_registry(self) -> StompEndpointRegistry:
                registry = StompEndpointRegistry()
                registry.add_endpoint("/ws-one")
                registry.add_endpoint("/ws-two").with_sockjs()
                return registry

            @Factory
            def message_broker_registry(self) -> MessageBrokerRegistry:
                registry = MessageBrokerRegistry()
                registry.enable_simple_broker("/topic")
                registry.set_application_destination_prefixes("/app", "/api")
                return registry

        app = Application("test").scan(__import__(__name__)).ready()

        ws_manager = app.websocket_manager
        assert ws_manager.enabled is True

        # 엔드포인트 수집 확인
        assert len(ws_manager.endpoints) == 2
        paths = ws_manager.get_endpoint_paths()
        assert "/ws-one" in paths
        assert "/ws-two" in paths

    def test_websocket_manager_get_endpoint_for_path(self, reset_container_manager):
        """경로에 해당하는 엔드포인트 조회"""

        @Component
        @EnableWebSocket
        class WebSocketConfig:
            @Factory
            def stomp_endpoint_registry(self) -> StompEndpointRegistry:
                registry = StompEndpointRegistry()
                registry.add_endpoint("/ws").set_allowed_origins("https://example.com")
                return registry

        app = Application("test").scan(__import__(__name__)).ready()

        ws_manager = app.websocket_manager

        endpoint = ws_manager.get_endpoint_for_path("/ws")
        assert endpoint is not None
        assert endpoint.path == "/ws"
        assert endpoint.allowed_origins == ["https://example.com"]

        # 없는 경로
        assert ws_manager.get_endpoint_for_path("/api") is None

    def test_application_websocket_manager_property(self, reset_container_manager):
        """Application.websocket_manager 프로퍼티 테스트"""

        @Component
        @EnableWebSocket
        class WebSocketConfig:
            pass

        app = Application("test").scan(__import__(__name__)).ready()

        # 같은 인스턴스 반환
        ws_manager1 = app.websocket_manager
        ws_manager2 = app.websocket_manager
        assert ws_manager1 is ws_manager2
