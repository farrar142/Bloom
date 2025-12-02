"""정적 파일 서빙

디렉토리의 정적 파일을 HTTP로 서빙하는 기능을 제공합니다.

사용 예시:
    import asyncio
    from bloom import Application, Component
    from bloom.core.decorators import Factory
    from bloom.web.static import StaticFiles, StaticFilesContainer

    @Component
    class StaticConfig:
        @Factory
        def static_files_container(self) -> StaticFilesContainer:
            container = StaticFilesContainer()
            container.add("/static", "public")
            container.add("/assets", "assets", html=True)
            return container

    app = Application("my_app").scan(StaticConfig)
    asyncio.run(app.ready_async())
    # StaticFilesManager가 자동으로 StaticFilesContainer를 수집하여 사용
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bloom.core.manager import ContainerManager
    from .http import HttpRequest, HttpResponse, FileResponse, StreamingResponse


# ============================================================================
# StaticFileConfig
# ============================================================================


@dataclass
class StaticFileConfig:
    """정적 파일 설정"""

    directory: Path
    path_prefix: str
    html: bool = False  # index.html 자동 서빙
    check_exists: bool = True  # 디렉토리 존재 확인


# ============================================================================
# StaticFiles - 단일 정적 파일 서버
# ============================================================================


class StaticFiles:
    """
    정적 파일 서버

    지정된 디렉토리의 파일을 HTTP로 서빙합니다.
    보안을 위해 디렉토리 외부 접근(path traversal)을 방지합니다.

    사용 예시:
        static = StaticFiles("public", path_prefix="/static")

        # 요청 처리
        response = await static.handle_request(request)

    특징:
        - Path traversal 공격 방지 (../ 등)
        - MIME 타입 자동 감지
        - index.html 자동 서빙 (html=True)
        - ETag/Last-Modified 캐싱 헤더
    """

    def __init__(
        self,
        directory: str | Path,
        path_prefix: str = "/static",
        html: bool = False,
        check_exists: bool = True,
    ):
        """
        Args:
            directory: 서빙할 디렉토리 경로
            path_prefix: URL 경로 프리픽스 (예: "/static")
            html: True면 디렉토리 접근 시 index.html 자동 서빙
            check_exists: True면 초기화 시 디렉토리 존재 확인
        """
        self.directory = Path(directory).resolve()
        self.path_prefix = path_prefix.rstrip("/")
        self.html = html

        if check_exists and not self.directory.is_dir():
            raise ValueError(f"Directory does not exist: {self.directory}")

    def _get_file_path(self, request_path: str) -> Path | None:
        """
        요청 경로에서 실제 파일 경로 반환

        Path traversal 공격 방지를 위해 resolved 경로가
        base directory 내에 있는지 확인합니다.
        """
        # 프리픽스 제거
        if not request_path.startswith(self.path_prefix):
            return None

        relative_path = request_path[len(self.path_prefix) :].lstrip("/")

        # 빈 경로면 index.html 시도 (html=True인 경우)
        if not relative_path and self.html:
            relative_path = "index.html"

        if not relative_path:
            return None

        # 실제 파일 경로 계산
        file_path = (self.directory / relative_path).resolve()

        # Path traversal 방지: 파일이 base directory 내에 있는지 확인
        try:
            file_path.relative_to(self.directory)
        except ValueError:
            # 디렉토리 외부 접근 시도
            return None

        # 디렉토리인 경우 index.html 시도
        if file_path.is_dir() and self.html:
            index_path = file_path / "index.html"
            if index_path.is_file():
                return index_path
            return None

        # 파일 존재 확인
        if not file_path.is_file():
            return None

        return file_path

    def _get_content_type(self, file_path: Path) -> str:
        """파일의 MIME 타입 반환"""
        content_type, _ = mimetypes.guess_type(str(file_path))
        return content_type or "application/octet-stream"

    def _get_file_stats(self, file_path: Path) -> dict:
        """파일 메타데이터 반환"""
        stat = file_path.stat()
        return {
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "etag": f'"{stat.st_mtime}-{stat.st_size}"',
        }

    async def handle_request(
        self, request: "HttpRequest"
    ) -> "HttpResponse | FileResponse | None":
        """
        정적 파일 요청 처리

        Args:
            request: HTTP 요청 객체

        Returns:
            HttpResponse 또는 None (해당 경로가 아닌 경우)
        """
        from .http import HttpResponse, FileResponse

        # GET, HEAD만 허용
        if request.method not in ("GET", "HEAD"):
            return None

        # 파일 경로 확인
        file_path = self._get_file_path(request.path)
        if file_path is None:
            return None

        # 파일 메타데이터
        try:
            stats = self._get_file_stats(file_path)
        except (OSError, IOError):
            return HttpResponse.not_found("File not found")

        content_type = self._get_content_type(file_path)

        # ETag 캐싱 확인
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and if_none_match == stats["etag"]:
            return HttpResponse(status_code=304, headers={"ETag": stats["etag"]})

        # HEAD 요청은 메타데이터만 반환
        if request.method == "HEAD":
            return HttpResponse(
                status_code=200,
                headers={
                    "Content-Type": content_type,
                    "Content-Length": str(stats["size"]),
                    "ETag": stats["etag"],
                },
            )

        # 파일 응답 생성
        response = FileResponse(
            file=file_path,
            content_type=content_type,
            attachment=False,  # inline으로 서빙
        )

        # 캐싱 헤더 추가
        response.headers["ETag"] = stats["etag"]
        response.headers["Cache-Control"] = "public, max-age=3600"  # 1시간 캐시

        return response

    def matches(self, path: str) -> bool:
        """주어진 경로가 이 정적 파일 핸들러와 매칭되는지 확인"""
        # 정확한 프리픽스 매칭: /static과 /static/... 만 매칭, /staticfiles는 제외
        if path == self.path_prefix:
            return True
        return path.startswith(self.path_prefix + "/")


# ============================================================================
# StaticFilesContainer - StaticFiles 인스턴스들을 담는 컨테이너
# ============================================================================


class StaticFilesContainer:
    """
    StaticFiles 인스턴스들을 담는 컨테이너

    @Factory로 생성하여 DI 컨테이너에 등록하면
    StaticFilesManager가 자동으로 수집하여 사용합니다.

    사용 예시:
        @Component
        class StaticConfig:
            @Factory
            def static_files_container(self) -> StaticFilesContainer:
                container = StaticFilesContainer()
                container.add("/static", "public")
                container.add("/assets", "assets", html=True)
                container.add("/", "dist", html=True)  # SPA용
                return container
    """

    def __init__(self):
        self._static_files: list[StaticFiles] = []

    def add(
        self,
        path_prefix: str,
        directory: str | Path,
        html: bool = False,
        check_exists: bool = True,
    ) -> "StaticFilesContainer":
        """
        정적 파일 디렉토리 추가

        Args:
            path_prefix: URL 경로 프리픽스 (예: "/static")
            directory: 서빙할 디렉토리 경로
            html: True면 디렉토리 접근 시 index.html 자동 서빙
            check_exists: 디렉토리 존재 확인 여부

        Returns:
            self (메서드 체이닝 지원)
        """
        static = StaticFiles(
            directory=directory,
            path_prefix=path_prefix,
            html=html,
            check_exists=check_exists,
        )
        self._static_files.append(static)
        return self

    def add_static(self, static_files: StaticFiles) -> "StaticFilesContainer":
        """
        StaticFiles 인스턴스 직접 추가

        Args:
            static_files: StaticFiles 인스턴스

        Returns:
            self (메서드 체이닝 지원)
        """
        self._static_files.append(static_files)
        return self

    @property
    def static_files(self) -> list[StaticFiles]:
        """등록된 StaticFiles 목록 반환"""
        return self._static_files.copy()

    def __iter__(self):
        """StaticFiles 인스턴스들을 순회"""
        return iter(self._static_files)

    def __len__(self) -> int:
        """등록된 StaticFiles 수"""
        return len(self._static_files)


# ============================================================================
# StaticFilesManager - StaticFilesContainer들을 수집하여 관리
# ============================================================================


class StaticFilesManager:
    """
    StaticFilesContainer들을 수집하여 정적 파일 요청을 처리하는 매니저

    ContainerManager에서 @Factory로 등록된 StaticFilesContainer를
    자동으로 수집하여 사용합니다.

    사용 예시:
        # 자동 수집 (권장)
        manager = StaticFilesManager()
        manager.collect_from_container(container_manager)

        # 수동 마운트
        manager.mount("/static", "public")

        # 요청 처리
        response = await manager.handle_request(request)
    """

    def __init__(self):
        self._mounts: list[StaticFiles] = []
        self._collected = False

    def collect_from_container(
        self, container_manager: "ContainerManager"
    ) -> "StaticFilesManager":
        """
        ContainerManager에서 StaticFilesContainer 인스턴스를 수집

        @Factory로 등록된 StaticFilesContainer를 찾아서
        그 안의 StaticFiles들을 수집합니다.

        주의: StaticFilesContainer는 하나만 등록할 수 있습니다.
        여러 개가 등록되면 에러가 발생합니다.

        Args:
            container_manager: DI 컨테이너 매니저

        Returns:
            self (메서드 체이닝 지원)

        Raises:
            RuntimeError: StaticFilesContainer가 2개 이상 등록된 경우
        """
        if self._collected:
            return self

        # StaticFilesContainer 타입의 인스턴스 조회
        try:
            # get_sub_instances로 StaticFilesContainer와 그 서브클래스 인스턴스들 조회
            containers = container_manager.get_sub_instances(StaticFilesContainer)

            if len(containers) > 1:
                raise RuntimeError(
                    f"Multiple StaticFilesContainer instances found ({len(containers)}). "
                    "Only one StaticFilesContainer is allowed. "
                    "Please merge all static file configurations into a single @Factory method."
                )

            for container in containers:
                for static_files in container:
                    self._mounts.append(static_files)
        except RuntimeError:
            # RuntimeError는 그대로 전파
            raise
        except Exception:
            # 다른 예외는 무시 (StaticFilesContainer가 없는 경우 등)
            pass

        self._collected = True
        return self

    def mount(
        self,
        path_prefix: str,
        directory: str | Path,
        html: bool = False,
        check_exists: bool = True,
    ) -> "StaticFilesManager":
        """
        정적 파일 디렉토리 직접 마운트

        Args:
            path_prefix: URL 경로 프리픽스
            directory: 서빙할 디렉토리
            html: index.html 자동 서빙 여부
            check_exists: 디렉토리 존재 확인 여부

        Returns:
            self (메서드 체이닝 지원)
        """
        static = StaticFiles(
            directory=directory,
            path_prefix=path_prefix,
            html=html,
            check_exists=check_exists,
        )
        self._mounts.append(static)
        return self

    async def handle_request(
        self, request: "HttpRequest"
    ) -> "HttpResponse | FileResponse | None":
        """
        정적 파일 요청 처리

        등록된 순서대로 매칭되는 핸들러를 찾아 처리합니다.

        Returns:
            HttpResponse 또는 None (매칭되는 핸들러 없음)
        """
        for static in self._mounts:
            if static.matches(request.path):
                response = await static.handle_request(request)
                if response is not None:
                    return response
        return None

    def matches(self, path: str) -> bool:
        """주어진 경로가 정적 파일 핸들러와 매칭되는지 확인"""
        return any(static.matches(path) for static in self._mounts)

    @property
    def mounts(self) -> list[StaticFiles]:
        """등록된 모든 StaticFiles 반환"""
        return self._mounts.copy()


__all__ = [
    "StaticFiles",
    "StaticFilesContainer",
    "StaticFilesManager",
    "StaticFileConfig",
]
