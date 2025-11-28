"""RouteManager - 라우트 Manager

ContainerManager에서 HttpMethodHandler들을 수집하여 RouteRegistry에 등록합니다.
"""

from typing import TYPE_CHECKING

from bloom.core.abstract import AbstractManager

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager

from .entry import RouteEntry
from .registry import RouteRegistry


class RouteManager(AbstractManager[RouteRegistry]):
    """
    라우트 Manager

    ContainerManager에서 HttpMethodHandler들을 수집하고,
    Controller의 RequestMapping prefix를 결합하여 RouteEntry를 생성합니다.

    특징:
    - HttpMethodHandler 자동 수집
    - Controller prefix 자동 결합
    - RouteRegistry 자동 생성/관리

    사용 예시:
        manager = RouteManager()
        manager.initialize(container_manager)

        # 라우트 검색
        handler, params = manager.registry.find("GET", "/api/users/123")
    """

    registry_type = RouteRegistry
    # entry_type은 사용하지 않음 (HttpMethodHandler에서 직접 수집)

    def __init__(self):
        super().__init__()
        self._controller_prefixes: dict[type, str] = {}

    @property
    def controller_prefixes(self) -> dict[type, str]:
        """Controller별 RequestMapping prefix"""
        return self._controller_prefixes

    def initialize(self, container_manager: "ContainerManager") -> None:
        """
        Manager 초기화

        1. RouteRegistry 검색/생성
        2. Controller prefix 수집
        3. HttpMethodHandler들을 수집하여 RouteEntry 생성

        Args:
            container_manager: HttpMethodHandler와 Controller를 검색할 ContainerManager
        """
        if self._initialized:
            return

        from bloom.web.controller import ControllerContainer
        from bloom.web.handler import HttpMethodHandler

        # 1. RouteRegistry 검색/생성
        existing_registries = container_manager.get_sub_instances(RouteRegistry)
        if existing_registries:
            # 기존 Registry가 있으면 그대로 사용 (이미 등록된 라우트만 활성화)
            self._registry = existing_registries[0]
            self._initialized = True
            return

        # 새 Registry 생성
        self._registry = RouteRegistry()

        # 2. Controller prefix 수집
        for qual_containers in container_manager.get_all_containers().values():
            for container in qual_containers.values():
                if isinstance(container, ControllerContainer):
                    prefixes = container.get_metadatas("request_mapping", default="")
                    self._controller_prefixes[container.target] = (
                        prefixes[0] if prefixes else ""
                    )

        # 3. HttpMethodHandler 수집 및 RouteEntry 생성
        for qual_containers in container_manager.get_all_containers().values():
            for container in qual_containers.values():
                if isinstance(container, HttpMethodHandler):
                    # owner_cls의 RequestMapping prefix 가져오기
                    prefix = ""
                    if container.owner_cls:
                        prefix = self._controller_prefixes.get(container.owner_cls, "")

                    # prefix + handler path 결합
                    handler_path = container.get_metadata("http_path")
                    full_path = prefix + handler_path
                    method = container.get_metadata("http_method")

                    # RouteEntry 생성 및 등록
                    entry = RouteEntry(method, full_path, container)
                    self._registry.register(entry)

        self._initialized = True

    def find_handler(self, method: str, path: str):
        """
        요청에 맞는 핸들러 찾기

        Args:
            method: HTTP 메서드
            path: 요청 경로

        Returns:
            (핸들러, 경로 파라미터) 튜플
        """
        return self.registry.find(method, path)

    def get_routes(self) -> list[tuple[str, str, str]]:
        """등록된 라우트 목록 반환"""
        return self.registry.get_all_routes()
