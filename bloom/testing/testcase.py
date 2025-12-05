"""bloom.testing.testcase - BloomTestCase 기본 클래스"""

from __future__ import annotations

import inspect
from typing import Any, TypeVar, Generic, get_type_hints, get_origin, get_args
from unittest.mock import MagicMock, AsyncMock

from bloom.core import get_container_manager, reset_container_manager
from bloom.core.container import Container, ScopeEnum

T = TypeVar("T")


class BloomTestCase:
    """
    Bloom 프레임워크 테스트 케이스 기본 클래스.

    사용 예:
        class MyTest(BloomTestCase):
            repo: MockBean[UserRepository]

            async def setUp(self):
                self.repo.find_all.return_value = [{"id": 1}]

            async def test_users(self):
                service = await self.get_instance(UserService)
                users = service.get_users()
                assert len(users) == 1

            async def tearDown(self):
                pass
    """

    _manager = None
    _mock_beans: dict[str, Any] = {}
    _fixtures: dict[str, Any] = {}

    async def setUp(self) -> None:
        """테스트 설정 (오버라이드 가능)"""
        pass

    async def tearDown(self) -> None:
        """테스트 정리 (오버라이드 가능)"""
        pass

    async def _run_test(self, method_name: str) -> None:
        """테스트 메서드 실행 (내부용)"""
        # 컨테이너 리셋 및 초기화
        reset_container_manager()
        self._manager = get_container_manager()
        self._mock_beans = {}
        self._fixtures = {}

        # MockBean 필드 분석 및 설정
        await self._setup_mock_beans()

        # setUp 호출
        await self.setUp()

        # autouse 픽스처 실행
        await self._run_autouse_fixtures()

        try:
            # 테스트 메서드 실행
            method = getattr(self, method_name)

            # 픽스처 의존성 주입
            kwargs = await self._resolve_fixture_dependencies(method)

            if inspect.iscoroutinefunction(method):
                await method(**kwargs)
            else:
                method(**kwargs)
        finally:
            # tearDown 호출
            await self.tearDown()

            # 컨테이너 정리
            if self._manager:
                await self._manager.scope_manager.destroy_singletons()
            reset_container_manager()

    async def _setup_mock_beans(self) -> None:
        """MockBean 필드 설정"""
        from .mock import MockBean

        # 클래스의 타입 힌트 분석
        hints = {}
        for cls in type(self).__mro__:
            if cls is BloomTestCase or cls is object:
                continue
            try:
                hints.update(get_type_hints(cls, include_extras=True))
            except Exception:
                pass

        for name, hint in hints.items():
            origin = get_origin(hint)

            # MockBean[T] 타입인지 확인
            if origin is MockBean or (
                hasattr(hint, "__origin__")
                and getattr(hint.__origin__, "__name__", "") == "MockBean"
            ):
                # 제네릭 타입 인자 추출
                args = get_args(hint)
                if args:
                    target_type = args[0]

                    # Mock 생성
                    mock = MagicMock(spec=target_type)

                    # 인스턴스에 설정
                    setattr(self, name, mock)
                    self._mock_beans[name] = (target_type, mock)

                    # 컨테이너에 Mock 등록 (Container로 래핑)
                    if self._manager:
                        container = Container(
                            target=target_type,
                            scope=ScopeEnum.SINGLETON,
                            name=None,
                            primary=False,
                            lazy=False,
                        )
                        self._manager.register(container, allow_override=True)
                        # 싱글톤 캐시에 직접 등록
                        self._manager.scope_manager.set_singleton(target_type, mock)

    async def _run_autouse_fixtures(self) -> None:
        """autouse 픽스처 실행"""
        for name in dir(self):
            if name.startswith("_"):
                continue

            method = getattr(self, name, None)
            if not callable(method):
                continue

            # fixture 데코레이터로 표시된 메서드인지 확인
            if getattr(method, "_bloom_fixture", False) and getattr(
                method, "_bloom_fixture_autouse", False
            ):
                if inspect.iscoroutinefunction(method):
                    result = await method()
                else:
                    result = method()

                # generator인 경우 yield까지 실행
                if inspect.isgenerator(result) or inspect.isasyncgen(result):
                    self._fixtures[name] = result
                    if inspect.isasyncgen(result):
                        await result.__anext__()
                    else:
                        next(result)

    async def _resolve_fixture_dependencies(self, method) -> dict[str, Any]:
        """메서드의 픽스처 의존성 해결"""
        kwargs = {}

        try:
            hints = get_type_hints(method)
        except Exception:
            return kwargs

        sig = inspect.signature(method)

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            # 해당 이름의 픽스처가 있는지 확인
            fixture_method = getattr(self, param_name, None)
            if fixture_method and getattr(fixture_method, "_bloom_fixture", False):
                if inspect.iscoroutinefunction(fixture_method):
                    kwargs[param_name] = await fixture_method()
                else:
                    kwargs[param_name] = fixture_method()

        return kwargs

    async def get_instance(self, cls: type[T]) -> T:
        """DI 컨테이너에서 인스턴스 획득"""
        if self._manager is None:
            self._manager = get_container_manager()
            await self._manager.initialize()

        # 컨테이너에 등록되지 않은 경우, @Component 메타데이터가 있으면 등록
        if not self._manager.has_container(cls):
            if getattr(cls, "__bloom_component__", False):
                scope = getattr(cls, "__bloom_scope__", ScopeEnum.SINGLETON)
                name = getattr(cls, "__bloom_name__", None)
                primary = getattr(cls, "__bloom_primary__", False)
                lazy = getattr(cls, "__bloom_lazy__", False)

                container = Container(
                    target=cls,
                    scope=scope,
                    name=name,
                    primary=primary,
                    lazy=lazy,
                )
                self._manager.register(container, allow_override=True)

        result = await self._manager.get_instance_async(cls)
        return result  # type: ignore

    def test_client(self, app) -> "TestClientContextManager":
        """HTTP TestClient 컨텍스트 매니저"""
        from .client import TestClient

        return TestClientContextManager(app)

    def stomp_client(self, url: str) -> "STOMPClientContextManager":
        """STOMP 클라이언트 컨텍스트 매니저"""
        return STOMPClientContextManager(url)


class TestClientContextManager:
    """TestClient async context manager"""

    def __init__(self, app):
        self.app = app
        self.client = None

    async def __aenter__(self):
        from .client import TestClient

        self.client = TestClient(self.app)
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class STOMPClientContextManager:
    """STOMP 클라이언트 async context manager"""

    def __init__(self, url: str):
        self.url = url
        self.client = None

    async def __aenter__(self):
        from .mock import MockSTOMP

        # 실제 STOMP 클라이언트 대신 Mock 반환 (테스트용)
        self.client = MockSTOMP()
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.disconnect()
