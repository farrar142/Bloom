"""정적 파일 서빙 테스트"""

import os
import tempfile
import pytest
from pathlib import Path

from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.web import Controller, Get
from bloom.web.static import StaticFiles, StaticFilesContainer, StaticFilesManager
from bloom.web.http import HttpRequest


class TestStaticFiles:
    """StaticFiles 클래스 테스트"""

    def test_init_with_valid_directory(self, tmp_path):
        """유효한 디렉토리로 초기화"""
        static = StaticFiles(tmp_path, path_prefix="/static")
        assert static.directory == tmp_path
        assert static.path_prefix == "/static"

    def test_init_with_invalid_directory(self):
        """존재하지 않는 디렉토리로 초기화 시 에러"""
        with pytest.raises(ValueError, match="Directory does not exist"):
            StaticFiles("/nonexistent/path", check_exists=True)

    def test_init_skip_directory_check(self):
        """디렉토리 존재 확인 비활성화"""
        # check_exists=False면 에러 없이 생성
        static = StaticFiles("/nonexistent/path", check_exists=False)
        assert static.path_prefix == "/static"

    def test_path_prefix_trailing_slash(self, tmp_path):
        """경로 프리픽스 끝의 슬래시 제거"""
        static = StaticFiles(tmp_path, path_prefix="/static/")
        assert static.path_prefix == "/static"

    @pytest.mark.asyncio
    async def test_serve_file(self, tmp_path):
        """파일 서빙 테스트"""
        # 테스트 파일 생성
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        static = StaticFiles(tmp_path, path_prefix="/static")
        request = HttpRequest(method="GET", path="/static/test.txt")

        response = await static.handle_request(request)
        assert response is not None
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_serve_file_not_found(self, tmp_path):
        """존재하지 않는 파일 요청"""
        static = StaticFiles(tmp_path, path_prefix="/static")
        request = HttpRequest(method="GET", path="/static/nonexistent.txt")

        response = await static.handle_request(request)
        assert response is None  # 파일이 없으면 None 반환

    @pytest.mark.asyncio
    async def test_path_traversal_prevention(self, tmp_path):
        """Path traversal 공격 방지"""
        # 상위 디렉토리에 파일 생성
        parent_file = tmp_path.parent / "secret.txt"
        parent_file.write_text("Secret data")

        try:
            static = StaticFiles(tmp_path, path_prefix="/static")

            # ../ 경로로 상위 디렉토리 접근 시도
            request = HttpRequest(method="GET", path="/static/../secret.txt")
            response = await static.handle_request(request)
            assert response is None  # 접근 거부
        finally:
            if parent_file.exists():
                parent_file.unlink()

    @pytest.mark.asyncio
    async def test_serve_nested_file(self, tmp_path):
        """중첩 디렉토리의 파일 서빙"""
        nested_dir = tmp_path / "assets" / "css"
        nested_dir.mkdir(parents=True)
        css_file = nested_dir / "style.css"
        css_file.write_text("body { color: red; }")

        static = StaticFiles(tmp_path, path_prefix="/static")
        request = HttpRequest(method="GET", path="/static/assets/css/style.css")

        response = await static.handle_request(request)
        assert response is not None
        assert response.content_type == "text/css"

    @pytest.mark.asyncio
    async def test_content_type_detection(self, tmp_path):
        """MIME 타입 자동 감지"""
        # 다양한 파일 타입 테스트
        files = {
            "test.html": "text/html",
            "test.css": "text/css",
            "test.js": "text/javascript",
            "test.json": "application/json",
            "test.png": "image/png",
            "test.jpg": "image/jpeg",
        }

        static = StaticFiles(tmp_path, path_prefix="/static")

        for filename, expected_type in files.items():
            test_file = tmp_path / filename
            test_file.write_bytes(b"test content")

            request = HttpRequest(method="GET", path=f"/static/{filename}")
            response = await static.handle_request(request)

            # application/javascript도 허용 (시스템에 따라 다름)
            if expected_type == "text/javascript":
                assert response.content_type in (
                    "text/javascript",
                    "application/javascript",
                )
            else:
                assert response.content_type == expected_type

    @pytest.mark.asyncio
    async def test_index_html_serving(self, tmp_path):
        """html=True일 때 index.html 자동 서빙"""
        index_file = tmp_path / "index.html"
        index_file.write_text("<html><body>Hello</body></html>")

        static = StaticFiles(tmp_path, path_prefix="/static", html=True)

        # 루트 경로 요청
        request = HttpRequest(method="GET", path="/static")
        response = await static.handle_request(request)
        assert response is not None
        assert response.content_type == "text/html"

    @pytest.mark.asyncio
    async def test_subdirectory_index_html(self, tmp_path):
        """서브 디렉토리의 index.html 자동 서빙"""
        sub_dir = tmp_path / "docs"
        sub_dir.mkdir()
        index_file = sub_dir / "index.html"
        index_file.write_text("<html><body>Docs</body></html>")

        static = StaticFiles(tmp_path, path_prefix="/static", html=True)

        request = HttpRequest(method="GET", path="/static/docs")
        response = await static.handle_request(request)
        assert response is not None
        assert response.content_type == "text/html"

    @pytest.mark.asyncio
    async def test_etag_caching(self, tmp_path):
        """ETag 캐싱 테스트"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        static = StaticFiles(tmp_path, path_prefix="/static")

        # 첫 번째 요청
        request1 = HttpRequest(method="GET", path="/static/test.txt")
        response1 = await static.handle_request(request1)
        etag = response1.headers.get("ETag")
        assert etag is not None

        # ETag를 포함한 두 번째 요청
        request2 = HttpRequest(
            method="GET",
            path="/static/test.txt",
            headers={"if-none-match": etag},
        )
        response2 = await static.handle_request(request2)
        assert response2.status_code == 304  # Not Modified

    @pytest.mark.asyncio
    async def test_head_request(self, tmp_path):
        """HEAD 요청 처리"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        static = StaticFiles(tmp_path, path_prefix="/static")
        request = HttpRequest(method="HEAD", path="/static/test.txt")

        response = await static.handle_request(request)
        assert response is not None
        assert response.status_code == 200
        assert "Content-Length" in response.headers
        assert response.body is None  # HEAD는 바디 없음

    @pytest.mark.asyncio
    async def test_post_request_ignored(self, tmp_path):
        """POST 요청은 무시"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        static = StaticFiles(tmp_path, path_prefix="/static")
        request = HttpRequest(method="POST", path="/static/test.txt")

        response = await static.handle_request(request)
        assert response is None  # POST는 처리하지 않음

    def test_matches_path(self, tmp_path):
        """경로 매칭 테스트"""
        static = StaticFiles(tmp_path, path_prefix="/static")

        assert static.matches("/static") is True
        assert static.matches("/static/file.txt") is True
        assert static.matches("/static/sub/file.txt") is True
        assert static.matches("/api/data") is False
        assert static.matches("/staticfiles") is False  # 완전히 다른 경로


class TestStaticFilesManager:
    """StaticFilesManager 테스트"""

    @pytest.mark.asyncio
    async def test_multiple_mounts(self, tmp_path):
        """여러 디렉토리 마운트"""
        static_dir = tmp_path / "static"
        assets_dir = tmp_path / "assets"
        static_dir.mkdir()
        assets_dir.mkdir()

        (static_dir / "main.js").write_text("console.log('main');")
        (assets_dir / "logo.png").write_bytes(b"PNG data")

        manager = StaticFilesManager()
        manager.mount("/static", static_dir)
        manager.mount("/assets", assets_dir)

        # /static 경로
        request1 = HttpRequest(method="GET", path="/static/main.js")
        response1 = await manager.handle_request(request1)
        assert response1 is not None

        # /assets 경로
        request2 = HttpRequest(method="GET", path="/assets/logo.png")
        response2 = await manager.handle_request(request2)
        assert response2 is not None

    @pytest.mark.asyncio
    async def test_no_match(self, tmp_path):
        """매칭되는 마운트 없음"""
        manager = StaticFilesManager()
        manager.mount("/static", tmp_path)

        request = HttpRequest(method="GET", path="/api/data")
        response = await manager.handle_request(request)
        assert response is None

    def test_method_chaining(self, tmp_path):
        """메서드 체이닝 테스트"""
        static_dir = tmp_path / "static"
        assets_dir = tmp_path / "assets"
        static_dir.mkdir()
        assets_dir.mkdir()

        manager = (
            StaticFilesManager()
            .mount("/static", static_dir)
            .mount("/assets", assets_dir, html=True)
        )

        assert manager.matches("/static/file.js")
        assert manager.matches("/assets/index.html")


class TestStaticFilesContainer:
    """StaticFilesContainer 테스트"""

    def test_container_add(self, tmp_path):
        """Container에 StaticFiles 추가"""
        static_dir = tmp_path / "static"
        static_dir.mkdir()

        container = StaticFilesContainer()
        result = container.add("/static", static_dir)

        assert result is container  # 체이닝 반환
        assert len(container.static_files) == 1
        assert container.static_files[0].path_prefix == "/static"

    def test_container_multiple_add(self, tmp_path):
        """Container에 여러 StaticFiles 추가"""
        static_dir = tmp_path / "static"
        assets_dir = tmp_path / "assets"
        static_dir.mkdir()
        assets_dir.mkdir()

        container = (
            StaticFilesContainer()
            .add("/static", static_dir)
            .add("/assets", assets_dir, html=True)
        )

        assert len(container.static_files) == 2
        assert container.static_files[0].path_prefix == "/static"
        assert container.static_files[1].path_prefix == "/assets"
        assert container.static_files[1].html is True

    def test_collect_from_container(self, reset_container_manager, tmp_path):
        """DI Container에서 StaticFilesContainer 수집"""
        static_dir = tmp_path / "public"
        assets_dir = tmp_path / "assets"
        static_dir.mkdir()
        assets_dir.mkdir()

        @Component
        class StaticConfig:
            @Factory
            def static_files_container(self) -> StaticFilesContainer:
                # 하나의 Factory에서 여러 경로 등록
                return (
                    StaticFilesContainer()
                    .add("/static", static_dir)
                    .add("/assets", assets_dir, html=True)
                )

        app = Application("test").scan(__import__(__name__)).ready()

        manager = StaticFilesManager()
        manager.collect_from_container(app.manager)

        # 두 개의 StaticFiles가 수집되어야 함
        assert len(manager._mounts) == 2
        assert manager.matches("/static/file.txt")
        assert manager.matches("/assets/index.html")

    def test_multiple_containers_raises_error(self, reset_container_manager, tmp_path):
        """여러 StaticFilesContainer가 있으면 에러 발생"""
        static_dir = tmp_path / "public"
        assets_dir = tmp_path / "assets"
        static_dir.mkdir()
        assets_dir.mkdir()

        @Component
        class BadStaticConfig:
            @Factory
            def first_container(self) -> StaticFilesContainer:
                return StaticFilesContainer().add("/static", static_dir)

            @Factory
            def second_container(self) -> StaticFilesContainer:
                return StaticFilesContainer().add("/assets", assets_dir)

        app = Application("test").scan(__import__(__name__)).ready()

        manager = StaticFilesManager()
        with pytest.raises(RuntimeError, match="Multiple StaticFilesContainer"):
            manager.collect_from_container(app.manager)

    def test_collect_empty_container(self, reset_container_manager):
        """StaticFilesContainer가 없을 때"""

        @Component
        class EmptyConfig:
            pass

        app = Application("test").scan(__import__(__name__)).ready()

        manager = StaticFilesManager()
        manager.collect_from_container(app.manager)

        assert len(manager._mounts) == 0


class TestASGIStaticFiles:
    """ASGIApplication 정적 파일 통합 테스트"""

    @pytest.mark.asyncio
    async def test_asgi_mount_static(self, reset_container_manager, tmp_path):
        """ASGIApplication.mount_static() 테스트"""
        # 테스트 파일 생성
        static_dir = tmp_path / "public"
        static_dir.mkdir()
        (static_dir / "test.txt").write_text("Hello from static!")

        @Controller
        class ApiController:
            @Get("/api/health")
            def health(self):
                return {"status": "ok"}

        app = Application("test").scan(__import__(__name__)).ready()
        app.asgi.mount_static("/static", str(static_dir))

        # 정적 파일 매니저가 설정되었는지 확인
        assert app.asgi._static_files_manager is not None
        assert app.asgi._static_files_manager.matches("/static/test.txt")

    @pytest.mark.asyncio
    async def test_asgi_static_takes_precedence(
        self, reset_container_manager, tmp_path
    ):
        """정적 파일이 라우터보다 먼저 처리되는지 확인"""
        static_dir = tmp_path / "public"
        static_dir.mkdir()
        (static_dir / "data.json").write_text('{"source": "static"}')

        @Controller
        class ApiController:
            @Get("/static/data.json")
            def data(self):
                return {"source": "api"}

        app = Application("test").scan(__import__(__name__)).ready()
        app.asgi.mount_static("/static", str(static_dir))

        # 정적 파일이 우선순위를 가지므로 static 파일이 서빙되어야 함
        from bloom.web.http import HttpRequest

        request = HttpRequest(method="GET", path="/static/data.json")
        response = await app.asgi._static_files_manager.handle_request(request)

        # 정적 파일에서 응답 확인
        assert response is not None

    def test_mount_static_chaining(self, reset_container_manager, tmp_path):
        """mount_static 메서드 체이닝"""
        dir1 = tmp_path / "static"
        dir2 = tmp_path / "assets"
        dir1.mkdir()
        dir2.mkdir()

        @Controller
        class DummyController:
            pass

        app = Application("test").scan(__import__(__name__)).ready()

        result = app.asgi.mount_static("/static", str(dir1)).mount_static(
            "/assets", str(dir2)
        )

        assert result is app.asgi  # 체이닝 가능
        assert app.asgi._static_files_manager.matches("/static/file.txt")
        assert app.asgi._static_files_manager.matches("/assets/image.png")
