"""라우터 성능 벤치마크 테스트"""

import pytest
import time
from bloom import Application, Component, Controller
from bloom.web import Get, RequestMapping

pytestmark = pytest.mark.performance  # 이 모듈의 모든 테스트에 performance 마커 적용


@pytest.fixture
def large_scale_app(reset_container_manager):
    """대규모 라우트를 가진 애플리케이션"""
    from bloom.web.handler import HttpMethodHandler

    # 대규모 라우트를 위한 컨트롤러들 (fixture 내부 정의)
    # v1 전용 라우트들 - v2와 path가 겹치지 않도록 분리
    @Controller
    @RequestMapping("/api/v1")
    class ApiV1Controller:
        @Get("/members")
        def list_members(self):
            return {"members": []}

        @Get("/members/{id}")
        def get_member(self, id: str):
            return {"id": id}

        @Get("/members/{id}/articles")
        def get_member_articles(self, id: str):
            return {"articles": []}

        @Get("/members/{id}/articles/{article_id}")
        def get_member_article(self, id: str, article_id: str):
            return {"id": id, "article_id": article_id}

        @Get("/articles")
        def list_articles(self):
            return {"articles": []}

        @Get("/articles/{id}")
        def get_article(self, id: str):
            return {"id": id}

        @Get("/articles/{id}/replies")
        def get_article_replies(self, id: str):
            return {"replies": []}

        @Get("/articles/{id}/replies/{reply_id}")
        def get_article_reply(self, id: str, reply_id: str):
            return {"id": id, "reply_id": reply_id}

        @Get("/categories")
        def list_categories(self):
            return {"categories": []}

        @Get("/categories/{id}")
        def get_category(self, id: str):
            return {"id": id}

        @Get("/tags")
        def list_tags(self):
            return {"tags": []}

        @Get("/tags/{id}")
        def get_tag(self, id: str):
            return {"id": id}

        @Get("/search")
        def search(self):
            return {"results": []}

        @Get("/admin/members")
        def admin_list_members(self):
            return {"members": []}

        @Get("/admin/members/{id}")
        def admin_get_member(self, id: str):
            return {"id": id}

        @Get("/admin/settings")
        def admin_settings(self):
            return {"settings": {}}

    @Controller
    @RequestMapping("/api/v2")
    class ApiV2Controller:
        @Get("/users")
        def v2_list_users(self):
            return {"users": []}

        @Get("/users/{id}")
        def v2_get_user(self, id: str):
            return {"id": id}

        @Get("/posts")
        def v2_list_posts(self):
            return {"posts": []}

        @Get("/posts/{id}")
        def v2_get_post(self, id: str):
            return {"id": id}

        @Get("/comments")
        def v2_list_comments(self):
            return {"comments": []}

        @Get("/comments/{id}")
        def v2_get_comment(self, id: str):
            return {"id": id}

    app = Application("benchmark").ready()
    return app


