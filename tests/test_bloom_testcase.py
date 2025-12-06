"""BloomTestCase 테스팅 모듈 TDD 테스트

TestClient, MockBean, 픽스처 통합 테스트
"""

import pytest
import json
from dataclasses import dataclass
from typing import Optional
from unittest.mock import MagicMock

from bloom.core import (
    Component,
    Service,
    Repository,
    Configuration,
    Factory,
    get_container_manager,
    reset_container_manager,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def reset_manager():
    """각 테스트 전후로 컨테이너 초기화"""
    reset_container_manager()
    yield
    reset_container_manager()


# =============================================================================
# Test: BloomTestCase 기본
# =============================================================================


class TestBloomTestCaseBasic:
    """BloomTestCase 기본 기능 테스트"""

    @pytest.mark.asyncio
    async def test_testcase_setup_teardown(self):
        """setUp/tearDown 자동 호출"""
        from bloom.testing import BloomTestCase

        class MyTest(BloomTestCase):
            setup_called = False
            teardown_called = False

            async def setUp(self):
                MyTest.setup_called = True

            async def tearDown(self):
                MyTest.teardown_called = True

            async def test_example(self):
                pass

        test = MyTest()
        await test._run_test("test_example")

        assert MyTest.setup_called
        assert MyTest.teardown_called

    @pytest.mark.asyncio
    async def test_testcase_container_initialized(self):
        """컨테이너가 자동으로 초기화됨"""
        from bloom.testing import BloomTestCase

        @Service
        class MyService:
            def get_value(self) -> str:
                return "real"

        class MyTest(BloomTestCase):
            async def test_service(self):
                service = await self.get_instance(MyService)
                assert service.get_value() == "real"

        test = MyTest()
        await test._run_test("test_service")

    @pytest.mark.asyncio
    async def test_testcase_get_instance(self):
        """get_instance로 DI 컨테이너에서 인스턴스 획득"""
        from bloom.testing import BloomTestCase

        @Service
        class UserService:
            def get_user(self, id: int) -> dict:
                return {"id": id, "name": f"User {id}"}

        class MyTest(BloomTestCase):
            async def test_user_service(self):
                service = await self.get_instance(UserService)
                user = service.get_user(1)
                assert user["id"] == 1

        test = MyTest()
        await test._run_test("test_user_service")


# =============================================================================
# Test: MockBean
# =============================================================================


class TestMockBean:
    """@MockBean 데코레이터 테스트"""

    @pytest.mark.asyncio
    async def test_mock_bean_replaces_real_instance(self):
        """@MockBean이 실제 인스턴스를 대체"""
        from bloom.testing import BloomTestCase, MockBean

        @Service
        class ExternalService:
            def call_api(self) -> str:
                return "real api call"

        @Service
        class MyService:
            external: ExternalService

            def process(self) -> str:
                return self.external.call_api()

        class MyTest(BloomTestCase):
            external: MockBean[ExternalService]

            async def test_with_mock(self):
                self.external.call_api.return_value = "mocked response"

                service = await self.get_instance(MyService)
                result = service.process()

                assert result == "mocked response"
                self.external.call_api.assert_called_once()

        test = MyTest()
        await test._run_test("test_with_mock")

    @pytest.mark.asyncio
    async def test_mock_bean_with_custom_return(self):
        """MockBean 커스텀 반환값"""
        from bloom.testing import BloomTestCase, MockBean

        @Repository
        class UserRepository:
            def find_by_id(self, id: int) -> Optional[dict]:
                # 실제로는 DB 조회
                return None

        @Service
        class UserService:
            repo: UserRepository

            def get_user(self, id: int) -> dict:
                user = self.repo.find_by_id(id)
                if not user:
                    raise ValueError("User not found")
                return user

        class MyTest(BloomTestCase):
            repo: MockBean[UserRepository]

            async def test_user_found(self):
                self.repo.find_by_id.return_value = {"id": 1, "name": "Test User"}

                service = await self.get_instance(UserService)
                user = service.get_user(1)

                assert user["name"] == "Test User"

            async def test_user_not_found(self):
                self.repo.find_by_id.return_value = None

                service = await self.get_instance(UserService)
                with pytest.raises(ValueError, match="User not found"):
                    service.get_user(999)

        test = MyTest()
        await test._run_test("test_user_found")
        await test._run_test("test_user_not_found")

    @pytest.mark.asyncio
    async def test_multiple_mock_beans(self):
        """여러 MockBean 동시 사용"""
        from bloom.testing import BloomTestCase, MockBean

        @Service
        class ServiceA:
            def method_a(self) -> str:
                return "a"

        @Service
        class ServiceB:
            def method_b(self) -> str:
                return "b"

        @Service
        class CompositeService:
            service_a: ServiceA
            service_b: ServiceB

            def combined(self) -> str:
                return f"{self.service_a.method_a()}-{self.service_b.method_b()}"

        class MyTest(BloomTestCase):
            service_a: MockBean[ServiceA]
            service_b: MockBean[ServiceB]

            async def test_combined(self):
                self.service_a.method_a.return_value = "mocked_a"
                self.service_b.method_b.return_value = "mocked_b"

                service = await self.get_instance(CompositeService)
                result = service.combined()

                assert result == "mocked_a-mocked_b"

        test = MyTest()
        await test._run_test("test_combined")


# =============================================================================
# Test: TestClient - HTTP
# =============================================================================


class TestHTTPClient:
    """TestClient HTTP 테스트"""

    @pytest.mark.asyncio
    async def test_get_request(self):
        """GET 요청 테스트"""
        from bloom.testing import BloomTestCase
        from bloom.web import ASGIApplication, JSONResponse

        app = ASGIApplication()

        @app.get("/api/users/{user_id}")
        async def get_user(request):
            user_id = request.path_params.get("user_id")
            return JSONResponse({"id": int(user_id), "name": f"User {user_id}"})

        class MyTest(BloomTestCase):
            async def test_get_user(self):
                async with self.test_client(app) as client:
                    response = await client.get("/api/users/1")

                    assert response.status_code == 200
                    data = response.json()
                    assert data["id"] == 1
                    assert data["name"] == "User 1"

        test = MyTest()
        await test._run_test("test_get_user")

    @pytest.mark.asyncio
    async def test_post_request_with_json(self):
        """POST JSON 요청 테스트"""
        from bloom.testing import BloomTestCase
        from bloom.web import ASGIApplication, JSONResponse

        app = ASGIApplication()

        @app.post("/api/users")
        async def create_user(request):
            body = await request.json()
            return JSONResponse(
                {"id": 1, "name": body["name"]},
                status_code=201,
            )

        class MyTest(BloomTestCase):
            async def test_create_user(self):
                async with self.test_client(app) as client:
                    response = await client.post(
                        "/api/users",
                        json={"name": "New User"},
                    )

                    assert response.status_code == 201
                    data = response.json()
                    assert data["name"] == "New User"

        test = MyTest()
        await test._run_test("test_create_user")

    @pytest.mark.asyncio
    async def test_request_with_headers(self):
        """헤더 포함 요청 테스트"""
        from bloom.testing import BloomTestCase
        from bloom.web import ASGIApplication, JSONResponse

        app = ASGIApplication()

        @app.get("/api/protected")
        async def protected(request):
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer "):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return JSONResponse({"message": "Success"})

        class MyTest(BloomTestCase):
            async def test_with_auth(self):
                async with self.test_client(app) as client:
                    response = await client.get(
                        "/api/protected",
                        headers={"Authorization": "Bearer token123"},
                    )

                    assert response.status_code == 200

            async def test_without_auth(self):
                async with self.test_client(app) as client:
                    response = await client.get("/api/protected")

                    assert response.status_code == 401

        test = MyTest()
        await test._run_test("test_with_auth")
        await test._run_test("test_without_auth")

    @pytest.mark.asyncio
    async def test_query_params(self):
        """쿼리 파라미터 테스트"""
        from bloom.testing import BloomTestCase
        from bloom.web import ASGIApplication, JSONResponse

        app = ASGIApplication()

        @app.get("/api/search")
        async def search(request):
            q = request.query_param("q", "")
            page = int(request.query_param("page", "1"))
            return JSONResponse({"query": q, "page": page})

        class MyTest(BloomTestCase):
            async def test_search(self):
                async with self.test_client(app) as client:
                    response = await client.get(
                        "/api/search",
                        params={"q": "test", "page": "2"},
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["query"] == "test"
                    assert data["page"] == 2

        test = MyTest()
        await test._run_test("test_search")

    @pytest.mark.asyncio
    async def test_all_http_methods(self):
        """모든 HTTP 메서드 테스트"""
        from bloom.testing import BloomTestCase
        from bloom.web import ASGIApplication, JSONResponse

        app = ASGIApplication()

        @app.get("/api/resource")
        async def get_resource(request):
            return JSONResponse({"method": "GET"})

        @app.post("/api/resource")
        async def post_resource(request):
            return JSONResponse({"method": "POST"})

        @app.put("/api/resource")
        async def put_resource(request):
            return JSONResponse({"method": "PUT"})

        @app.patch("/api/resource")
        async def patch_resource(request):
            return JSONResponse({"method": "PATCH"})

        @app.delete("/api/resource")
        async def delete_resource(request):
            return JSONResponse({"method": "DELETE"})

        class MyTest(BloomTestCase):
            async def test_methods(self):
                async with self.test_client(app) as client:
                    assert (await client.get("/api/resource")).json()["method"] == "GET"
                    assert (await client.post("/api/resource")).json()[
                        "method"
                    ] == "POST"
                    assert (await client.put("/api/resource")).json()["method"] == "PUT"
                    assert (await client.patch("/api/resource")).json()[
                        "method"
                    ] == "PATCH"
                    assert (await client.delete("/api/resource")).json()[
                        "method"
                    ] == "DELETE"

        test = MyTest()
        await test._run_test("test_methods")


# =============================================================================
# Test: TestClient - WebSocket
# =============================================================================


class TestWebSocketClient:
    """TestClient WebSocket 테스트"""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="ASGIApplication WebSocket support not yet implemented")
    async def test_websocket_connect(self):
        """WebSocket 연결 테스트"""
        from bloom.testing import BloomTestCase
        from bloom.web import ASGIApplication

        app = ASGIApplication()

        # WebSocket 핸들러 등록 (간단한 에코)
        @app.websocket("/ws")
        async def websocket_handler(websocket):
            await websocket.accept()
            data = await websocket.receive_text()
            await websocket.send_text(f"Echo: {data}")
            await websocket.close()

        class MyTest(BloomTestCase):
            async def test_ws_echo(self):
                async with self.test_client(app) as client:
                    async with client.websocket("/ws") as ws:
                        await ws.send_text("Hello")
                        response = await ws.receive_text()
                        assert response == "Echo: Hello"

        test = MyTest()
        await test._run_test("test_ws_echo")

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="ASGIApplication WebSocket support not yet implemented")
    async def test_websocket_json(self):
        """WebSocket JSON 메시지 테스트"""
        from bloom.testing import BloomTestCase
        from bloom.web import ASGIApplication

        app = ASGIApplication()

        @app.websocket("/ws/json")
        async def ws_json_handler(websocket):
            await websocket.accept()
            data = await websocket.receive_json()
            await websocket.send_json({"received": data, "status": "ok"})
            await websocket.close()

        class MyTest(BloomTestCase):
            async def test_ws_json(self):
                async with self.test_client(app) as client:
                    async with client.websocket("/ws/json") as ws:
                        await ws.send_json({"message": "test"})
                        response = await ws.receive_json()
                        assert response["status"] == "ok"
                        assert response["received"]["message"] == "test"

        test = MyTest()
        await test._run_test("test_ws_json")


