"""PathTrie 테스트

Trie 자료구조를 사용하여 HTTP Route와 STOMP MessageMapping 경로 매칭을 테스트합니다.
"""

import pytest
from dataclasses import dataclass

from bloom.web.routing.trie import PathTrie, PathIncluded, TrieMatch
from bloom.web.routing import Route
from bloom.web.messaging.decorators import MessageMappingInfo


# =============================================================================
# Test Fixtures - PathIncluded 구현체들
# =============================================================================


@dataclass
class MockRoute(PathIncluded):
    """테스트용 HTTP Route"""

    path: str
    method: str = "GET"
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"route_{self.path}"


@dataclass
class MockMessageMapping(PathIncluded):
    """테스트용 STOMP MessageMapping"""

    path: str
    handler_name: str = ""

    def __post_init__(self) -> None:
        if not self.handler_name:
            self.handler_name = f"handler_{self.path}"


# =============================================================================
# 1. 기본 삽입/조회 테스트
# =============================================================================
def need[T](item: T | None) -> T:
    """None이 아닌 값을 반환하거나 예외 발생"""
    if item is None:
        raise ValueError("Expected non-None value")
    return item


class TestTrieBasicOperations:
    """Trie 기본 작업 테스트"""

    def test_insert_and_find_exact_path(self):
        """정확한 경로 삽입 및 조회"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users")

        trie.insert(route)
        result = trie.find("/users")

        assert result is not None
        assert result.item == route
        assert result.path_params == {}

    def test_insert_multiple_paths(self):
        """여러 경로 삽입"""
        trie: PathTrie[MockRoute] = PathTrie()
        route1 = MockRoute(path="/users")
        route2 = MockRoute(path="/orders")
        route3 = MockRoute(path="/products")

        trie.insert(route1)
        trie.insert(route2)
        trie.insert(route3)

        assert trie.find("/users") is not None
        assert need(trie.find("/users")).item == route1
        assert need(trie.find("/orders")).item == route2
        assert need(trie.find("/products")).item == route3

    def test_find_non_existent_path(self):
        """존재하지 않는 경로 조회"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users")
        trie.insert(route)

        result = trie.find("/orders")
        assert result is None

    def test_nested_path(self):
        """중첩 경로"""
        trie: PathTrie[MockRoute] = PathTrie()
        route1 = MockRoute(path="/api/v1/users")
        route2 = MockRoute(path="/api/v1/orders")
        route3 = MockRoute(path="/api/v2/users")

        trie.insert(route1)
        trie.insert(route2)
        trie.insert(route3)

        assert need(trie.find("/api/v1/users")).item == route1
        assert need(trie.find("/api/v1/orders")).item == route2
        assert need(trie.find("/api/v2/users")).item == route3
        assert trie.find("/api/v1") is None  # 중간 경로는 매칭 안됨

    def test_root_path(self):
        """루트 경로"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/")

        trie.insert(route)
        result = trie.find("/")

        assert result is not None
        assert result.item == route


# =============================================================================
# 2. 경로 파라미터 테스트
# =============================================================================


class TestTriePathParameters:
    """경로 파라미터 테스트"""

    def test_single_path_param(self):
        """단일 경로 파라미터"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users/{id}")

        trie.insert(route)
        result = trie.find("/users/123")

        assert result is not None
        assert result.item == route
        assert result.path_params == {"id": "123"}

    def test_multiple_path_params(self):
        """복수 경로 파라미터"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users/{user_id}/orders/{order_id}")

        trie.insert(route)
        result = trie.find("/users/42/orders/100")

        assert result is not None
        assert result.path_params == {"user_id": "42", "order_id": "100"}

    def test_path_param_with_static_segments(self):
        """정적 세그먼트와 파라미터 혼합"""
        trie: PathTrie[MockRoute] = PathTrie()
        route1 = MockRoute(path="/users/{id}/profile")
        route2 = MockRoute(path="/users/{id}/settings")

        trie.insert(route1)
        trie.insert(route2)

        result1 = trie.find("/users/123/profile")
        result2 = trie.find("/users/456/settings")

        assert result1 is not None
        assert result1.item == route1
        assert result1.path_params == {"id": "123"}

        assert result2 is not None
        assert result2.item == route2
        assert result2.path_params == {"id": "456"}

    def test_typed_path_param_int(self):
        """타입 힌트가 있는 경로 파라미터 - int"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users/{id:int}")

        trie.insert(route)

        # 숫자만 매칭
        result = trie.find("/users/123")
        assert result is not None
        assert result.path_params == {"id": "123"}

        # 문자는 매칭 안됨
        result_fail = trie.find("/users/abc")
        assert result_fail is None

    def test_typed_path_param_path(self):
        """타입 힌트가 있는 경로 파라미터 - path (여러 세그먼트)"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/files/{filepath:path}")

        trie.insert(route)

        result = trie.find("/files/docs/readme.txt")
        assert result is not None
        assert result.path_params == {"filepath": "docs/readme.txt"}

    def test_path_param_different_values(self):
        """같은 패턴에 다른 값들"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users/{id}")
        trie.insert(route)

        result1 = trie.find("/users/1")
        result2 = trie.find("/users/999")
        result3 = trie.find("/users/john")

        assert need(result1).path_params == {"id": "1"}
        assert need(result2).path_params == {"id": "999"}
        assert need(result3).path_params == {"id": "john"}


