"""bloom Application"""

from typing import TYPE_CHECKING, Any
from pathlib import Path

if TYPE_CHECKING:
    from .core.container import Container

from .core.manager import ContainerManager, set_current_manager, try_get_current_manager
from .core.utils import topological_sort
from .web.router import Router
from .web.asgi import ASGIApplication
from .config.loader import ConfigurationLoader
from .config.binder import ConfigurationBinder
from .config.properties import is_configuration_properties, get_prefix


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

    def __init__(self, name: str, manager: "ContainerManager | None" = None):
        self.name = name
        # 외부에서 manager를 전달받거나, 현재 활성 manager 사용, 또는 새로 생성
        if manager is not None:
            self.manager = manager
        elif existing := try_get_current_manager():
            self.manager = existing
            self.manager.app_name = name  # 이름 업데이트
        else:
            self.manager = ContainerManager(name)
        self._router: Router | None = None
        self._asgi: ASGIApplication | None = None
        self._is_ready = False
        self._config_loader = ConfigurationLoader()
        self._config_binder = ConfigurationBinder()
        # 생성 시점에 현재 매니저로 설정 (데코레이터 자동 등록 지원)
        set_current_manager(self.manager)

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

    def load_config(
        self,
        source: str | Path | dict[str, Any] | None = None,
        source_type: str = "auto",
    ) -> "Application":
        """
        설정 로드

        Args:
            source: 설정 소스 (파일 경로, dict 등)
            source_type: 소스 타입 ("yaml", "json", "env", "dict", "auto")

        Returns:
            self (메서드 체이닝 지원)

        사용 예시:
            app.load_config("config/application.yaml")
            app.load_config({"app": {"name": "MyApp"}}, source_type="dict")
            app.load_config(source_type="env")  # 환경 변수만 로드
        """
        if source is None:
            # 환경 변수만 로드
            self._config_loader.load_from_env()
            return self

        if isinstance(source, dict):
            self._config_loader.load_from_dict(source)
            return self

        # 파일 경로
        path = Path(source)

        if source_type == "auto":
            # 확장자로 타입 자동 감지
            suffix = path.suffix.lower()
            if suffix in (".yaml", ".yml"):
                source_type = "yaml"
            elif suffix == ".json":
                source_type = "json"
            elif suffix == ".env":
                source_type = "env"

        if source_type == "yaml":
            self._config_loader.load_from_yaml(path)
        elif source_type == "json":
            self._config_loader.load_from_json(path)
        elif source_type == "env":
            self._config_loader.load_from_dotenv(path)

        return self

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

        # 1. ConfigurationProperties 바인딩
        self._bind_configuration_properties()

        # 2. 컨테이너 초기화
        self._initialize_containers()

        # 3. 라우터 초기화
        self.router.collect_routes()

        self._is_ready = True
        return self

    def _bind_configuration_properties(self) -> None:
        """ConfigurationProperties를 바인딩하여 인스턴스 생성"""
        config_dict = self._config_loader.get_config()

        for qual_containers in self.manager.get_all_containers().values():
            for qualifier, container in qual_containers.items():
                target = container.target

                # ConfigurationProperties인지 확인
                if not is_configuration_properties(target):
                    continue

                # prefix 추출
                prefix = get_prefix(target)

                # 설정 바인딩
                instance = self._config_binder.bind(config_dict, target, prefix)

                # 인스턴스 등록
                self.manager.set_instance(target, instance, qualifier=qualifier)

    def _initialize_containers(self) -> None:
        """모든 컨테이너를 토폴로지컬 순서로 초기화"""
        from bloom.core.lazy import is_lazy_component

        # 모든 컨테이너를 (qualifier, container) 튜플 리스트로 변환
        all_containers: list[tuple[str, "Container"]] = []
        for qual_containers in self.manager.get_all_containers().values():
            for qualifier, container in qual_containers.items():
                all_containers.append((qualifier, container))

        # 토폴로지컬 정렬
        sorted_containers = topological_sort(all_containers)

        # 정렬된 순서로 초기화 (초기화 순서 저장)
        self._initialized_containers = sorted_containers

        for qualifier, container in sorted_containers:
            # @Lazy 컴포넌트는 즉시 초기화하지 않음 (접근 시 LazyProxy가 초기화)
            if is_lazy_component(container):
                continue
            instance = container.initialize_instance()
            self.manager.set_instance(container.target, instance, qualifier=qualifier)

    def shutdown(self) -> "Application":
        """
        애플리케이션 종료

        모든 컴포넌트의 @PreDestroy 메서드를 역순으로 호출합니다.
        (나중에 초기화된 컴포넌트부터 먼저 정리)

        Returns:
            self (메서드 체이닝 지원)
        """
        if not self._is_ready:
            return self

        # 현재 매니저 설정
        set_current_manager(self.manager)

        # LifecycleManager를 통해 역순으로 PreDestroy 호출
        if hasattr(self, "_initialized_containers"):
            containers = [container for _, container in self._initialized_containers]
            self.manager.lifecycle.invoke_all_pre_destroy(containers)

        self._is_ready = False
        return self

    # 하위 호환성을 위한 메서드들
    def scan_components(self, module: object) -> None:
        """@deprecated: scan() 사용 권장"""
        self.scan(module)

    def initialize_components(self) -> None:
        """@deprecated: ready() 사용 권장"""
        self._initialize_containers()
