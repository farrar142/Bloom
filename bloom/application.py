"""bloom Application"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core.container import Container

from .core.manager import ContainerManager, set_current_manager
from .core.utils import topological_sort
from .web.router import Router
from .web.asgi import ASGIApplication


class Application:
    """
    bloom 애플리케이션 진입점

    사용 예시:
        app = Application("my_app")
        app.scan(MyModule)
        app.ready()

        # ASGI 서버로 실행
        # uvicorn main:app.asgi
    """

    def __init__(self, name: str):
        self.name = name
        self.manager = ContainerManager(name)  # 인스턴스 소유
        self._router: Router | None = None
        self._asgi: ASGIApplication | None = None
        self._is_ready = False

    @property
    def router(self) -> Router:
        """Router 인스턴스 반환"""
        if self._router is None:
            self._router = Router(self.manager)
        return self._router

    @property
    def asgi(self) -> ASGIApplication:
        """ASGI 애플리케이션 반환 (uvicorn 등에서 사용)"""
        if self._asgi is None:
            self._asgi = ASGIApplication(self.router)
        return self._asgi

    def scan(self, *modules: object) -> "Application":
        """
        모듈들을 스캔하여 컴포넌트 수집

        Args:
            *modules: 스캔할 모듈들

        Returns:
            self (메서드 체이닝 지원)
        """
        # 스캔 중 현재 매니저 설정
        set_current_manager(self.manager)
        for module in modules:
            self.manager.scan_components(module)
        return self

    def ready(self) -> "Application":
        """
        애플리케이션 초기화 완료

        1. 컴포넌트 의존성 정렬 및 초기화
        2. 라우터에 핸들러 등록

        Returns:
            self (메서드 체이닝 지원)
        """
        if self._is_ready:
            return self

        # 현재 매니저 설정
        set_current_manager(self.manager)

        # 1. 컨테이너 초기화
        self._initialize_containers()

        # 2. 라우터 초기화
        self.router.collect_routes()

        self._is_ready = True
        return self

    def _initialize_containers(self) -> None:
        """모든 컨테이너를 토폴로지컬 순서로 초기화"""
        # 모든 컨테이너를 (qualifier, container) 튜플 리스트로 변환
        all_containers: list[tuple[str, "Container"]] = []
        for qual_containers in self.manager.get_all_containers().values():
            for qualifier, container in qual_containers.items():
                all_containers.append((qualifier, container))

        # 토폴로지컬 정렬
        sorted_containers = topological_sort(all_containers)

        # 정렬된 순서로 초기화
        for qualifier, container in sorted_containers:
            instance = container.initialize_instance()
            self.manager.set_instance(container.target, instance, qualifier=qualifier)

    # 하위 호환성을 위한 메서드들
    def scan_components(self, module: object) -> None:
        """@deprecated: scan() 사용 권장"""
        self.scan(module)

    def initialize_components(self) -> None:
        """@deprecated: ready() 사용 권장"""
        self._initialize_containers()