# =============================================================================
# Test: TestClient - STOMP
# =============================================================================


class TestSTOMPClient:
    """TestClient STOMP 프로토콜 테스트"""

    @pytest.mark.asyncio
    async def test_stomp_connect_subscribe_send(self):
        """STOMP 연결, 구독, 전송 테스트"""
        from bloom.testing import BloomTestCase

        class MyTest(BloomTestCase):
            async def test_stomp_basic(self):
                # STOMP 클라이언트 테스트 (메시지 브로커 연결)
                async with self.stomp_client("ws://localhost:8080/stomp") as stomp:
                    # 연결
                    await stomp.connect()

                    # 구독
                    messages = []

                    async def on_message(frame):
                        messages.append(frame)

                    await stomp.subscribe("/topic/test", on_message)

                    # 메시지 전송
                    await stomp.send("/app/test", {"data": "hello"})

                    # 메시지 수신 대기 (타임아웃 포함)
                    await stomp.wait_for_message(timeout=1.0)

                    assert len(messages) > 0

        # 실제 STOMP 서버가 없으므로 skip
        pytest.skip("STOMP server not available")

    @pytest.mark.asyncio
    async def test_stomp_mock(self):
        """STOMP Mock 테스트"""
        from bloom.testing import BloomTestCase, MockSTOMP

        class MyTest(BloomTestCase):
            async def test_stomp_mock(self):
                # Mock STOMP 클라이언트
                stomp = MockSTOMP()

                # 연결 시뮬레이션
                await stomp.connect()
                assert stomp.connected

                # 구독 시뮬레이션
                received = []
                await stomp.subscribe("/topic/test", lambda f: received.append(f))

                # 메시지 수신 시뮬레이션
                stomp.simulate_message("/topic/test", {"data": "test"})

                assert len(received) == 1
                assert received[0]["data"] == "test"

        test = MyTest()
        await test._run_test("test_stomp_mock")


