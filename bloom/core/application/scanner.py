"""bloom.core.application.scanner - 모듈 스캔 관리

모듈 스캔 및 자동 스캔을 담당합니다.
"""

from __future__ import annotations

import importlib
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager


logger = logging.getLogger(__name__)


class ScannerManager:
    """모듈 스캔 관리자

    @Component, @Service, @Controller 등이 붙은 클래스를 스캔합니다.
    """

    def __init__(self):
        self._scanned_modules: list[Any] = []

    @property
    def scanned_modules(self) -> list[Any]:
        """스캔된 모듈 목록"""
        return self._scanned_modules

    def scan(
        self,
        *modules: object,
        container_manager: "ContainerManager",
    ) -> None:
        """모듈들을 스캔하여 컴포넌트 수집

        Args:
            modules: 스캔할 모듈들
            container_manager: 컨테이너 관리자
        """
        from bloom.core.scanner import scan_modules

        for module in modules:
            self._scanned_modules.append(module)
            scan_modules(module, manager=container_manager)

    def auto_scan(
        self,
        caller_file: str | None,
        container_manager: "ContainerManager",
    ) -> None:
        """호출 파일 위치의 패키지와 하위 디렉토리를 자동 스캔

        Args:
            caller_file: 호출 파일 경로 또는 패키지 이름
            container_manager: 컨테이너 관리자
        """
        package_name, package_dir = self._resolve_package_info(caller_file)

        logger.info(f"Auto-scanning package: {package_name} from {package_dir}")

        scanned_modules = self._scan_directory_recursive(package_dir, package_name)

        for module in scanned_modules:
            self.scan(module, container_manager=container_manager)

        logger.info(f"Auto-scanned {len(scanned_modules)} modules")

    def _resolve_package_info(self, caller_file: str | None) -> tuple[str, Path]:
        """패키지 정보 해석

        Args:
            caller_file: 호출 파일 경로 또는 패키지 이름

        Returns:
            (패키지 이름, 패키지 디렉토리) 튜플
        """
        # 패키지 이름 문자열인 경우
        if (
            caller_file
            and not caller_file.endswith((".py", ".pyc"))
            and "." in caller_file
        ):
            package_name = caller_file
            try:
                package_module = importlib.import_module(package_name)
                if hasattr(package_module, "__file__") and package_module.__file__:
                    package_dir = Path(package_module.__file__).resolve().parent
                else:
                    raise ValueError(f"Package {package_name} has no __file__")
            except ImportError as e:
                raise ValueError(f"Could not import package {package_name}: {e}")
            return package_name, package_dir

        # 호출자의 __file__ 자동 감지
        if caller_file is None:
            import inspect

            frame = inspect.currentframe()
            # 2단계 위로 (auto_scan -> Application.auto_scan -> 호출자)
            if frame and frame.f_back and frame.f_back.f_back:
                caller_file = frame.f_back.f_back.f_globals.get("__file__")
            if not caller_file:
                raise ValueError(
                    "Could not detect caller file. " "Please pass __file__ explicitly."
                )

        caller_path = Path(caller_file).resolve()
        package_dir = caller_path.parent

        # 패키지 이름 결정
        caller_module_name = None
        for name, module in sys.modules.items():
            if hasattr(module, "__file__") and module.__file__:
                try:
                    if Path(module.__file__).resolve() == caller_path:
                        caller_module_name = name
                        break
                except (OSError, ValueError):
                    continue

        if caller_module_name:
            package_name = (
                caller_module_name.rsplit(".", 1)[0]
                if "." in caller_module_name
                else caller_module_name
            )
        else:
            package_name = package_dir.name

        return package_name, package_dir

    def _scan_directory_recursive(
        self,
        dir_path: Path,
        parent_package: str,
        is_root: bool = True,
    ) -> list[Any]:
        """디렉토리를 재귀적으로 스캔

        Args:
            dir_path: 스캔할 디렉토리 경로
            parent_package: 부모 패키지 이름
            is_root: 루트 디렉토리인지 (루트는 스캔하지 않음)

        Returns:
            스캔된 모듈 목록
        """
        scanned_modules = []

        init_file = dir_path / "__init__.py"
        if not init_file.exists():
            return scanned_modules

        # 루트 디렉토리가 아니면 현재 패키지 import
        if not is_root:
            try:
                module = importlib.import_module(parent_package)
                scanned_modules.append(module)
            except ImportError as e:
                logger.warning(f"Could not import {parent_package}: {e}")
                return scanned_modules

        # 하위 디렉토리 스캔
        for item in dir_path.iterdir():
            if item.is_dir() and not item.name.startswith(("_", ".")):
                sub_init = item / "__init__.py"
                if sub_init.exists():
                    sub_package = f"{parent_package}.{item.name}"
                    scanned_modules.extend(
                        self._scan_directory_recursive(item, sub_package, is_root=False)
                    )

        return scanned_modules