# =============================================================================
# 3. 우선순위 테스트 (정적 > 동적)
# =============================================================================


class TestTriePriority:
    """경로 매칭 우선순위 테스트"""

    def test_static_over_dynamic(self):
        """정적 경로가 동적 경로보다 우선"""
        trie: PathTrie[MockRoute] = PathTrie()
        dynamic = MockRoute(path="/users/{id}")
        static = MockRoute(path="/users/me")

        trie.insert(dynamic)
        trie.insert(static)

        # "me"는 정적 경로 매칭
        result = trie.find("/users/me")
        assert result is not None
        assert result.item == static
        assert result.path_params == {}

        # 다른 값은 동적 경로 매칭
        result2 = trie.find("/users/123")
        assert result2 is not None
        assert result2.item == dynamic

    def test_static_over_dynamic_reverse_insert(self):
        """삽입 순서와 무관하게 정적 우선"""
        trie: PathTrie[MockRoute] = PathTrie()
        static = MockRoute(path="/users/me")
        dynamic = MockRoute(path="/users/{id}")

        # 순서 바꿔서 삽입
        trie.insert(static)
        trie.insert(dynamic)

        result = trie.find("/users/me")
        assert need(result).item == static

    def test_multiple_dynamic_segments(self):
        """여러 동적 세그먼트 우선순위"""
        trie: PathTrie[MockRoute] = PathTrie()
        route1 = MockRoute(path="/users/{id}/orders/{oid}")
        route2 = MockRoute(path="/users/{id}/orders/latest")

        trie.insert(route1)
        trie.insert(route2)

        # "latest"는 정적 매칭
        result = trie.find("/users/123/orders/latest")
        assert need(result).item == route2

        # 숫자는 동적 매칭
        result2 = trie.find("/users/123/orders/456")
        assert need(result2).item == route1


# =============================================================================
# 4. MessageMapping 테스트 (STOMP)
# =============================================================================


