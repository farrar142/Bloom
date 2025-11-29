"""Application 및 의존성 정렬 테스트"""

from bloom import Application, Component
from bloom.core import Factory

from . import conftest


class TestApplication:
    """Application 테스트"""

    def test_application_sets_name(self):
        """Application이 app_name을 설정"""
        app = Application("my_app")
        assert app.manager.app_name == "my_app"

    def test_scan_and_ready(self):
        """새 API: scan().ready() 체이닝"""
        app = Application("test_app").scan(conftest).ready()

        service = app.manager.get_instance(conftest.Service)
        assert service is not None
        assert isinstance(service.repository, conftest.Repository)

    def test_factory_initialization(self):
        """팩토리를 통한 인스턴스 생성"""
        app = Application("test_app").scan(conftest).ready()

        external = app.manager.get_instance(conftest.ExternalService)
        assert external is not None
        assert isinstance(external.repo, conftest.Repository)

    def test_router_initialized_on_ready(self):
        """ready() 호출 시 라우터 초기화"""
        app = Application("test_app").scan(conftest).ready()

        # 라우터가 초기화되어야 함
        assert app.router is not None
        routes = app.router.get_routes()
        # conftest에 핸들러가 없으면 빈 리스트
        assert isinstance(routes, list)

    def test_asgi_property(self):
        """ASGI 애플리케이션 속성"""
        app = Application("test_app").scan(conftest).ready()

        # asgi 속성 접근 가능
        from bloom.web import ASGIApplication

        assert isinstance(app.asgi, ASGIApplication)


class TestTopologicalSort:
    """의존성 기반 정렬 테스트"""

    def test_dependency_order(self):
        """의존성 순서대로 초기화"""
        init_order: list[str] = []

        app = Application("test_app")

        @Component
        class A:
            def __init__(self):
                init_order.append("A")

        @Component
        class B:
            a: A

            def __init__(self):
                init_order.append("B")

        @Component
        class C:
            b: B

            def __init__(self):
                init_order.append("C")

        app.ready()

        # A -> B -> C 순서로 초기화되어야 함
        assert init_order == ["A", "B", "C"]
