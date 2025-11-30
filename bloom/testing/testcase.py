"""Django 스타일 TestCase 클래스

Django의 TestCase처럼 모든 테스트 기능을 하나의 클래스에 통합합니다.

사용 예시:
    ```python
    from bloom.testing import TestCase
    from bloom import Component

    @Component
    class UserService:
        def get_users(self) -> list:
            return ["user1", "user2"]

    class TestUserService(TestCase):
        components = [UserService]

        async def test_get_users(self):
            service = self.get_instance(UserService)
            users = service.get_users()
            self.assertEqual(users, ["user1", "user2"])

        async def test_with_mock(self):
            class FakeService:
                def get_users(self):
                    return ["fake"]

            with self.override(UserService, FakeService()):
                service = self.get_instance(UserService)
                self.assertEqual(service.get_users(), ["fake"])
    ```
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Callable, TypeVar, Iterator, TYPE_CHECKING
from unittest import TestCase as UnitTestCase

from .client import TestClient, TestResponse
from .mock import MockContainer, _FactoryWrapper
from ..application import Application
from ..core.manager import ContainerManager, set_current_manager

if TYPE_CHECKING:
    from ..core.container import Container


T = TypeVar("T")


class TestCase(UnitTestCase):
    """
    Bloom 통합 테스트 케이스

    Django의 TestCase처럼 모든 테스트 기능을 하나의 클래스에 제공합니다.

    클래스 속성:
        app_name: Application 이름 (기본: "test")
        components: 스캔할 컴포넌트 리스트
        config: 설정 딕셔너리
        auto_ready: True면 setUp에서 자동으로 ready() 호출

    사용 가능한 메서드:
        - HTTP 테스트: get(), post(), put(), delete(), patch()
        - 인스턴스 조회: get_instance(), get_instances()
        - Mock: override(), override_factory()
        - Assertion: assert_instance_of(), assert_injected(), assert_status()
    """

    # 클래스 레벨 설정
    app_name: str = "test"
    components: list[type] = []
    config: dict[str, Any] | None = None
    auto_ready: bool = True

    # 인스턴스 속성
    app: Application
    manager: ContainerManager
    client: TestClient
    _mock_container: MockContainer
    _loop: asyncio.AbstractEventLoop | None

    def setUp(self) -> None:
        """테스트 설정 - 각 테스트 전에 호출됨"""
        super().setUp()

        # Application 생성
        self.app = Application(self.app_name)
        self.manager = self.app.manager

        # 설정 로드
        if self.config:
            self.app.load_config(self.config, source_type="dict")

        # 컴포넌트 스캔
        for component in self.components:
            self.app.scan(component)

        # ready() 호출
        if self.auto_ready and self.components:
            self.app.ready()

        # TestClient 생성
        self.client = TestClient(self.app)

        # MockContainer 초기화
        self._mock_container = MockContainer()

        # 이벤트 루프
        self._loop = None

    def tearDown(self) -> None:
        """테스트 정리 - 각 테스트 후에 호출됨"""
        super().tearDown()

        # 이벤트 루프 정리
        if self._loop and not self._loop.is_running():
            self._loop.close()

        # ContainerManager 정리
        set_current_manager(None)

    # === 이벤트 루프 ===

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """이벤트 루프 반환"""
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def run_async(self, coro) -> Any:
        """코루틴 동기 실행"""
        return self.loop.run_until_complete(coro)

    # === DI Container 접근 ===

    def get_instance(self, target_type: type[T]) -> T:
        """
        인스턴스 조회

        Args:
            target_type: 조회할 타입

        Returns:
            해당 타입의 인스턴스
        """
        return self.manager.get_instance(target_type)

    def get_instances(self, target_type: type[T]) -> list[T]:
        """
        타입의 모든 인스턴스 조회

        Args:
            target_type: 조회할 타입

        Returns:
            해당 타입의 인스턴스 리스트
        """
        return self.manager.get_instances(target_type)

    def has_instance(self, target_type: type) -> bool:
        """인스턴스 존재 여부 확인"""
        return self.manager.get_instance(target_type, raise_exception=False) is not None

    # === HTTP 테스트 (동기 래퍼) ===

    def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> TestResponse:
        """GET 요청"""
        return self.run_async(
            self.client.get(path, headers=headers, query_params=query_params)
        )

    def post(
        self,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """POST 요청"""
        return self.run_async(
            self.client.post(path, json_body=json, body=body, headers=headers)
        )

    def put(
        self,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """PUT 요청"""
        return self.run_async(
            self.client.put(path, json_body=json, body=body, headers=headers)
        )

    def delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """DELETE 요청"""
        return self.run_async(self.client.delete(path, headers=headers))

    def patch(
        self,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """PATCH 요청"""
        return self.run_async(
            self.client.patch(path, json_body=json, body=body, headers=headers)
        )

    # === Mock ===

    @contextmanager
    def override(self, target_type: type[T], instance: T) -> Iterator[T]:
        """
        의존성 오버라이드

        Usage:
            with self.override(UserRepository, FakeRepository()) as fake:
                # fake가 주입됨
                pass
        """
        self._mock_container.override(target_type, instance)
        with self._mock_container.apply(self.manager):
            yield instance
        self._mock_container.remove(target_type)

    @contextmanager
    def override_factory(
        self, target_type: type[T], factory: Callable[..., T]
    ) -> Iterator[None]:
        """
        팩토리 오버라이드

        Usage:
            with self.override_factory(UserRepository, lambda: FakeRepository()):
                pass
        """
        self._mock_container.override_factory(target_type, factory)
        with self._mock_container.apply(self.manager):
            yield
        self._mock_container.remove(target_type)

    # === 추가 Assertion 메서드 ===

    def assert_instance_of(self, obj: Any, expected_type: type) -> None:
        """타입 검증"""
        self.assertIsInstance(
            obj,
            expected_type,
            f"Expected {expected_type.__name__}, got {type(obj).__name__}",
        )

    def assert_injected(
        self, obj: Any, field_name: str, expected_type: type | None = None
    ) -> Any:
        """
        필드 주입 검증

        Returns:
            주입된 필드 값
        """
        self.assertTrue(
            hasattr(obj, field_name),
            f"Field '{field_name}' not found in {type(obj).__name__}",
        )
        value = getattr(obj, field_name)
        self.assertIsNotNone(value, f"Field '{field_name}' is None (not injected)")

        if expected_type:
            self.assertIsInstance(value, expected_type)

        return value

    def assert_status(self, response: TestResponse, expected_status: int) -> None:
        """HTTP 상태 코드 검증"""
        self.assertEqual(
            response.status_code,
            expected_status,
            f"Expected status {expected_status}, got {response.status_code}",
        )

    def assert_json_equal(self, response: TestResponse, expected: Any) -> None:
        """JSON 응답 검증"""
        self.assertEqual(response.json(), expected)

    def assert_success(self, response: TestResponse) -> None:
        """2xx 상태 코드 검증"""
        self.assertTrue(
            response.is_success, f"Expected success (2xx), got {response.status_code}"
        )

    def assert_not_found(self, response: TestResponse) -> None:
        """404 상태 코드 검증"""
        self.assert_status(response, 404)

    def assert_bad_request(self, response: TestResponse) -> None:
        """400 상태 코드 검증"""
        self.assert_status(response, 400)

    def assert_unauthorized(self, response: TestResponse) -> None:
        """401 상태 코드 검증"""
        self.assert_status(response, 401)

    def assert_forbidden(self, response: TestResponse) -> None:
        """403 상태 코드 검증"""
        self.assert_status(response, 403)

    # === 유틸리티 ===

    def print_container_tree(self) -> str:
        """컨테이너 트리 출력 (디버깅용)"""
        from .utils import print_container_tree

        return print_container_tree(self.manager)

    def get_container_info(self, target: type) -> dict[str, Any]:
        """컨테이너 정보 조회 (디버깅용)"""
        from .utils import get_container_info

        return get_container_info(target)


class AsyncTestCase(TestCase):
    """
    비동기 테스트 케이스

    pytest-asyncio와 함께 사용하거나, run_async로 동기 실행 가능합니다.

    Usage:
        class TestMyService(AsyncTestCase):
            components = [MyService]

            async def test_async_method(self):
                service = self.get_instance(MyService)
                result = await service.async_method()
                self.assertEqual(result, "expected")
    """

    async def async_get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> TestResponse:
        """비동기 GET 요청"""
        return await self.client.get(path, headers=headers, query_params=query_params)

    async def async_post(
        self,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """비동기 POST 요청"""
        return await self.client.post(path, json_body=json, body=body, headers=headers)

    async def async_put(
        self,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """비동기 PUT 요청"""
        return await self.client.put(path, json_body=json, body=body, headers=headers)

    async def async_delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """비동기 DELETE 요청"""
        return await self.client.delete(path, headers=headers)

    async def async_patch(
        self,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> TestResponse:
        """비동기 PATCH 요청"""
        return await self.client.patch(path, json_body=json, body=body, headers=headers)