class TestRouterPerformance:
    """라우터 성능 테스트"""

    def test_static_route_lookup_performance(self, large_scale_app):
        """정적 경로 조회 성능 - O(1) 해시맵 기대"""
        router = large_scale_app.router

        # 웜업
        for _ in range(100):
            router.find_handler("GET", "/api/v1/members")

        # 벤치마크
        iterations = 10000
        start = time.perf_counter()
        for _ in range(iterations):
            handler, params = router.find_handler("GET", "/api/v1/members")
            assert handler is not None
            assert params == {}
        end = time.perf_counter()

        elapsed = end - start
        per_lookup = (elapsed / iterations) * 1_000_000  # 마이크로초

        print(f"\n정적 경로 조회: {iterations}회 in {elapsed:.4f}초")
        print(f"평균: {per_lookup:.2f} μs/lookup")
        print(f"처리량: {iterations / elapsed:.0f} lookups/sec")

        # 성능 기준: 평균 10μs 이하 (100,000 lookups/sec 이상)
        assert per_lookup < 10, f"정적 경로 조회가 너무 느림: {per_lookup:.2f} μs"

    def test_dynamic_route_lookup_performance(self, large_scale_app):
        """동적 경로 조회 성능 - O(log n) 트리 탐색 기대"""
        router = large_scale_app.router

        # 웜업
        for _ in range(100):
            router.find_handler("GET", "/api/v1/members/123")

        # 벤치마크
        iterations = 10000
        start = time.perf_counter()
        for i in range(iterations):
            handler, params = router.find_handler("GET", f"/api/v1/members/{i}")
            assert handler is not None
            assert params == {"id": str(i)}
        end = time.perf_counter()

        elapsed = end - start
        per_lookup = (elapsed / iterations) * 1_000_000  # 마이크로초

        print(f"\n동적 경로 조회: {iterations}회 in {elapsed:.4f}초")
        print(f"평균: {per_lookup:.2f} μs/lookup")
        print(f"처리량: {iterations / elapsed:.0f} lookups/sec")

        # 성능 기준: 평균 15μs 이하 (66,000 lookups/sec 이상)
        assert per_lookup < 15, f"동적 경로 조회가 너무 느림: {per_lookup:.2f} μs"

    def test_nested_dynamic_route_performance(self, large_scale_app):
        """중첩된 동적 경로 성능"""
        router = large_scale_app.router

        # 웜업
        for _ in range(100):
            router.find_handler("GET", "/api/v1/members/123/articles/456")

        # 벤치마크
        iterations = 10000
        start = time.perf_counter()
        for i in range(iterations):
            handler, params = router.find_handler(
                "GET", f"/api/v1/members/{i}/articles/{i * 10}"
            )
            assert handler is not None
            assert params == {"id": str(i), "article_id": str(i * 10)}
        end = time.perf_counter()

        elapsed = end - start
        per_lookup = (elapsed / iterations) * 1_000_000  # 마이크로초

        print(f"\n중첩 동적 경로 조회: {iterations}회 in {elapsed:.4f}초")
        print(f"평균: {per_lookup:.2f} μs/lookup")
        print(f"처리량: {iterations / elapsed:.0f} lookups/sec")

        # 성능 기준: 평균 20μs 이하 (50,000 lookups/sec 이상)
        assert per_lookup < 20, f"중첩 동적 경로 조회가 너무 느림: {per_lookup:.2f} μs"

    def test_not_found_performance(self, large_scale_app):
        """존재하지 않는 경로 조회 성능"""
        router = large_scale_app.router

        # 웜업
        for _ in range(100):
            router.find_handler("GET", "/api/v1/nonexistent/path")

        # 벤치마크
        iterations = 10000
        start = time.perf_counter()
        for i in range(iterations):
            handler, params = router.find_handler("GET", f"/api/v1/nonexistent/{i}")
            assert handler is None
            assert params == {}
        end = time.perf_counter()

        elapsed = end - start
        per_lookup = (elapsed / iterations) * 1_000_000  # 마이크로초

        print(f"\n404 경로 조회: {iterations}회 in {elapsed:.4f}초")
        print(f"평균: {per_lookup:.2f} μs/lookup")
        print(f"처리량: {iterations / elapsed:.0f} lookups/sec")

        # 성능 기준: 평균 15μs 이하 (빠른 실패)
        assert per_lookup < 15, f"404 경로 조회가 너무 느림: {per_lookup:.2f} μs"

    def test_mixed_route_lookup_performance(self, large_scale_app):
        """혼합 경로 조회 성능 (실제 사용 패턴 시뮬레이션)"""
        router = large_scale_app.router

        test_paths = [
            ("GET", "/api/v1/members"),
            ("GET", "/api/v1/members/123"),
            ("GET", "/api/v1/articles"),
            ("GET", "/api/v1/articles/456"),
            ("GET", "/api/v1/members/123/articles"),
            ("GET", "/api/v1/members/123/articles/789"),
            ("GET", "/api/v2/users"),
            ("GET", "/api/v2/users/999"),
            ("GET", "/api/v1/search"),
            ("GET", "/api/v1/admin/members"),
        ]

        # 웜업
        for method, path in test_paths:
            router.find_handler(method, path)

        # 벤치마크
        iterations = 10000
        start = time.perf_counter()
        for i in range(iterations):
            method, path = test_paths[i % len(test_paths)]
            # 동적 파라미터 치환
            path = path.replace("123", str(i % 1000))
            path = path.replace("456", str(i % 500))
            path = path.replace("789", str(i % 100))
            path = path.replace("999", str(i % 2000))
            handler, params = router.find_handler(method, path)
            # 대부분 찾아야 함
            assert handler is not None or "/nonexistent/" in path
        end = time.perf_counter()

        elapsed = end - start
        per_lookup = (elapsed / iterations) * 1_000_000  # 마이크로초

        print(f"\n혼합 경로 조회: {iterations}회 in {elapsed:.4f}초")
        print(f"평균: {per_lookup:.2f} μs/lookup")
        print(f"처리량: {iterations / elapsed:.0f} lookups/sec")

        # 성능 기준: 평균 15μs 이하 (전체적으로 빠름)
        assert per_lookup < 15, f"혼합 경로 조회가 너무 느림: {per_lookup:.2f} μs"


class TestRouteTrieCorrectness:
    """RouteTrie 정확성 테스트"""

    def test_route_priority_static_over_dynamic(self):
        """정적 경로가 동적 경로보다 우선"""

        @Controller
        class PriorityController:
            @Get("/items/special")
            def special_item(self):
                return {"type": "special"}

            @Get("/items/{id}")
            def get_item(self, id: str):
                return {"type": "dynamic", "id": id}

        app = Application("priority_test").ready()
        router = app.router

        # 정적 경로 우선 매칭
        handler, params = router.find_handler("GET", "/items/special")
        assert handler is not None
        assert handler.handler_method.__name__ == "special_item"
        assert params == {}

        # 동적 경로 매칭
        handler, params = router.find_handler("GET", "/items/123")
        assert handler is not None
        assert handler.handler_method.__name__ == "get_item"
        assert params == {"id": "123"}

    def test_multiple_dynamic_params(self):
        """여러 동적 파라미터 처리"""

        @Controller
        class MultiParamController:
            @Get("/users/{user_id}/posts/{post_id}/comments/{comment_id}")
            def get_comment(self, user_id: str, post_id: str, comment_id: str):
                return {
                    "user_id": user_id,
                    "post_id": post_id,
                    "comment_id": comment_id,
                }

        app = Application("multi_param_test").ready()
        router = app.router

        handler, params = router.find_handler(
            "GET", "/users/u123/posts/p456/comments/c789"
        )
        assert handler is not None
        assert params == {"user_id": "u123", "post_id": "p456", "comment_id": "c789"}

    def test_trailing_slash_handling(self):
        """trailing slash 처리 확인"""

        @Controller
        class SlashController:
            @Get("/api/users")
            def list_users(self):
                return {"users": []}

        app = Application("slash_test").ready()
        router = app.router

        # trailing slash 없이 등록되었으면 그대로 매칭
        handler, params = router.find_handler("GET", "/api/users")
        assert handler is not None

        # trailing slash 있어도 매칭됨 (빈 세그먼트는 필터링되므로)
        handler, params = router.find_handler("GET", "/api/users/")
        assert handler is not None  # RouteTrie는 trailing slash를 무시함