class TestTrieMessageMapping:
    """STOMP MessageMapping용 Trie 테스트"""

    def test_message_mapping_basic(self):
        """기본 메시지 매핑"""
        trie: PathTrie[MockMessageMapping] = PathTrie()
        mapping = MockMessageMapping(path="/chat/message")

        trie.insert(mapping)
        result = trie.find("/chat/message")

        assert result is not None
        assert result.item == mapping

    def test_message_mapping_with_room(self):
        """채팅방 파라미터"""
        trie: PathTrie[MockMessageMapping] = PathTrie()
        mapping = MockMessageMapping(path="/chat/{room}")

        trie.insert(mapping)
        result = trie.find("/chat/general")

        assert result is not None
        assert result.path_params == {"room": "general"}

    def test_message_mapping_complex(self):
        """복잡한 메시지 매핑"""
        trie: PathTrie[MockMessageMapping] = PathTrie()
        mapping1 = MockMessageMapping(path="/app/chat/{room}/message")
        mapping2 = MockMessageMapping(path="/app/chat/{room}/typing")
        mapping3 = MockMessageMapping(path="/app/user/{user_id}/status")

        trie.insert(mapping1)
        trie.insert(mapping2)
        trie.insert(mapping3)

        result1 = trie.find("/app/chat/room1/message")
        assert need(result1).item == mapping1
        assert need(result1).path_params == {"room": "room1"}

        result2 = trie.find("/app/chat/room2/typing")
        assert need(result2).item == mapping2
        result3 = trie.find("/app/user/42/status")
        assert need(result3).item == mapping3
        assert need(result3).path_params == {"user_id": "42"}


# =============================================================================
# 5. 제네릭 타입 테스트
# =============================================================================


class TestTrieGenericTypes:
    """제네릭 타입 테스트"""

    def test_different_generic_types(self):
        """다른 제네릭 타입으로 별개 Trie"""
        route_trie: PathTrie[MockRoute] = PathTrie()
        message_trie: PathTrie[MockMessageMapping] = PathTrie()

        route = MockRoute(path="/users/{id}")
        mapping = MockMessageMapping(path="/users/{id}")

        route_trie.insert(route)
        message_trie.insert(mapping)

        route_result = route_trie.find("/users/123")
        message_result = message_trie.find("/users/123")

        assert isinstance(need(route_result).item, MockRoute)
        assert isinstance(need(message_result).item, MockMessageMapping)


# =============================================================================
# 6. 삭제 테스트
# =============================================================================


