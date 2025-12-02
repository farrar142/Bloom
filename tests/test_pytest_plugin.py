"""pytest 기반 테스팅 모듈 테스트"""

import pytest
from dataclasses import dataclass

from bloom import Application, Component
from bloom.web import Controller, Get, Post
from bloom.web.http import HttpResponse
from bloom.web.params.types import RequestBody
from bloom.core.exceptions import NotFoundError
from bloom.tests import (
    BloomTestClient,
    AssertableResponse,
    assert_instance,
    assert_injected_field,
    assert_container_exists,
    create_test_app,
)


# =============================================================================
# 테스트용 컴포넌트
# =============================================================================


@dataclass
class CreateUserRequest:
    name: str
    email: str


@Component
class UserRepository:
    """테스트용 Repository"""

    def get_users(self) -> list[dict]:
        return [
            {"id": 1, "name": "Alice", "email": "alice@example.com"},
            {"id": 2, "name": "Bob", "email": "bob@example.com"},
        ]

    def get_user(self, user_id: int) -> dict | None:
        users = {u["id"]: u for u in self.get_users()}
        return users.get(user_id)

    def create_user(self, name: str, email: str) -> dict:
        return {"id": 3, "name": name, "email": email}


@Component
class UserService:
    """테스트용 Service"""

    repository: UserRepository

    def get_all_users(self) -> list[dict]:
        return self.repository.get_users()

    def get_user_by_id(self, user_id: int) -> dict | None:
        return self.repository.get_user(user_id)

    def create_user(self, name: str, email: str) -> dict:
        return self.repository.create_user(name, email)


@Controller
class UserController:
    """테스트용 Controller"""

    service: UserService

    @Get("/api/users")
    def list_users(self) -> list[dict]:
        return self.service.get_all_users()

    @Get("/api/users/{user_id}")
    def get_user(self, user_id: int) -> dict:
        user = self.service.get_user_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")
        return user

    @Post("/api/users")
    def create_user(self, body: RequestBody[CreateUserRequest]) -> dict:
        return self.service.create_user(body.name, body.email)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def app():
    """테스트용 Application fixture"""
    app = Application("pytest_test")
    app.scan(UserRepository, UserService, UserController)
    await app.ready_async()
    return app


@pytest.fixture
async def client(app):
    """BloomTestClient fixture"""
    async with BloomTestClient(app) as c:
        yield c


# =============================================================================
# BloomTestClient 테스트
# =============================================================================


class TestBloomTestClient:
    """BloomTestClient 기본 기능 테스트"""

    async def test_get_request(self, client: BloomTestClient):
        """GET 요청 테스트"""
        response = await client.get("/api/users")

        assert response.ok
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Alice"

    async def test_post_request(self, client: BloomTestClient):
        """POST 요청 테스트"""
        response = await client.post(
            "/api/users", json_body={"name": "Charlie", "email": "charlie@example.com"}
        )

        assert response.ok
        data = response.json()
        assert data["name"] == "Charlie"
        assert data["email"] == "charlie@example.com"

    async def test_not_found(self, client: BloomTestClient):
        """404 응답 테스트"""
        response = await client.get("/api/users/999")

        assert response.status_code == 404
        assert response.is_client_error

    async def test_get_instance(self, client: BloomTestClient):
        """컨테이너 인스턴스 조회"""
        service = client.get_instance(UserService)

        assert service is not None
        assert isinstance(service, UserService)

    async def test_set_header(self, app):
        """헤더 설정 테스트"""
        async with BloomTestClient(app) as client:
            client.set_header("X-Custom", "test-value")
            # 헤더가 설정되었는지 확인
            assert client._client.default_headers["X-Custom"] == "test-value"

    async def test_set_auth(self, app):
        """Authorization 헤더 설정 테스트"""
        async with BloomTestClient(app) as client:
            client.set_auth("my-token")
            assert client._client.default_headers["Authorization"] == "Bearer my-token"

            client.set_auth("api-key", scheme="ApiKey")
            assert client._client.default_headers["Authorization"] == "ApiKey api-key"


# =============================================================================
# AssertableResponse 테스트
# =============================================================================


