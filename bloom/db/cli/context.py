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

        # 2. Application에서 스캔된 모든 모듈에서 엔티티 찾기
        if self.application:
            for module in getattr(self.application, "_scanned_modules", []):
                for name in dir(module):
                    try:
                        obj = getattr(module, name)
                        if isinstance(obj, type) and get_entity_meta(obj):
                            if obj not in entities:
                                entities.append(obj)
                    except Exception:
                        continue

            # 3. DI 컨테이너에서 Entity로 등록된 클래스들 수집
            for container in self.application.container_manager.get_all_containers():
                cls = container.target
                if isinstance(cls, type) and get_entity_meta(cls):
                    if cls not in entities:
                        entities.append(cls)

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

        import asyncio
        from bloom.db.session import SessionFactory
        from bloom.db.dialect import SQLiteDialect
        from bloom.db.backends import SQLiteBackend

        # 1. Application DI에서 SessionFactory 찾기
        if self.application:
            try:
                # 동기 컨텍스트에서 비동기 호출
                self._session_factory = asyncio.get_event_loop().run_until_complete(
                    self.application.container_manager.get_instance_async(
                        SessionFactory, required=False
                    )
                )
                if self._session_factory:
                    self._show_connection_info(self._session_factory)
                    return self._session_factory
            except RuntimeError:
                # 이미 이벤트 루프가 실행 중인 경우
                try:
                    loop = asyncio.new_event_loop()
                    self._session_factory = loop.run_until_complete(
                        self.application.container_manager.get_instance_async(
                            SessionFactory, required=False
                        )
                    )
                    loop.close()
                    if self._session_factory:
                        self._show_connection_info(self._session_factory)
                        return self._session_factory
                except Exception:
                    pass
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