class TestTrieRemove:
    """Trie 삭제 테스트"""

    def test_remove_path(self):
        """경로 삭제"""
        trie: PathTrie[MockRoute] = PathTrie()
        route1 = MockRoute(path="/users")
        route2 = MockRoute(path="/orders")

        trie.insert(route1)
        trie.insert(route2)

        # 삭제 전
        assert trie.find("/users") is not None

        # 삭제
        removed = trie.remove("/users")
        assert removed is True

        # 삭제 후
        assert trie.find("/users") is None
        assert trie.find("/orders") is not None  # 다른 경로는 유지

    def test_remove_non_existent(self):
        """존재하지 않는 경로 삭제"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users")
        trie.insert(route)

        removed = trie.remove("/orders")
        assert removed is False


# =============================================================================
# 7. 모든 경로 조회 테스트
# =============================================================================


class TestTrieGetAll:
    """모든 항목 조회 테스트"""

    def test_get_all_items(self):
        """모든 항목 조회"""
        trie: PathTrie[MockRoute] = PathTrie()
        route1 = MockRoute(path="/users")
        route2 = MockRoute(path="/users/{id}")
        route3 = MockRoute(path="/orders")
        route4 = MockRoute(path="/orders/{id}/items")

        trie.insert(route1)
        trie.insert(route2)
        trie.insert(route3)
        trie.insert(route4)

        all_items = trie.get_all()
        assert len(all_items) == 4
        assert route1 in all_items
        assert route2 in all_items
        assert route3 in all_items
        assert route4 in all_items

    def test_get_all_empty(self):
        """빈 Trie에서 조회"""
        trie: PathTrie[MockRoute] = PathTrie()
        assert trie.get_all() == []


# =============================================================================
# 8. 엣지 케이스 테스트
# =============================================================================


class TestTrieEdgeCases:
    """엣지 케이스 테스트"""

    def test_trailing_slash(self):
        """후행 슬래시 처리"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users")
        trie.insert(route)

        # 후행 슬래시 있어도 매칭
        result = trie.find("/users/")
        assert result is not None
        assert result.item == route

    def test_empty_segment(self):
        """빈 세그먼트 (연속 슬래시)"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users")
        trie.insert(route)

        # 연속 슬래시는 정규화
        result = trie.find("//users")
        assert result is not None

    def test_special_characters_in_param(self):
        """파라미터에 특수문자"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/files/{filename}")
        trie.insert(route)

        result = trie.find("/files/my-file_v2.txt")
        assert result is not None
        assert result.path_params == {"filename": "my-file_v2.txt"}

    def test_unicode_path(self):
        """유니코드 경로"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/게시판/{id}")
        trie.insert(route)

        result = trie.find("/게시판/123")
        assert result is not None
        assert result.path_params == {"id": "123"}

    def test_duplicate_insert(self):
        """중복 삽입"""
        trie: PathTrie[MockRoute] = PathTrie()
        route1 = MockRoute(path="/users", name="first")
        route2 = MockRoute(path="/users", name="second")

        trie.insert(route1)
        trie.insert(route2)

        # 마지막 삽입된 것이 유지
        result = trie.find("/users")
        assert need(result).item == route2


# =============================================================================
# 9. 성능 관련 테스트
# =============================================================================


class TestTriePerformance:
    """성능 관련 테스트"""

    def test_many_routes(self):
        """많은 라우트 처리"""
        trie: PathTrie[MockRoute] = PathTrie()

        # 100개 라우트 삽입
        for i in range(100):
            route = MockRoute(path=f"/api/v1/resource{i}")
            trie.insert(route)

        # 모든 라우트 찾기
        for i in range(100):
            result = trie.find(f"/api/v1/resource{i}")
            assert result is not None

    def test_deep_nesting(self):
        """깊은 중첩 경로"""
        trie: PathTrie[MockRoute] = PathTrie()
        deep_path = "/a/b/c/d/e/f/g/h/i/j"
        route = MockRoute(path=deep_path)

        trie.insert(route)
        result = trie.find(deep_path)

        assert result is not None
        assert result.item == route


# =============================================================================
# 10. contains 테스트
# =============================================================================


class TestTrieContains:
    """포함 여부 확인 테스트"""

    def test_contains_exact(self):
        """정확한 경로 포함 확인"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users")
        trie.insert(route)

        assert trie.contains("/users") is True
        assert trie.contains("/orders") is False

    def test_contains_with_params(self):
        """파라미터 경로 포함 확인"""
        trie: PathTrie[MockRoute] = PathTrie()
        route = MockRoute(path="/users/{id}")
        trie.insert(route)

        # 패턴으로 확인
        assert trie.contains("/users/{id}") is True
        # 실제 값으로는 contains가 아닌 find 사용
        assert trie.find("/users/123") is not None


# =============================================================================
# 11. 실제 클래스 통합 테스트
# =============================================================================