class TestAssertableResponse:
    """AssertableResponse 체이닝 테스트"""

    async def test_chained_assertions(self, client: BloomTestClient):
        """체이닝 assertion 테스트"""
        (await client.get("/api/users")).assert_ok().assert_json_content_type()

    async def test_assert_status(self, client: BloomTestClient):
        """상태 코드 assertion"""
        (await client.get("/api/users")).assert_status(200)
        (await client.get("/api/users/999")).assert_status(404)

    async def test_assert_ok(self, client: BloomTestClient):
        """2xx assertion"""
        (await client.get("/api/users")).assert_ok()

    async def test_assert_not_found(self, client: BloomTestClient):
        """404 assertion"""
        (await client.get("/api/users/999")).assert_not_found()

    async def test_assert_json(self, client: BloomTestClient):
        """JSON 전체 비교"""
        response = await client.get("/api/users")
        response.assert_json(
            [
                {"id": 1, "name": "Alice", "email": "alice@example.com"},
                {"id": 2, "name": "Bob", "email": "bob@example.com"},
            ]
        )

    async def test_assert_json_path(self, client: BloomTestClient):
        """JSON 경로 검증"""
        response = await client.get("/api/users/1")
        response.assert_json_path("name", "Alice")
        response.assert_json_path("email", "alice@example.com")

    async def test_assert_json_has_key(self, client: BloomTestClient):
        """JSON 키 존재 검증"""
        (await client.get("/api/users/1")).assert_json_has_key(
            "name"
        ).assert_json_has_key("email")

    async def test_assert_json_has_keys(self, client: BloomTestClient):
        """JSON 복수 키 존재 검증"""
        (await client.get("/api/users/1")).assert_json_has_keys("id", "name", "email")

    async def test_assert_json_length(self, client: BloomTestClient):
        """JSON 배열 길이 검증"""
        (await client.get("/api/users")).assert_json_length(2)

    async def test_assert_header_contains(self, client: BloomTestClient):
        """헤더 포함 검증"""
        (await client.get("/api/users")).assert_header_contains("content-type", "json")

    async def test_assert_text_contains(self, client: BloomTestClient):
        """텍스트 포함 검증"""
        (await client.get("/api/users")).assert_text_contains("Alice")

    async def test_failed_assertion_raises(self, client: BloomTestClient):
        """실패한 assertion이 AssertionError를 발생시키는지"""
        with pytest.raises(AssertionError):
            (await client.get("/api/users")).assert_status(404)

        with pytest.raises(AssertionError):
            (await client.get("/api/users")).assert_json([])


# =============================================================================
# Standalone Assertion 함수 테스트
# =============================================================================


class TestAssertionFunctions:
    """독립형 assertion 함수 테스트"""

    async def test_assert_instance(self, app):
        """타입 검증"""
        service = app.manager.get_instance(UserService)
        result = assert_instance(service, UserService)
        assert result is service

    async def test_assert_instance_failure(self, app):
        """타입 검증 실패"""
        service = app.manager.get_instance(UserService)
        with pytest.raises(AssertionError):
            assert_instance(service, UserRepository)

    async def test_assert_injected_field(self, app):
        """필드 주입 검증"""
        service = app.manager.get_instance(UserService)
        repo = assert_injected_field(service, "repository", UserRepository)
        assert isinstance(repo, UserRepository)

    async def test_assert_injected_field_not_found(self, app):
        """필드 없음 검증"""
        service = app.manager.get_instance(UserService)
        with pytest.raises(AssertionError):
            assert_injected_field(service, "nonexistent")

    async def test_assert_container_exists(self):
        """컨테이너 존재 검증"""
        assert_container_exists(UserService)

    async def test_assert_container_not_exists(self):
        """컨테이너 없음 검증"""

        class NotAComponent:
            pass

        with pytest.raises(AssertionError):
            assert_container_exists(NotAComponent)


# =============================================================================
# 복합 시나리오 테스트
# =============================================================================


class TestComplexScenarios:
    """복합 시나리오 테스트"""

    async def test_crud_flow(self, client: BloomTestClient):
        """CRUD 플로우 테스트"""
        # List
        (await client.get("/api/users")).assert_ok().assert_json_length(2)

        # Create
        (
            await client.post(
                "/api/users",
                json_body={"name": "Charlie", "email": "charlie@example.com"},
            )
        ).assert_ok().assert_json_path("name", "Charlie")

        # Read
        (await client.get("/api/users/1")).assert_ok().assert_json_path("name", "Alice")

        # Not Found
        (await client.get("/api/users/999")).assert_not_found()

    async def test_with_custom_headers(self, app):
        """커스텀 헤더와 함께 테스트"""
        async with BloomTestClient(app) as client:
            client.set_header("X-Request-ID", "test-123")
            client.set_header("Accept-Language", "ko-KR")

            response = await client.get("/api/users")
            response.assert_ok()

    async def test_service_injection_chain(self, client: BloomTestClient):
        """서비스 주입 체인 검증"""
        service = client.get_instance(UserService)

        # Service -> Repository 주입 확인
        repo = assert_injected_field(service, "repository", UserRepository)

        # Repository 메서드 호출
        users = repo.get_users()
        assert len(users) == 2
