"""PathTrie 통합 테스트

실제 Router, MessageController에 PathTrie를 적용한 통합 테스트입니다.
"""

import pytest
from dataclasses import dataclass

from bloom.web.routing import Router, Route, PathTrie, TrieMatch
from bloom.web.messaging.decorators import (
    MessageMapping,
    SubscribeMapping,
    MessageController,
    MessageMappingInfo,
    SubscribeMappingInfo,
    get_message_controller_info,
)


# =============================================================================
# 1. Router with PathTrie 테스트
# =============================================================================


class TestRouterWithTrie:
    """Router에 PathTrie 적용 테스트"""

    def test_router_uses_trie_for_matching(self):
        """Router가 Trie를 사용하여 매칭"""
        router = Router()

        @router.get("/users")
        async def list_users():
            return []

        @router.get("/users/{id}")
        async def get_user(id: int):
            return {"id": id}

        @router.get("/users/{id}/orders")
        async def get_user_orders(id: int):
            return []

        # Trie 기반 매칭 테스트
        match1 = router.match("/users", "GET")
        assert match1 is not None
        assert match1.handler == list_users

        match2 = router.match("/users/123", "GET")
        assert match2 is not None
        assert match2.handler == get_user
        assert match2.path_params == {"id": "123"}

        match3 = router.match("/users/456/orders", "GET")
        assert match3 is not None
        assert match3.handler == get_user_orders
        assert match3.path_params == {"id": "456"}

    def test_router_trie_static_priority(self):
        """정적 경로가 동적 경로보다 우선"""
        router = Router()

        @router.get("/users/me")
        async def get_current_user():
            return {"id": "me"}

        @router.get("/users/{id}")
        async def get_user(id: str):
            return {"id": id}

        # "me"는 정적 매칭
        match_me = router.match("/users/me", "GET")
        assert match_me is not None
        assert match_me.handler == get_current_user
        assert match_me.path_params == {}

        # 다른 값은 동적 매칭
        match_123 = router.match("/users/123", "GET")
        assert match_123 is not None
        assert match_123.handler == get_user
        assert match_123.path_params == {"id": "123"}

    def test_router_trie_typed_params(self):
        """타입이 있는 경로 파라미터"""
        router = Router()

        @router.get("/items/{id:int}")
        async def get_item(id: int):
            return {"id": id}

        # 숫자만 매칭
        match_num = router.match("/items/123", "GET")
        assert match_num is not None

        # 문자는 매칭 안됨
        match_str = router.match("/items/abc", "GET")
        assert match_str is None

    def test_router_trie_multiple_methods(self):
        """같은 경로에 다른 HTTP 메서드"""
        router = Router()

        @router.get("/users")
        async def list_users():
            return []

        @router.post("/users")
        async def create_user():
            return {"created": True}

        @router.get("/users/{id}")
        async def get_user(id: str):
            return {}

        @router.put("/users/{id}")
        async def update_user(id: str):
            return {}

        @router.delete("/users/{id}")
        async def delete_user(id: str):
            return {}

        # GET /users
        assert router.match("/users", "GET").handler == list_users
        # POST /users
        assert router.match("/users", "POST").handler == create_user
        # GET /users/1
        assert router.match("/users/1", "GET").handler == get_user
        # PUT /users/1
        assert router.match("/users/1", "PUT").handler == update_user
        # DELETE /users/1
        assert router.match("/users/1", "DELETE").handler == delete_user

    def test_router_trie_with_sub_router(self):
        """서브 라우터와 Trie 통합"""
        main_router = Router()
        api_router = Router()  # prefix 없이 생성

        @api_router.get("/users")
        async def list_users():
            return []

        @api_router.get("/users/{id}")
        async def get_user(id: str):
            return {}

        main_router.include_router(api_router, prefix="/api/v1")

        match1 = main_router.match("/api/v1/users", "GET")
        assert match1 is not None

        match2 = main_router.match("/api/v1/users/123", "GET")
        assert match2 is not None
        assert match2.path_params == {"id": "123"}

    def test_router_trie_performance(self):
        """많은 라우트에서 Trie 성능"""
        router = Router()

        # 100개의 다양한 라우트 등록
        async def dummy_handler():
            pass

        for i in range(100):
            router.add_route(f"/resource{i}", "GET", dummy_handler)
            router.add_route(f"/resource{i}/{{id}}", "GET", dummy_handler)
            router.add_route(f"/resource{i}/{{id}}/sub", "GET", dummy_handler)

        # 매칭 테스트
        for i in range(100):
            match = router.match(f"/resource{i}", "GET")
            assert match is not None

            match_with_id = router.match(f"/resource{i}/123", "GET")
            assert match_with_id is not None
            assert match_with_id.path_params == {"id": "123"}


