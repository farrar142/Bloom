"""CLI Context - Database CLI execution context"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    from bloom.db.session import SessionFactory
    from bloom.application import Application


class DBContext:
    """CLI 실행 컨텍스트

    Application 인스턴스를 통해 DI 컨테이너에서 DB 관련 객체를 가져옵니다.
    """

    def __init__(
        self,
        migrations_dir: Path,
        application: "Application | None" = None,
        application_module: Any = None,  # 앱이 정의된 모듈
        entities_module: str | None = None,
        database_url: str | None = None,
    ):
        self.migrations_dir = migrations_dir
        self.application = application
        self.application_module = application_module
        self.entities_module = entities_module
        self.database_url = database_url
        self._entity_classes: list[type] | None = None
        self._session_factory: "SessionFactory | None" = None

    @property
    def entity_classes(self) -> list[type]:
        """엔티티 클래스들 로드"""
        if self._entity_classes is None:
            self._entity_classes = self._discover_entities()
        return self._entity_classes

    def _discover_entities(self) -> list[type]:
        """엔티티 클래스 자동 발견"""
        from bloom.db.entity import get_entity_meta

        entities: list[type] = []

        # 1. Application이 정의된 모듈에서 엔티티 찾기
        if self.application_module:
            for name in dir(self.application_module):
                obj = getattr(self.application_module, name)
                if isinstance(obj, type) and get_entity_meta(obj):
                    if obj not in entities:
                        entities.append(obj)

        # 2. Application DI에서 엔티티 찾기
        if self.application:
            # DI 컨테이너에서 Entity로 등록된 클래스들 수집
            for cls in self.application.manager.container_registry.keys():
                if isinstance(cls, type) and get_entity_meta(cls):
                    if cls not in entities:
                        entities.append(cls)

        # 3. */entities.py 패턴으로 앱별 엔티티 찾기
        entities.extend(self._discover_app_entities())

        # 4. entities_module에서 직접 로드
        if self.entities_module:
            try:
                module = importlib.import_module(self.entities_module)

                # 모듈에서 @Entity가 적용된 클래스 찾기
                for name in dir(module):
                    obj = getattr(module, name)
                    if isinstance(obj, type) and get_entity_meta(obj):
                        if obj not in entities:
                            entities.append(obj)

            except ImportError as e:
                click.echo(f"Warning: Could not import {self.entities_module}: {e}")

        return entities

    def _discover_app_entities(self) -> list[type]:
        """앱 디렉토리의 entities.py에서 엔티티 찾기
        
        스캔 경로:
          - */entities.py    (앱별 엔티티)
          - */models.py      (레거시 호환)
        """
        import sys
        from bloom.db.entity import get_entity_meta

        entities: list[type] = []
        cwd = Path.cwd()
        
        # cwd를 sys.path에 추가
        cwd_str = str(cwd)
        if cwd_str not in sys.path:
            sys.path.insert(0, cwd_str)

        for subdir in cwd.iterdir():
            if not subdir.is_dir():
                continue
            # 숨김/특수 디렉토리 제외
            if subdir.name.startswith((".", "_")):
                continue
            if subdir.name in ("venv", "env", "node_modules", "tests", "docs", "migrations", "settings"):
                continue

            # entities.py 또는 models.py 확인
            for filename in ("entities.py", "models.py"):
                entity_file = subdir / filename
                if entity_file.exists():
                    module_name = f"{subdir.name}.{filename[:-3]}"
                    try:
                        module = importlib.import_module(module_name)
                        for name in dir(module):
                            obj = getattr(module, name)
                            if isinstance(obj, type) and get_entity_meta(obj):
                                if obj not in entities:
                                    entities.append(obj)
                    except ImportError as e:
                        # 임포트 실패 시 조용히 무시
                        pass

        return entities

    def _show_connection_info(self, session_factory: "SessionFactory") -> None:
        """연결 정보 표시"""
        dialect_name = session_factory.dialect.name
        backend = session_factory.backend
        # Backend에서 연결 정보 추출
        if hasattr(backend, "config") and backend.config:
            config = backend.config
            if config.database:
                click.echo(f"Database: {dialect_name}://{config.database}")
            else:
                click.echo(f"Database: {dialect_name}")
        else:
            click.echo(f"Database: {dialect_name}")

    def get_session_factory(self) -> "SessionFactory":
        """세션 팩토리 생성 또는 DI에서 가져오기"""
        if self._session_factory is not None:
            return self._session_factory

        from bloom.db.session import SessionFactory
        from bloom.db.dialect import SQLiteDialect
        from bloom.db.backends import SQLiteBackend

        # 1. Application DI에서 SessionFactory 찾기
        if self.application:
            try:
                self._session_factory = self.application.manager.get_instance(
                    SessionFactory, raise_exception=False
                )
                if self._session_factory:
                    self._show_connection_info(self._session_factory)
                    return self._session_factory
            except Exception:
                pass

            # DI에 SessionFactory가 없으면 에러
            raise click.ClickException(
                "SessionFactory not found in Application DI container.\n\n"
                "Please register SessionFactory in your Application:\n\n"
                "  @Component\n"
                "  class DatabaseConfig:\n"
                "      @Factory\n"
                "      def session_factory(self) -> SessionFactory:\n"
                "          backend = SQLiteBackend('db.sqlite3')\n"
                "          return SessionFactory(backend)\n"
            )

        # 2. --entities 모드: --database 옵션이나 설정 파일에서 DB URL 사용
        db_url = self.database_url

        if not db_url:
            raise click.ClickException(
                "No database configuration found.\n\n"
                "Options:\n"
                "  1. Register SessionFactory in your Application via @Factory\n"
                "  2. Use --database option: bloom db --database=sqlite:///db.sqlite3 ...\n"
                "  3. Add database_url to pyproject.toml [tool.bloom.db]"
            )

        if db_url.startswith("sqlite"):
            db_path = db_url.replace("sqlite:///", "")
            backend = SQLiteBackend(db_path)
            self._session_factory = SessionFactory(backend)
        else:
            raise click.ClickException(f"Unsupported database type: {db_url}")

        self._show_connection_info(self._session_factory)
        return self._session_factory
