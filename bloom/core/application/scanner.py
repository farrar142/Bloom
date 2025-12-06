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

    # 클래스 변수로 현재 스캔 중인 패키지 추적
    _scanning_packages: set[str] = set()

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
            # 이미 스캔된 모듈은 건너뛰기
            if module in self._scanned_modules:
                logger.debug(f"Module {module} already scanned, skipping")
                continue
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

        # package_name이 None이면 디렉토리의 하위 패키지들만 직접 스캔
        if package_name is None:
            logger.info(f"Auto-scanning directory: {package_dir}")
            scanned_modules = self._scan_subpackages_only(package_dir)
            for module in scanned_modules:
                self.scan(module, container_manager=container_manager)
            logger.info(f"Auto-scanned {len(scanned_modules)} modules")
            return

        # 재귀 스캔 방지
        if package_name in ScannerManager._scanning_packages:
            logger.debug(f"Already scanning {package_name}, skipping")
            return

        ScannerManager._scanning_packages.add(package_name)
        try:
            logger.info(f"Auto-scanning package: {package_name} from {package_dir}")

            scanned_modules = self._scan_directory_recursive(package_dir, package_name)

            for module in scanned_modules:
                self.scan(module, container_manager=container_manager)

            logger.info(f"Auto-scanned {len(scanned_modules)} modules")
        finally:
            ScannerManager._scanning_packages.discard(package_name)

    def _resolve_package_info(self, caller_file: str | None) -> tuple[str | None, Path]:
        """패키지 정보 해석

        Args:
            caller_file: 호출 파일 경로 또는 패키지 이름

        Returns:
            (패키지 이름 또는 None, 패키지 디렉토리) 튜플
            패키지 이름이 None이면 디렉토리의 하위 패키지들만 스캔
        """
        import os

        # 패키지 이름 문자열인 경우 (예: "examples.demo_app")
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

        # 현재 작업 디렉토리 기반 스캔 (인자 없이 호출된 경우)
        if caller_file is None:
            cwd = Path(os.getcwd()).resolve()
            init_file = cwd / "__init__.py"

            if init_file.exists():
                # 현재 디렉토리가 패키지인 경우
                package_name = cwd.name
                # sys.path에 부모 디렉토리 추가
                parent_dir = str(cwd.parent)
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)
                    logger.debug(f"Added {parent_dir} to sys.path")
                return package_name, cwd
            else:
                # __init__.py가 없으면 현재 디렉토리의 하위 패키지들만 스캔
                # sys.path에 현재 디렉토리 추가
                cwd_str = str(cwd)
                if cwd_str not in sys.path:
                    sys.path.insert(0, cwd_str)
                    logger.debug(f"Added {cwd_str} to sys.path")
                return None, cwd  # package_name을 None으로 반환

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

        # 호출자가 패키지 내 모듈인지 확인
        if caller_module_name and "." in caller_module_name:
            # examples.demo_app.app -> examples.demo_app
            package_name = caller_module_name.rsplit(".", 1)[0]
            return package_name, package_dir

        # 호출자가 단독 모듈 (예: app.py를 uvicorn app:asgi로 실행)
        # 디렉토리에 __init__.py가 있으면 패키지로 취급
        init_file = package_dir / "__init__.py"
        if init_file.exists():
            # 디렉토리를 패키지로 취급
            package_name = package_dir.name
            parent_dir = str(package_dir.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
                logger.debug(f"Added {parent_dir} to sys.path")
            return package_name, package_dir

        # __init__.py가 없으면 하위 패키지들만 스캔
        package_dir_str = str(package_dir)
        if package_dir_str not in sys.path:
            sys.path.insert(0, package_dir_str)
            logger.debug(f"Added {package_dir_str} to sys.path")

        return None, package_dir  # package_name을 None으로 반환

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

    def _scan_subpackages_only(self, dir_path: Path) -> list[Any]:
        """디렉토리의 하위 패키지들만 스캔 (디렉토리 자체는 패키지가 아닌 경우)

        uvicorn app:asgi 처럼 단일 파일로 실행할 때 사용.
        디렉토리의 하위 폴더들을 최상위 패키지로 취급하여 스캔.

        Args:
            dir_path: 스캔할 디렉토리 경로

        Returns:
            스캔된 모듈 목록
        """
        scanned_modules = []

        for item in dir_path.iterdir():
            if item.is_dir() and not item.name.startswith(("_", ".")):
                sub_init = item / "__init__.py"
                if sub_init.exists():
                    # 하위 폴더를 최상위 패키지로 취급
                    package_name = item.name
                    scanned_modules.extend(
                        self._scan_directory_recursive(
                            item, package_name, is_root=False
                        )
                    )

        return scanned_modules