# =============================================================================
# 2. MessageMapping Registry with PathTrie 테스트
# =============================================================================


class TestMessageMappingRegistry:
    """MessageMapping 레지스트리에 PathTrie 적용 테스트"""

    def test_message_mapping_registry_find(self):
        """MessageMapping 레지스트리에서 destination 매칭"""
        from bloom.web.messaging.registry import MessageMappingRegistry

        registry = MessageMappingRegistry()

        @MessageController("/app")
        class ChatController:
            @MessageMapping("/chat/{room}")
            async def handle_chat(self, room: str):
                pass

            @MessageMapping("/chat/{room}/message")
            async def handle_message(self, room: str):
                pass

        # 컨트롤러 등록
        registry.register_controller(ChatController)

        # 매칭 테스트
        result1 = registry.find_message_handler("/app/chat/general")
        assert result1 is not None
        assert result1.path_params == {"room": "general"}

        result2 = registry.find_message_handler("/app/chat/room1/message")
        assert result2 is not None
        assert result2.path_params == {"room": "room1"}

    def test_subscribe_mapping_registry_find(self):
        """SubscribeMapping 레지스트리에서 destination 매칭"""
        from bloom.web.messaging.registry import MessageMappingRegistry

        registry = MessageMappingRegistry()

        @MessageController("/app")
        class NotificationController:
            @SubscribeMapping("/notifications/{user_id}")
            async def on_subscribe_notifications(self, user_id: str):
                return []

            @SubscribeMapping("/topic/{channel}")
            async def on_subscribe_topic(self, channel: str):
                return []

        registry.register_controller(NotificationController)

        # 매칭 테스트
        result1 = registry.find_subscribe_handler("/app/notifications/user123")
        assert result1 is not None
        assert result1.path_params == {"user_id": "user123"}

        result2 = registry.find_subscribe_handler("/app/topic/news")
        assert result2 is not None
        assert result2.path_params == {"channel": "news"}

    def test_message_mapping_static_priority(self):
        """MessageMapping에서 정적 경로 우선순위"""
        from bloom.web.messaging.registry import MessageMappingRegistry

        registry = MessageMappingRegistry()

        @MessageController("/app")
        class PriorityController:
            @MessageMapping("/chat/broadcast")
            async def handle_broadcast(self):
                pass

            @MessageMapping("/chat/{room}")
            async def handle_room(self, room: str):
                pass

        registry.register_controller(PriorityController)

        # "broadcast"는 정적 매칭
        result_broadcast = registry.find_message_handler("/app/chat/broadcast")
        assert result_broadcast is not None
        assert result_broadcast.path_params == {}

        # 다른 값은 동적 매칭
        result_room = registry.find_message_handler("/app/chat/general")
        assert result_room is not None
        assert result_room.path_params == {"room": "general"}

    def test_mixed_message_and_subscribe_mappings(self):
        """MessageMapping과 SubscribeMapping 혼합"""
        from bloom.web.messaging.registry import MessageMappingRegistry

        registry = MessageMappingRegistry()

        @MessageController("/app")
        class MixedController:
            @MessageMapping("/send/{topic}")
            async def send_message(self, topic: str):
                pass

            @SubscribeMapping("/subscribe/{topic}")
            async def subscribe_topic(self, topic: str):
                return []

        registry.register_controller(MixedController)

        # MessageMapping
        msg_result = registry.find_message_handler("/app/send/news")
        assert msg_result is not None
        assert msg_result.path_params == {"topic": "news"}

        # SubscribeMapping
        sub_result = registry.find_subscribe_handler("/app/subscribe/news")
        assert sub_result is not None
        assert sub_result.path_params == {"topic": "news"}

        # 교차 검색 안됨
        assert registry.find_message_handler("/app/subscribe/news") is None
        assert registry.find_subscribe_handler("/app/send/news") is None


