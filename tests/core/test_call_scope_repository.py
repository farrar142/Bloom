"""CALL 스코프 Repository 의존성 테스트

Controller → Service → Repository → AsyncSession 체인에서
CALL 스코프 의존성이 제대로 주입되는지 테스트합니다.
"""

import pytest
import asyncio
from dataclasses import dataclass
from typing import Any

from bloom import Application
from bloom.core import (
    Component,
    Service,
    Configuration,
    Factory,
    PostConstruct,
    get_container_manager,
    reset_container_manager,
)
from bloom.core.scope import ScopeEnum
from bloom.core.manager import ContainerManager
from bloom.core.proxy import LazyProxy, AsyncProxy
from bloom.core.decorators import register_factories_from_configuration
from bloom.web import Controller, GetMapping, PostMapping, RequestMapping, JSONResponse


# =============================================================================
# Mock Components (Repository 패턴 시뮬레이션)
# =============================================================================


@dataclass
class MockAsyncSession:
    """AsyncSession 시뮬레이션"""

    id: int

    @property
    def dialect(self):
        return MockDialect()


class MockDialect:
    def select_sql(self, meta, where=None):
        return f"SELECT * FROM table WHERE {where}"


# =============================================================================
# Tests
# =============================================================================


class TestCallScopeRepositoryChain:
    """Controller → Service → Repository → AsyncSession 체인 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        """테스트 전후 컨테이너 초기화"""
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_repository_async_session_injection(self):
        """Repository에 AsyncSession이 제대로 주입되는지 확인"""

        # CALL 스코프로 AsyncSession 팩토리 등록
        @Configuration
        class TestDatabaseConfig:
            _session_counter: int = 0

            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                """매 CALL마다 새 세션 생성"""
                TestDatabaseConfig._session_counter += 1
                return MockAsyncSession(id=TestDatabaseConfig._session_counter)

        # Repository - AsyncSession 의존성 (AsyncProxy로 선언 필수)
        @Component
        class TestUserRepository:
            async_session: AsyncProxy[MockAsyncSession]  # CALL 스코프 async factory

            async def find_by_email(self, email: str) -> dict | None:
                # AsyncProxy는 await resolve()로 인스턴스 접근
                session = await self.async_session.resolve()
                sql = session.dialect.select_sql(
                    None, where=f"email='{email}'"
                )
                return {"email": email, "sql": sql}

        manager = get_container_manager()
        scope_manager = manager.scope_manager

        # Factory 메서드를 컨테이너에 등록
        register_factories_from_configuration(TestDatabaseConfig, manager)

        # CALL 스코프 시작
        frame_id = scope_manager.start_call()

        try:
            # Repository 인스턴스 가져오기
            repo = await manager.get_instance_async(TestUserRepository)

            # CALL 스코프 async factory는 AsyncProxy로 주입됨
            async_session_field = vars(repo).get("async_session")
            print(f"async_session field type: {type(async_session_field)}")
            assert isinstance(
                async_session_field, AsyncProxy
            ), "async_session should be AsyncProxy"

            # find_by_email 호출 시 await resolve()로 접근
            result = await repo.find_by_email("test@example.com")

            print(f"Result: {result}")
            assert result is not None
            assert "email" in result
            assert "sql" in result
        finally:
            await scope_manager.end_call(frame_id)

    @pytest.mark.asyncio
    async def test_service_to_repository_chain(self):
        """Service → Repository 체인에서 AsyncSession 접근"""

        @Configuration
        class TestDatabaseConfig2:
            _session_counter: int = 0

            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                TestDatabaseConfig2._session_counter += 1
                return MockAsyncSession(id=TestDatabaseConfig2._session_counter)

        @Component
        class TestUserRepository2:
            async_session: AsyncProxy[MockAsyncSession]

            async def find_by_email(self, email: str) -> dict | None:
                session = await self.async_session.resolve()
                sql = session.dialect.select_sql(
                    None, where=f"email='{email}'"
                )
                return {"email": email, "sql": sql}

        @Service
        class TestUserService2:
            user_repo: TestUserRepository2

            async def get_user_by_email(self, email: str) -> dict | None:
                return await self.user_repo.find_by_email(email)

        manager = get_container_manager()
        scope_manager = manager.scope_manager

        # Factory 메서드를 컨테이너에 등록
        register_factories_from_configuration(TestDatabaseConfig2, manager)

        # CALL 스코프 컨텍스트 내에서 SINGLETON들을 미리 초기화
        frame_id = scope_manager.start_call()

        try:
            # 의존성 체인의 모든 SINGLETON을 미리 생성 (ScopeManager 캐싱)
            # Repository → Service 순서로 생성
            await manager.get_instance_async(TestUserRepository2)
            service = await manager.get_instance_async(TestUserService2)

            # 이제 Service 메서드 호출 시 LazyProxy가 캐시된 Repository를 반환
            result = await service.get_user_by_email("test@example.com")

            print(f"Service result: {result}")
            assert result is not None
            assert "email" in result
        finally:
            await scope_manager.end_call(frame_id)

    @pytest.mark.asyncio
    async def test_controller_full_chain(self):
        """Controller → Service → Repository → AsyncSession 전체 체인"""

        @Configuration
        class TestDatabaseConfig3:
            _session_counter: int = 0

            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                TestDatabaseConfig3._session_counter += 1
                return MockAsyncSession(id=TestDatabaseConfig3._session_counter)

        @Component
        class TestUserRepository3:
            async_session: AsyncProxy[MockAsyncSession]

            async def find_by_email(self, email: str) -> dict | None:
                session = await self.async_session.resolve()
                sql = session.dialect.select_sql(
                    None, where=f"email='{email}'"
                )
                return {"email": email, "sql": sql}

        @Service
        class TestUserService3:
            user_repo: TestUserRepository3

            async def get_user_by_email(self, email: str) -> dict | None:
                return await self.user_repo.find_by_email(email)

        @Component
        class TestUserController3:
            user_service: TestUserService3

            async def get_user(self, email: str) -> dict:
                user = await self.user_service.get_user_by_email(email)
                return user or {"error": "not found"}

        manager = get_container_manager()
        scope_manager = manager.scope_manager

        # Factory 메서드를 컨테이너에 등록
        register_factories_from_configuration(TestDatabaseConfig3, manager)

        frame_id = scope_manager.start_call()

        try:
            # 의존성 체인의 모든 SINGLETON을 미리 생성 (의존성 순서대로)
            await manager.get_instance_async(TestUserRepository3)
            await manager.get_instance_async(TestUserService3)
            controller = await manager.get_instance_async(TestUserController3)

            result = await controller.get_user("test@example.com")

            print(f"Controller result: {result}")
            assert result is not None
            assert "email" in result
        finally:
            await scope_manager.end_call(frame_id)

    @pytest.mark.asyncio
    async def test_call_scope_creates_new_session_per_call(self):
        """각 CALL마다 새 AsyncSession이 생성되는지 확인"""

        @Configuration
        class TestDatabaseConfig4:
            _session_counter: int = 0

            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                TestDatabaseConfig4._session_counter += 1
                return MockAsyncSession(id=TestDatabaseConfig4._session_counter)

        manager = get_container_manager()
        scope_manager = manager.scope_manager

        # Factory 메서드를 컨테이너에 등록
        register_factories_from_configuration(TestDatabaseConfig4, manager)

        # 첫 번째 CALL
        frame_id1 = scope_manager.start_call()
        try:
            session1 = await manager.get_instance_async(MockAsyncSession)
            session1_id = session1.id
        finally:
            await scope_manager.end_call(frame_id1)

        # 두 번째 CALL
        frame_id2 = scope_manager.start_call()
        try:
            session2 = await manager.get_instance_async(MockAsyncSession)
            session2_id = session2.id
        finally:
            await scope_manager.end_call(frame_id2)

        # 서로 다른 세션이어야 함
        print(f"Session 1 ID: {session1_id}, Session 2 ID: {session2_id}")
        assert session1_id != session2_id

    @pytest.mark.asyncio
    async def test_call_scope_async_proxy_chain(self):
        """AsyncProxy를 통한 CALL 스코프 의존성 체인 테스트
        
        Controller → Service → Repository → AsyncSession 체인에서
        AsyncProxy로 선언된 CALL 스코프 의존성이 제대로 동작하는지 확인합니다.
        """

        @Configuration
        class TestDatabaseConfig5:
            _session_counter: int = 0

            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                TestDatabaseConfig5._session_counter += 1
                return MockAsyncSession(id=TestDatabaseConfig5._session_counter)

        @Component
        class TestUserRepository5:
            async_session: AsyncProxy[MockAsyncSession]

            async def find_by_email(self, email: str) -> dict | None:
                session = await self.async_session.resolve()
                sql = session.dialect.select_sql(
                    None, where=f"email='{email}'"
                )
                return {"email": email, "sql": sql}

        @Service
        class TestUserService5:
            user_repo: TestUserRepository5

            async def get_user_by_email(self, email: str) -> dict | None:
                return await self.user_repo.find_by_email(email)

        @Component
        class TestUserController5:
            user_service: TestUserService5

            async def get_user(self, email: str) -> dict:
                user = await self.user_service.get_user_by_email(email)
                return user or {"error": "not found"}

        manager = get_container_manager()
        scope_manager = manager.scope_manager

        # Factory 메서드를 컨테이너에 등록
        register_factories_from_configuration(TestDatabaseConfig5, manager)

        # CALL 컨텍스트 시작
        frame_id = scope_manager.start_call()

        try:
            # 의존성 체인의 모든 컴포넌트 생성
            await manager.get_instance_async(TestUserRepository5)
            await manager.get_instance_async(TestUserService5)
            controller = await manager.get_instance_async(TestUserController5)

            # 메서드 호출 - AsyncProxy.resolve() 시점에 CALL 스코프 의존성 생성
            result = await controller.get_user("test@example.com")

            print(f"Result: {result}")
            assert result is not None
            assert "email" in result

            # async_session이 생성되었는지 확인
            session = scope_manager.get_call_scoped(MockAsyncSession)
            assert session is not None
            print(f"Session ID: {session.id}")
        finally:
            await scope_manager.end_call(frame_id)


class TestCallScopeWithASGI:
    """실제 ASGI 요청을 통한 CALL 스코프 테스트

    Application.asgi를 통해 HTTP 요청을 보내고,
    Controller → Service → Repository → AsyncSession 체인에서
    CALL 스코프 의존성이 제대로 주입되는지 확인합니다.
    """

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        """테스트 전후 컨테이너 초기화"""
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_http_request_with_call_scope_dependency(self):
        """HTTP 요청 시 CALL 스코프 의존성이 제대로 주입되는지 테스트"""
        import httpx

        # 세션 생성 카운터 (각 요청마다 새 세션이 생성되어야 함)
        session_ids: list[int] = []

        @Configuration
        class ASGITestDatabaseConfig:
            _session_counter: int = 0

            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                ASGITestDatabaseConfig._session_counter += 1
                session = MockAsyncSession(id=ASGITestDatabaseConfig._session_counter)
                session_ids.append(session.id)
                return session

        @Component
        class ASGITestUserRepository:
            async_session: AsyncProxy[MockAsyncSession]

            async def find_by_email(self, email: str) -> dict | None:
                # AsyncProxy는 await resolve()로 인스턴스 접근
                session = await self.async_session.resolve()
                sql = session.dialect.select_sql(
                    None, where=f"email='{email}'"
                )
                return {"email": email, "sql": sql, "session_id": session.id}

        @Service
        class ASGITestUserService:
            user_repo: ASGITestUserRepository

            async def get_user_by_email(self, email: str) -> dict | None:
                return await self.user_repo.find_by_email(email)

        @Controller
        @RequestMapping("/api/test-users")
        class ASGITestUserController:
            user_service: ASGITestUserService

            @GetMapping("/{email}")
            async def get_user(self, email: str) -> JSONResponse:
                user = await self.user_service.get_user_by_email(email)
                return JSONResponse(user or {"error": "not found"})

        # Application 생성 및 설정
        app = Application("asgi-test-app")
        app.scan(ASGITestDatabaseConfig)
        app.scan(ASGITestUserRepository)
        app.scan(ASGITestUserService)
        app.scan(ASGITestUserController)
        await app.ready_async()

        # httpx로 ASGI 테스트
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi), base_url="http://test"
        ) as client:
            # 첫 번째 요청
            response1 = await client.get("/api/test-users/user1@example.com")
            if response1.status_code != 200:
                print("Response1 Error:", response1.text)
            assert (
                response1.status_code == 200
            ), f"Expected 200, got {response1.status_code}: {response1.text}"
            data1 = response1.json()
            assert data1["email"] == "user1@example.com"
            session1_id = data1["session_id"]

            # 두 번째 요청
            response2 = await client.get("/api/test-users/user2@example.com")
            assert response2.status_code == 200
            data2 = response2.json()
            assert data2["email"] == "user2@example.com"
            session2_id = data2["session_id"]

            # 각 요청마다 새 세션이 생성되어야 함 (CALL 스코프)
            print(f"Session IDs: {session_ids}")
            print(f"Request 1 session: {session1_id}, Request 2 session: {session2_id}")
            assert (
                session1_id != session2_id
            ), "Each request should have a different session"

        await app.shutdown_async()

    @pytest.mark.asyncio
    async def test_multiple_requests_isolation(self):
        """여러 HTTP 요청 간 CALL 스코프 격리 테스트"""
        import httpx

        request_sessions: dict[str, int] = {}

        @Configuration
        class IsolationTestConfig:
            _session_counter: int = 0

            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                IsolationTestConfig._session_counter += 1
                return MockAsyncSession(id=IsolationTestConfig._session_counter)

        @Component
        class IsolationTestRepository:
            async_session: AsyncProxy[MockAsyncSession]

            async def get_session_id(self) -> int:
                session = await self.async_session.resolve()
                return session.id

        @Service
        class IsolationTestService:
            repo: IsolationTestRepository

            async def get_session_info(self, request_id: str) -> dict:
                session_id = await self.repo.get_session_id()
                request_sessions[request_id] = session_id
                return {"request_id": request_id, "session_id": session_id}

        @Controller
        @RequestMapping("/api/isolation-test")
        class IsolationTestController:
            service: IsolationTestService

            @GetMapping("/{request_id}")
            async def get_info(self, request_id: str) -> JSONResponse:
                info = await self.service.get_session_info(request_id)
                return JSONResponse(info)

        app = Application("isolation-test-app")
        app.scan(IsolationTestConfig)
        app.scan(IsolationTestRepository)
        app.scan(IsolationTestService)
        app.scan(IsolationTestController)
        await app.ready_async()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi), base_url="http://test"
        ) as client:
            # 여러 요청 동시 실행
            responses = await asyncio.gather(
                client.get("/api/isolation-test/req1"),
                client.get("/api/isolation-test/req2"),
                client.get("/api/isolation-test/req3"),
            )

            for resp in responses:
                assert resp.status_code == 200, f"Request failed: {resp.text}"

            # 모든 세션 ID가 다르면 격리가 잘 되는 것
            session_id_set = set(request_sessions.values())
            print(f"Request sessions: {request_sessions}")
            assert (
                len(session_id_set) == 3
            ), f"Expected 3 unique sessions, got {len(session_id_set)}"

        await app.shutdown_async()

    @pytest.mark.asyncio
    async def test_post_request_with_call_scope(self):
        """POST 요청에서도 CALL 스코프가 동작하는지 테스트"""
        import httpx
        from bloom.web import RequestBody
        from dataclasses import dataclass as dc

        created_sessions: list[int] = []

        @Configuration
        class PostTestConfig:
            _session_counter: int = 0

            @Factory(scope=ScopeEnum.CALL)
            async def async_session(self) -> MockAsyncSession:
                PostTestConfig._session_counter += 1
                session = MockAsyncSession(id=PostTestConfig._session_counter)
                created_sessions.append(session.id)
                return session

        @dc
        class CreateUserRequest:
            name: str
            email: str

        @Component
        class PostTestRepository:
            async_session: AsyncProxy[MockAsyncSession]

            async def create(self, name: str, email: str) -> dict:
                session = await self.async_session.resolve()
                return {
                    "name": name,
                    "email": email,
                    "session_id": session.id,
                }

        @Service
        class PostTestService:
            repo: PostTestRepository

            async def create_user(self, name: str, email: str) -> dict:
                return await self.repo.create(name, email)

        @Controller
        @RequestMapping("/api/post-test")
        class PostTestController:
            service: PostTestService

            @PostMapping
            async def create_user(
                self, body: RequestBody[CreateUserRequest]
            ) -> JSONResponse:
                user = await self.service.create_user(body.name, body.email)
                return JSONResponse(user, status_code=201)

        app = Application("post-test-app")
        app.scan(PostTestConfig)
        app.scan(PostTestRepository)
        app.scan(PostTestService)
        app.scan(PostTestController)
        await app.ready_async()

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app.asgi), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/post-test",
                json={"name": "Test User", "email": "test@example.com"},
            )

            if response.status_code != 201:
                print("Response Error:", response.text)
            assert (
                response.status_code == 201
            ), f"Expected 201, got {response.status_code}: {response.text}"

            data = response.json()
            assert data["name"] == "Test User"
            assert data["email"] == "test@example.com"
            assert "session_id" in data

        await app.shutdown_async()