# =============================================================================
# Test: Fixtures Integration
# =============================================================================


class TestFixturesIntegration:
    """pytest 픽스처 통합 테스트"""

    @pytest.mark.asyncio
    async def test_fixture_injection(self):
        """픽스처를 통한 의존성 주입"""
        from bloom.testing import BloomTestCase, fixture

        @Service
        class DatabaseService:
            def query(self) -> list:
                return []

        class MyTest(BloomTestCase):
            @fixture
            async def db_service(self) -> DatabaseService:
                """테스트용 DB 서비스 픽스처"""
                return await self.get_instance(DatabaseService)

            async def test_with_fixture(self, db_service: DatabaseService):
                result = db_service.query()
                assert isinstance(result, list)

        test = MyTest()
        await test._run_test("test_with_fixture")

    @pytest.mark.asyncio
    async def test_autouse_fixture(self):
        """autouse 픽스처 테스트"""
        from bloom.testing import BloomTestCase, fixture

        class MyTest(BloomTestCase):
            data: list = []

            @fixture(autouse=True)
            async def setup_data(self):
                """매 테스트 전 데이터 초기화"""
                self.data = [1, 2, 3]
                yield
                self.data = []

            async def test_data_exists(self):
                assert self.data == [1, 2, 3]

        test = MyTest()
        await test._run_test("test_data_exists")