class TestTrieRealClassIntegration:
    """실제 Route/MessageMappingInfo 클래스 통합 테스트"""

    def test_route_is_path_included(self):
        """Route가 PathIncluded 프로토콜 구현"""

        async def dummy_handler():
            pass

        route = Route(
            path="/users/{id}",
            method="GET",
            handler=dummy_handler,
        )

        # Protocol 검사
        assert isinstance(route, PathIncluded)
        assert hasattr(route, "path")
        assert route.path == "/users/{id}"

    def test_route_with_trie(self):
        """Route와 PathTrie 통합"""

        async def get_users():
            pass

        async def get_user():
            pass

        async def get_user_orders():
            pass

        trie: PathTrie[Route] = PathTrie()

        route1 = Route(path="/users", method="GET", handler=get_users)
        route2 = Route(path="/users/{id}", method="GET", handler=get_user)
        route3 = Route(path="/users/{id}/orders", method="GET", handler=get_user_orders)

        trie.insert(route1)
        trie.insert(route2)
        trie.insert(route3)

        # 매칭 테스트
        result1 = trie.find("/users")
        assert result1 is not None
        assert result1.item.handler == get_users

        result2 = trie.find("/users/123")
        assert result2 is not None
        assert result2.item.handler == get_user
        assert result2.path_params == {"id": "123"}

        result3 = trie.find("/users/456/orders")
        assert result3 is not None
        assert result3.item.handler == get_user_orders
        assert result3.path_params == {"id": "456"}

    def test_message_mapping_info_with_trie(self):
        """MessageMappingInfo와 PathTrie 통합"""
        import re

        # MessageMappingInfo의 destination을 path로 사용하기 위한 래퍼
        @dataclass
        class MessageMappingWrapper(PathIncluded):
            """MessageMappingInfo를 PathIncluded로 래핑"""

            path: str
            info: MessageMappingInfo

        def create_mapping(destination: str) -> MessageMappingWrapper:
            pattern = re.compile(
                destination.replace("{", "(?P<").replace("}", ">[^/]+)")
            )
            variables = re.findall(r"\{(\w+)\}", destination)
            info = MessageMappingInfo(
                destination=destination,
                pattern=pattern,
                variables=variables,
            )
            return MessageMappingWrapper(path=destination, info=info)

        trie: PathTrie[MessageMappingWrapper] = PathTrie()

        mapping1 = create_mapping("/app/chat/{room}/message")
        mapping2 = create_mapping("/app/chat/{room}/typing")
        mapping3 = create_mapping("/app/user/{user_id}/status")

        trie.insert(mapping1)
        trie.insert(mapping2)
        trie.insert(mapping3)

        # 매칭 테스트
        result1 = trie.find("/app/chat/general/message")
        assert result1 is not None
        assert result1.item.info.destination == "/app/chat/{room}/message"
        assert result1.path_params == {"room": "general"}

        result2 = trie.find("/app/chat/room123/typing")
        assert result2 is not None
        assert result2.item.info.destination == "/app/chat/{room}/typing"
        assert result2.path_params == {"room": "room123"}

        result3 = trie.find("/app/user/42/status")
        assert result3 is not None
        assert result3.path_params == {"user_id": "42"}

    def test_mixed_static_and_dynamic_routes(self):
        """정적/동적 경로 혼합 실제 시나리오"""

        async def handler():
            pass

        trie: PathTrie[Route] = PathTrie()

        # REST API 일반적인 패턴
        routes = [
            Route(path="/api/v1/users", method="GET", handler=handler),
            Route(path="/api/v1/users/me", method="GET", handler=handler),  # 정적 우선
            Route(path="/api/v1/users/{id}", method="GET", handler=handler),
            Route(path="/api/v1/users/{id}/profile", method="GET", handler=handler),
            Route(path="/api/v1/orders", method="GET", handler=handler),
            Route(path="/api/v1/orders/{order_id}", method="GET", handler=handler),
            Route(
                path="/api/v1/orders/{order_id}/items", method="GET", handler=handler
            ),
            Route(
                path="/api/v1/orders/{order_id}/items/{item_id}",
                method="GET",
                handler=handler,
            ),
        ]

        for route in routes:
            trie.insert(route)

        # 테스트
        assert need(trie.find("/api/v1/users")).item.path == "/api/v1/users"
        assert (
            need(trie.find("/api/v1/users/me")).item.path == "/api/v1/users/me"
        )  # 정적 우선
        assert need(trie.find("/api/v1/users/123")).item.path == "/api/v1/users/{id}"
        assert (
            need(trie.find("/api/v1/users/456/profile")).item.path
            == "/api/v1/users/{id}/profile"
        )

        result = trie.find("/api/v1/orders/1/items/2")
        assert result is not None
        assert result.path_params == {"order_id": "1", "item_id": "2"}
