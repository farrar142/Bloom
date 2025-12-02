"""Bloom 테스팅 유틸리티 테스트"""

import pytest
from dataclasses import dataclass

from bloom import Application, Component
from bloom.web import Controller, Get, Post
from bloom.web.http import HttpResponse
from bloom.web.params.types import RequestBody

from bloom.tests import (
    TestClient,
    TestResponse,
    MockContainer,
    override_dependency,
    isolated_container,
    create_test_app,
    assert_instance_of,
    assert_injected,
    assert_has_container,
    get_container_info,
    print_container_tree,
    SpyComponent,
    CallRecord,
)


# === 테스트용 컴포넌트 ===


@dataclass
class CreateItemRequest:
    name: str


@Component
class TestRepository:
    """테스트용 Repository"""

    def get_items(self) -> list[str]:
        return ["item1", "item2", "item3"]


@Component
class TestService:
    """Repository를 의존하는 Service"""

    repository: TestRepository

    def get_all_items(self) -> list[str]:
        return self.repository.get_items()


@Controller
class TestController:
    """테스트용 Controller"""

    service: TestService

    @Get("/items")
    def get_items(self) -> list[str]:
        return self.service.get_all_items()

    @Post("/items")
    def create_item(self, item: RequestBody[CreateItemRequest]) -> dict:
        return {"status": "created", "item": {"name": item.name}}

    @Get("/error")
    def error_endpoint(self) -> HttpResponse:
        raise ValueError("Test error")


# === TestClient 테스트 ===


class TestTestClient:
    """TestClient 테스트"""

    @pytest.mark.asyncio
    async def test_get_request(self):
        """GET 요청 테스트"""
        app = create_test_app("test", TestRepository, TestService, TestController)
        client = TestClient(app)

        response = await client.get("/items")

        assert response.status_code == 200
        assert response.json() == ["item1", "item2", "item3"]

    @pytest.mark.asyncio
    async def test_post_request(self):
        """POST 요청 테스트"""
        app = create_test_app("test", TestRepository, TestService, TestController)
        client = TestClient(app)

        response = await client.post("/items", json_body={"name": "new_item"})

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert data["item"]["name"] == "new_item"

    @pytest.mark.asyncio
    async def test_404_response(self):
        """404 응답 테스트"""
        app = create_test_app("test", TestRepository, TestService, TestController)
        client = TestClient(app)

        response = await client.get("/not-found")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_response_headers(self):
        """응답 헤더 테스트"""
        app = create_test_app("test", TestRepository, TestService, TestController)
        client = TestClient(app)

        response = await client.get("/items")

        assert "content-type" in response.headers
        assert "application/json" in response.headers.get("content-type", "")


# === MockContainer 테스트 ===


class TestMockContainer:
    """MockContainer 테스트"""

    async def test_override_before_ready(self):
        """ready() 전에 오버라이드 적용 테스트"""

        class FakeRepository:
            def get_items(self) -> list[str]:
                return ["fake1", "fake2"]

        app = Application("test")
        app.scan(TestRepository).scan(TestService)

        mock = MockContainer()
        mock.override(TestRepository, FakeRepository())

        with mock.apply(app.manager):
            # ready() 호출 시 mock이 주입됨
            await app.ready_async()
            service = app.manager.get_instance(TestService)
            items = service.get_all_items()
            assert items == ["fake1", "fake2"]

    async def test_override_instance_directly(self):
        """인스턴스 레지스트리 직접 오버라이드 테스트"""

        class FakeRepository:
            def get_items(self) -> list[str]:
                return ["fake1", "fake2"]

        app = create_test_app("test", TestRepository)
        mock = MockContainer()
        mock.override(TestRepository, FakeRepository())

        with mock.apply(app.manager):
            # MockContainer가 인스턴스 레지스트리를 대체함
            repo = app.manager.get_instance(TestRepository)
            items = repo.get_items()
            assert items == ["fake1", "fake2"]

    async def test_override_factory(self):
        """팩토리 오버라이드 테스트"""
        call_count = 0

        class FakeRepository:
            def get_items(self) -> list[str]:
                return ["factory_item"]

        def create_fake():
            nonlocal call_count
            call_count += 1
            return FakeRepository()

        mock = MockContainer()
        mock.override_factory(TestRepository, create_fake)

        # get_mock 호출 시마다 새 인스턴스 생성
        _ = mock.get_mock(TestRepository)
        _ = mock.get_mock(TestRepository)

        assert call_count == 2

    async def test_chained_override(self):
        """체이닝 오버라이드 테스트"""

        class FakeRepo:
            def get_items(self):
                return []

        class FakeService:
            def get_all_items(self):
                return ["chained"]

        mock = MockContainer()
        result = mock.override(TestRepository, FakeRepo()).override(
            TestService, FakeService()
        )

        assert result is mock  # 체이닝 반환 확인
        assert mock.get_mock(TestRepository) is not None
        assert mock.get_mock(TestService) is not None

    async def test_clear_and_remove(self):
        """clear, remove 테스트"""

        class FakeRepo:
            pass

        mock = MockContainer()
        mock.override(TestRepository, FakeRepo())

        assert mock.get_mock(TestRepository) is not None

        mock.remove(TestRepository)
        assert mock.get_mock(TestRepository) is None

        mock.override(TestRepository, FakeRepo())
        mock.clear()
        assert mock.get_mock(TestRepository) is None