# =============================================================================
# Test: 통합 시나리오
# =============================================================================


class TestIntegrationScenario:
    """통합 시나리오 테스트"""

    @pytest.mark.asyncio
    async def test_full_scenario(self):
        """MockBean + TestClient 통합 테스트"""
        from bloom.testing import BloomTestCase, MockBean
        from bloom.web import ASGIApplication, JSONResponse

        @Repository
        class UserRepository:
            def find_all(self) -> list:
                return []  # 실제로는 DB 조회

            def save(self, user: dict) -> dict:
                return user  # 실제로는 DB 저장

        @Service
        class UserService:
            repo: UserRepository

            def get_users(self) -> list:
                return self.repo.find_all()

            def create_user(self, name: str) -> dict:
                return self.repo.save({"name": name})

        # 컨트롤러 역할의 라우트
        app = ASGIApplication()

        class MyTest(BloomTestCase):
            repo: MockBean[UserRepository]

            async def setUp(self):
                await super().setUp()
                # Mock 설정
                self.repo.find_all.return_value = [
                    {"id": 1, "name": "User 1"},
                    {"id": 2, "name": "User 2"},
                ]

            async def test_integration(self):
                # 서비스 레이어 테스트
                service = await self.get_instance(UserService)
                users = service.get_users()

                assert len(users) == 2
                assert users[0]["name"] == "User 1"
                self.repo.find_all.assert_called_once()

        test = MyTest()
        await test._run_test("test_integration")
