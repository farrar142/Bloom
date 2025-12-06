"""bloom.core.scanner - 모듈 스캔 및 컴포넌트 수집"""

from __future__ import annotations

import inspect
import importlib
import pkgutil
from types import ModuleType
from typing import Any, Iterator, TYPE_CHECKING

from .decorators import register_factories_from_configuration

if TYPE_CHECKING:
    from .manager import ContainerManager
    from .container import Container


class Scanner:
    """
    모듈 스캔 및 컴포넌트 수집.

    주어진 모듈(또는 패키지)을 순회하며 @Component가 붙은 클래스를 찾음.
    @Configuration 클래스의 @Factory 메서드도 등록.
    """

    # 클래스 변수로 스캔된 모듈 추적 (모든 인스턴스에서 공유)
    _scanned_modules: set[str] = set()

    def __init__(self, manager: "ContainerManager") -> None:
        self._manager = manager

    def scan(
        self, *modules: ModuleType | str | type | object
    ) -> list["Container[Any]"]:
        """
        모듈들을 스캔하여 컴포넌트 수집.

        Args:
            modules: 스캔할 모듈, 패키지 이름, 또는 클래스

        Returns:
            발견된 Container 목록
        """
        found: list[Container[Any]] = []

        for module in modules:
            if isinstance(module, str):
                # 문자열이면 모듈 import
                module = importlib.import_module(module)

            if isinstance(module, type):
                # 클래스면 직접 처리
                self._process_class(module, found)
            elif isinstance(module, ModuleType):
                # 모듈이면 스캔
                found.extend(self._scan_module(module))
            else:
                raise TypeError(
                    f"Expected module, str, or class, got {type(module).__name__}"
                )

        return found

    def _scan_module(self, module: ModuleType) -> list["Container[Any]"]:
        """단일 모듈 스캔"""
        module_name = module.__name__

        # 이미 스캔한 모듈은 스킵
        if module_name in self._scanned_modules:
            return []
        self._scanned_modules.add(module_name)

        found: list[Container[Any]] = []

        # 모듈 내 모든 클래스 검사
        for name, obj in inspect.getmembers(module, inspect.isclass):
            # 다른 모듈에서 import된 것은 스킵
            if getattr(obj, "__module__", None) != module_name:
                continue

            self._process_class(obj, found)

        # 서브모듈이 있으면 재귀 스캔 (패키지인 경우)
        if hasattr(module, "__path__"):
            for submodule in self._iter_submodules(module):
                found.extend(self._scan_module(submodule))

        return found

    def _process_class[T](self, cls: type[T], found: list["Container[Any]"]) -> None:
        """클래스 처리 - 컴포넌트/설정 확인"""
        # @Component 확인
        if getattr(cls, "__bloom_component__", False):
            container = self._manager.get_container(cls)
            if container:
                found.append(container)

        # @Configuration 확인 → @Factory 메서드 등록
        if getattr(cls, "__bloom_configuration__", False):
            register_factories_from_configuration(cls, self._manager)

    def _iter_submodules(self, package: ModuleType) -> Iterator[ModuleType]:
        """패키지의 서브모듈 순회"""
        if not hasattr(package, "__path__"):
            return

        for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
            full_name = f"{package.__name__}.{modname}"

            try:
                submodule = importlib.import_module(full_name)
                yield submodule
            except ImportError:
                # import 실패하면 스킵
                continue


def scan_modules(
    *modules: ModuleType | str | type | object,
    manager: "ContainerManager | None" = None,
) -> list["Container[Any]"]:
    """
    모듈 스캔 헬퍼 함수.

    사용 예:
        import my_app.services
        import my_app.repositories

        containers = scan_modules(
            my_app.services,
            my_app.repositories,
        )
    """
    if manager is None:
        from .manager import get_container_manager

        manager = get_container_manager()

    scanner = Scanner(manager)
    return scanner.scan(*modules)


def discover_components(
    package_name: str,
    manager: "ContainerManager | None" = None,
) -> list["Container[Any]"]:
    """
    패키지 내 모든 컴포넌트 자동 발견.

    사용 예:
        # my_app 패키지와 모든 서브패키지 스캔
        containers = discover_components("my_app")
    """
    if manager is None:
        from .manager import get_container_manager

        manager = get_container_manager()

    package = importlib.import_module(package_name)
    scanner = Scanner(manager)
    return scanner.scan(package)