# =============================================================================
# 3. End-to-End 통합 테스트
# =============================================================================


class TestEndToEndIntegration:
    """전체 시스템 통합 테스트"""

    def test_complete_rest_api_routing(self):
        """완전한 REST API 라우팅 시나리오"""
        router = Router()

        # REST API 엔드포인트 정의
        @router.get("/api/v1/products")
        async def list_products():
            return []

        @router.post("/api/v1/products")
        async def create_product():
            return {}

        @router.get("/api/v1/products/{product_id}")
        async def get_product(product_id: str):
            return {}

        @router.put("/api/v1/products/{product_id}")
        async def update_product(product_id: str):
            return {}

        @router.delete("/api/v1/products/{product_id}")
        async def delete_product(product_id: str):
            return {}

        @router.get("/api/v1/products/{product_id}/reviews")
        async def get_product_reviews(product_id: str):
            return []

        @router.post("/api/v1/products/{product_id}/reviews")
        async def create_product_review(product_id: str):
            return {}

        @router.get("/api/v1/products/{product_id}/reviews/{review_id}")
        async def get_product_review(product_id: str, review_id: str):
            return {}

        # 테스트
        test_cases = [
            ("/api/v1/products", "GET", list_products, {}),
            ("/api/v1/products", "POST", create_product, {}),
            ("/api/v1/products/123", "GET", get_product, {"product_id": "123"}),
            ("/api/v1/products/456", "PUT", update_product, {"product_id": "456"}),
            ("/api/v1/products/789", "DELETE", delete_product, {"product_id": "789"}),
            (
                "/api/v1/products/100/reviews",
                "GET",
                get_product_reviews,
                {"product_id": "100"},
            ),
            (
                "/api/v1/products/100/reviews",
                "POST",
                create_product_review,
                {"product_id": "100"},
            ),
            (
                "/api/v1/products/100/reviews/5",
                "GET",
                get_product_review,
                {"product_id": "100", "review_id": "5"},
            ),
        ]

        for path, method, expected_handler, expected_params in test_cases:
            match = router.match(path, method)
            assert match is not None, f"Failed to match {method} {path}"
            assert match.handler == expected_handler, f"Wrong handler for {method} {path}"
            assert match.path_params == expected_params, f"Wrong params for {method} {path}"

    def test_complete_websocket_messaging(self):
        """완전한 WebSocket 메시징 시나리오"""
        from bloom.web.messaging.registry import MessageMappingRegistry

        registry = MessageMappingRegistry()

        @MessageController("/app")
        class GameController:
            @MessageMapping("/game/{game_id}/join")
            async def join_game(self, game_id: str):
                pass

            @MessageMapping("/game/{game_id}/move")
            async def make_move(self, game_id: str):
                pass

            @MessageMapping("/game/{game_id}/chat")
            async def game_chat(self, game_id: str):
                pass

            @SubscribeMapping("/game/{game_id}/state")
            async def subscribe_game_state(self, game_id: str):
                return {}

            @SubscribeMapping("/game/{game_id}/players")
            async def subscribe_players(self, game_id: str):
                return []

        registry.register_controller(GameController)

        # MessageMapping 테스트
        join_result = registry.find_message_handler("/app/game/game123/join")
        assert join_result is not None
        assert join_result.path_params == {"game_id": "game123"}

        move_result = registry.find_message_handler("/app/game/game456/move")
        assert move_result is not None
        assert move_result.path_params == {"game_id": "game456"}

        # SubscribeMapping 테스트
        state_result = registry.find_subscribe_handler("/app/game/game789/state")
        assert state_result is not None
        assert state_result.path_params == {"game_id": "game789"}

        players_result = registry.find_subscribe_handler("/app/game/game000/players")
        assert players_result is not None
        assert players_result.path_params == {"game_id": "game000"}

    def test_router_get_all_routes_with_trie(self):
        """Trie에서 모든 라우트 조회"""
        router = Router()

        @router.get("/users")
        async def list_users():
            pass

        @router.get("/users/{id}")
        async def get_user():
            pass

        @router.post("/users")
        async def create_user():
            pass

        routes = router.get_routes()
        assert len(routes) == 3

        paths = [r.path for r in routes]
        assert "/users" in paths
        assert "/users/{id}" in paths