# === override_dependency 컨텍스트 매니저 테스트 ===


class TestOverrideDependency:
    """override_dependency 컨텍스트 매니저 테스트"""

    async def test_single_override(self):
        """단일 의존성 오버라이드"""

        class FakeRepo:
            def get_items(self):
                return ["override_test"]

        app = Application("test")
        app.scan(TestRepository)

        with override_dependency(TestRepository, FakeRepo(), app.manager) as fake:
            await app.ready_async()
            repo = app.manager.get_instance(TestRepository)
            items = repo.get_items()

        assert items == ["override_test"]


# === isolated_container 테스트 ===


class TestIsolatedContainer:
    """isolated_container 테스트"""

    async def test_isolation(self):
        """컨테이너 격리 테스트"""
        with isolated_container("isolated") as manager:
            assert manager.app_name == "isolated"
            assert len(manager.container_registry) == 0


# === create_test_app 테스트 ===


class TestCreateTestApp:
    """create_test_app 테스트"""

    async def test_basic_creation(self):
        """기본 생성 테스트"""
        app = create_test_app("mytest", TestRepository)

        assert app.name == "mytest"
        repo = app.manager.get_instance(TestRepository)
        assert repo is not None

    async def test_with_config(self):
        """설정 포함 생성 테스트"""
        app = create_test_app(
            "config_test",
            TestRepository,
            config={"app": {"name": "TestApp"}},
        )

        config = app._config_manager.get_config()
        assert config.get("app", {}).get("name") == "TestApp"

    async def test_without_ready(self):
        """ready=False 테스트"""
        app = create_test_app("no_ready", TestRepository, ready=False)

        # ready() 호출 전이므로 인스턴스가 없어야 함
        assert len(app.manager.instance_registry) == 0

        await app.ready_async()
        repo = app.manager.get_instance(TestRepository)
        assert repo is not None


# === Assertion 헬퍼 테스트 ===


class TestAssertionHelpers:
    """Assertion 헬퍼 테스트"""

    async def test_assert_instance_of(self):
        """타입 검증 테스트"""
        obj = "test"
        assert_instance_of(obj, str)

        with pytest.raises(AssertionError):
            assert_instance_of(obj, int)

    async def test_assert_injected(self):
        """주입 검증 테스트"""
        app = create_test_app("test", TestRepository, TestService)
        service = app.manager.get_instance(TestService)

        repo = assert_injected(service, "repository", TestRepository)
        assert repo is not None
        assert isinstance(repo, TestRepository)

    async def test_assert_has_container(self):
        """컨테이너 존재 검증 테스트"""
        assert_has_container(TestRepository)

        class NoContainerClass:
            pass

        with pytest.raises(AssertionError):
            assert_has_container(NoContainerClass)


# === 디버깅 유틸리티 테스트 ===


class TestDebuggingUtils:
    """디버깅 유틸리티 테스트"""

    async def test_get_container_info(self):
        """컨테이너 정보 조회 테스트"""
        info = get_container_info(TestRepository)

        assert info["exists"] is True
        assert info["target"] == "TestRepository"

        class NoContainer:
            pass

        info = get_container_info(NoContainer)
        assert info["exists"] is False

    async def test_print_container_tree(self):
        """컨테이너 트리 출력 테스트"""
        app = create_test_app("tree_test", TestRepository, TestService)
        tree = print_container_tree(app.manager)

        assert "ContainerManager: tree_test" in tree
        assert "Containers:" in tree
        assert "Instances:" in tree


# === SpyComponent 테스트 ===


class TestSpyComponent:
    """SpyComponent 테스트"""

    async def test_spy_call_tracking(self):
        """호출 추적 테스트"""

        class MyService:
            def add(self, a: int, b: int) -> int:
                return a + b

        spy = SpyComponent(MyService())

        result = spy.call_method("add", 1, 2)

        assert result == 3
        assert spy.call_count("add") == 1
        calls = spy.get_calls("add")
        assert len(calls) == 1
        assert calls[0].args == (1, 2)
        assert calls[0].result == 3

    async def test_spy_exception_tracking(self):
        """예외 추적 테스트"""

        class MyService:
            def fail(self):
                raise ValueError("fail!")

        spy = SpyComponent(MyService())

        with pytest.raises(ValueError):
            spy.call_method("fail")

        assert spy.call_count("fail") == 1
        calls = spy.get_calls("fail")
        assert isinstance(calls[0].exception, ValueError)

    async def test_spy_reset(self):
        """리셋 테스트"""

        class MyService:
            def method(self):
                return "ok"

        spy = SpyComponent(MyService())
        spy.call_method("method")
        assert spy.call_count("method") == 1

        spy.reset()
        assert spy.call_count("method") == 0


# === CallRecord 테스트 ===


class TestCallRecord:
    """CallRecord 테스트"""

    async def test_call_record_repr(self):
        """문자열 표현 테스트"""
        record = CallRecord(args=(1, 2), kwargs={"key": "value"}, result=3)

        repr_str = repr(record)
        assert "args=(1, 2)" in repr_str
        assert "kwargs={'key': 'value'}" in repr_str
        assert "result=3" in repr_str


# === TestCase 테스트 ===
