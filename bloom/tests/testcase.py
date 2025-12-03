"""Bloom pytest 기반 테스트 모듈

클래스 기반의 pytest 테스트를 지원합니다.
unittest.TestCase를 상속하지 않고 순수 pytest 스타일로 동작합니다.

Usage:
    from bloom.tests import BloomTestCase
    from bloom import Component

    @Component
    class UserService:
        def get_users(self):
            return ["user1", "user2"]

    class TestUserService(BloomTestCase):
        components = [UserService]

        async def test_get_users(self):
            service = self.get_instance(UserService)
            assert service.get_users() == ["user1", "user2"]

        async def test_with_mock(self):
            class FakeService:
                def get_users(self):
                    return ["fake"]

            with self.override(UserService, FakeService()):
                service = self.get_instance(UserService)
                assert service.get_users() == ["fake"]

        async def test_http(self):
            response = await self.get("/api/users")
            assert response.ok
            response.assert_json(["user1", "user2"])
"""

from __future__ import annotations

import pytest
from typing import TYPE_CHECKING, Any, TypeVar, Iterator, Callable
from contextlib import contextmanager

if TYPE_CHECKING:
    from bloom.application import Application
    from bloom.core.manager import ContainerManager

T = TypeVar("T")


class BloomTestCase:
    """pytest 기반 Bloom 테스트 케이스

    클래스 속성을 통해 테스트 환경을 설정하고,
    pytest의 fixture 시스템과 연동하여 자동으로 Application을 초기화합니다.

    클래스 속성:
        components: 스캔할 컴포넌트 리스트
        app_name: Application 이름 (기본: "test")
        config: 설정 딕셔너리

    자동 제공되는 속성:
        app: Application 인스턴스
        manager: ContainerManager
        client: BloomTestClient (HTTP 테스트용)

    사용 예시:
        class TestMyService(BloomTestCase):
            components = [MyService, MyRepository]
            config = {"database.url": "sqlite:///:memory:"}

            async def test_something(self):
                service = self.get_instance(MyService)
                assert service is not None

            async def test_http(self):
                response = await self.get("/api/data")
                response.assert_ok()
    """

    # pytest가 이 클래스를 테스트로 수집하지 않도록
    __test__ = False

    # 클래스 레벨 설정 (서브클래스에서 오버라이드)
    components: list[type] = []
    app_name: str = "test"
    config: dict[str, Any] | None = None

    # 인스턴스 속성 (setup_method에서 초기화)
    app: "Application"
    manager: "ContainerManager"
    _client: "BloomTestClient | None"
    _mock_container: "MockContainer"

    def __init_subclass__(cls, **kwargs):
        """서브클래스 생성 시 __test__ = True로 설정"""
        super().__init_subclass__(**kwargs)
        # 서브클래스는 테스트로 수집되어야 함
        cls.__test__ = True

    @pytest.fixture(autouse=True)
    async def _setup_bloom(self):
        """pytest fixture - 각 테스트 전에 자동 실행"""
        from bloom.application import Application
        from .mock import MockContainer

        # Application 생성
        self.app = Application(self.app_name)
        self.manager = self.app.manager

        # 설정 로드
        if self.config:
            self.app.load_config(self.config, source_type="dict")

        # 컴포넌트 스캔
        for component in self.components:
            self.app.scan(component)

        # ready_async 호출
        if self.components:
            await self.app.ready_async()

        # Mock 컨테이너 초기화
        self._mock_container = MockContainer()
        self._client = None

        yield

        # 테스트 후 정리
        try:
            await self.app.shutdown_async()
        except Exception:
            pass

    # =========================================================================
    # Container 접근
    # =========================================================================

    def get_instance(self, type_: type[T], raise_exception: bool = True) -> T:
        """컨테이너에서 인스턴스 조회

        Args:
            type_: 조회할 타입
            raise_exception: 없을 때 예외 발생 여부

        Returns:
            인스턴스
        """
        return self.manager.get_instance(
            type_, raise_exception=raise_exception
        )  # type:ignore

    def get_instances(self, type_: type[T]) -> list[T]:
        """컨테이너에서 해당 타입의 모든 인스턴스 조회"""
        return self.manager.get_instances(type_)

    def has_instance(self, type_: type) -> bool:
        """인스턴스 존재 여부 확인"""
        return self.get_instance(type_, raise_exception=False) is not None

    # =========================================================================
    # Mock / Override
    # =========================================================================

    @contextmanager
    def override(self, type_: type[T], instance: T) -> Iterator[T]:
        """의존성 오버라이드

        Usage:
            with self.override(UserService, FakeUserService()):
                # 이 블록 내에서 UserService 대신 FakeUserService 사용
                service = self.get_instance(UserService)
        """
        self._mock_container.override(type_, instance)
        with self._mock_container.apply(self.manager):
            yield instance
        self._mock_container.remove(type_)

    @contextmanager
    def override_factory(
        self, type_: type[T], factory: Callable[[], T]
    ) -> Iterator[None]:
        """팩토리로 의존성 오버라이드

        Usage:
            with self.override_factory(UserService, lambda: FakeUserService()):
                service = self.get_instance(UserService)
        """
        self._mock_container.override_factory(type_, factory)
        with self._mock_container.apply(self.manager):
            yield
        self._mock_container.remove(type_)

    # =========================================================================
    # HTTP 테스트
    # =========================================================================

    @property
    def client(self) -> "BloomTestClient":
        """HTTP 테스트 클라이언트 (lazy 초기화)"""
        if self._client is None:
            from .pytest_plugin import BloomTestClient

            self._client = BloomTestClient(self.app)
        return self._client

    async def get(self, path: str, **kwargs) -> "AssertableResponse":
        """GET 요청"""
        return await self.client.get(path, **kwargs)

    async def post(self, path: str, **kwargs) -> "AssertableResponse":
        """POST 요청"""
        return await self.client.post(path, **kwargs)

    async def put(self, path: str, **kwargs) -> "AssertableResponse":
        """PUT 요청"""
        return await self.client.put(path, **kwargs)

    async def patch(self, path: str, **kwargs) -> "AssertableResponse":
        """PATCH 요청"""
        return await self.client.patch(path, **kwargs)

    async def delete(self, path: str, **kwargs) -> "AssertableResponse":
        """DELETE 요청"""
        return await self.client.delete(path, **kwargs)

    async def request(self, method: str, path: str, **kwargs) -> "AssertableResponse":
        """임의 HTTP 요청"""
        return await self.client.request(method, path, **kwargs)

    # =========================================================================
    # Assertion 헬퍼
    # =========================================================================

    def assert_instance(self, obj: Any, type_: type[T], msg: str | None = None) -> T:
        """타입 검증"""
        message = msg or f"Expected {type_.__name__}, got {type(obj).__name__}"
        assert isinstance(obj, type_), message
        return obj

    def assert_injected(self, obj: Any, field: str, type_: type[T] | None = None) -> T:
        """필드 주입 검증"""
        assert hasattr(obj, field), f"Field '{field}' not found in {type(obj).__name__}"
        value = getattr(obj, field)
        assert value is not None, f"Field '{field}' is None (not injected)"

        if type_ is not None:
            assert isinstance(
                value, type_
            ), f"Field '{field}': expected {type_.__name__}, got {type(value).__name__}"
        return value

    def assert_container_exists(self, type_: type) -> None:
        """컨테이너 존재 검증"""
        from bloom.core.container import Container

        container = Container.get_container(type_)
        assert container is not None, f"Container not found for {type_.__name__}"


# Type alias for import convenience
from .pytest_plugin import AssertableResponse, BloomTestClient
from .mock import MockContainer
