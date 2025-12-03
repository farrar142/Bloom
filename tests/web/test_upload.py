"""파일 업로드 테스트"""

import pytest
import tempfile
import os
from pathlib import Path

from bloom.web.upload import (
    UploadedFile,
    MultipartParser,
    parse_multipart,
    create_uploaded_file,
)
from bloom.web import Request


# === Test Utilities ===


class MockReceive:
    def __init__(self, body: bytes = b""):
        self.body = body
        self._sent = False

    async def __call__(self):
        if not self._sent:
            self._sent = True
            return {"type": "http.request", "body": self.body, "more_body": False}
        return {"type": "http.disconnect"}


def make_request(
    method: str = "POST",
    path: str = "/",
    content_type: str = "",
    body: bytes = b"",
) -> Request:
    headers = []
    if content_type:
        headers.append((b"content-type", content_type.encode()))
    if body:
        headers.append((b"content-length", str(len(body)).encode()))

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers,
    }
    return Request(scope, MockReceive(body))


def create_multipart_body(boundary: str, parts: list[dict]) -> bytes:
    """멀티파트 바디 생성 헬퍼

    Args:
        boundary: 경계 문자열
        parts: [{"name": "...", "filename": "...", "content_type": "...", "content": bytes}]
    """
    body_parts = []
    for part in parts:
        headers = f'Content-Disposition: form-data; name="{part["name"]}"'
        if "filename" in part:
            headers += f'; filename="{part["filename"]}"'
        headers += "\r\n"
        if "content_type" in part:
            headers += f'Content-Type: {part["content_type"]}\r\n'
        headers += "\r\n"

        body_parts.append(
            f"--{boundary}\r\n{headers}".encode() + part.get("content", b"")
        )

    body = b"\r\n".join(body_parts)
    body += f"\r\n--{boundary}--\r\n".encode()
    return body


# === UploadedFile Tests ===


class TestUploadedFile:
    """UploadedFile 테스트"""

    def test_create_uploaded_file(self):
        """UploadedFile 생성"""
        content = b"Hello, World!"
        file = create_uploaded_file(
            filename="test.txt", content=content, content_type="text/plain"
        )

        assert file.filename == "test.txt"
        assert file.content_type == "text/plain"
        assert file.size == len(content)

    def test_read_file(self):
        """파일 내용 읽기"""
        content = b"Test content"
        file = create_uploaded_file(filename="test.txt", content=content)

        # 전체 읽기
        assert file.read() == content

        # seek 후 다시 읽기
        file.seek(0)
        assert file.read() == content

        # 부분 읽기
        file.seek(0)
        assert file.read(4) == b"Test"

    @pytest.mark.asyncio
    async def test_async_read(self):
        """비동기 파일 읽기"""
        content = b"Async test content"
        file = create_uploaded_file(filename="test.txt", content=content)

        result = await file.aread()
        assert result == content

    @pytest.mark.asyncio
    async def test_save_file(self):
        """파일 저장"""
        content = b"Save test content"
        file = create_uploaded_file(filename="test.txt", content=content)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "saved.txt"
            await file.save(str(path))

            assert path.exists()
            assert path.read_bytes() == content

    @pytest.mark.asyncio
    async def test_save_temp(self):
        """임시 파일 저장"""
        content = b"Temp save test"
        file = create_uploaded_file(filename="test.txt", content=content)

        temp_path = await file.save_temp(suffix=".txt")
        try:
            assert os.path.exists(temp_path)
            with open(temp_path, "rb") as f:
                assert f.read() == content
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_file_properties(self):
        """파일 속성"""
        file = create_uploaded_file(
            filename="image.png",
            content=b"\x89PNG\r\n\x1a\n",
            content_type="image/png",
        )

        assert file.filename == "image.png"
        assert file.content_type == "image/png"
        assert file.size == 8


# === MultipartParser Tests ===


class TestMultipartParser:
    """MultipartParser 테스트"""

    @pytest.mark.asyncio
    async def test_parse_simple_file(self):
        """단일 파일 파싱"""
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = create_multipart_body(
            boundary,
            [
                {
                    "name": "file",
                    "filename": "test.txt",
                    "content_type": "text/plain",
                    "content": b"Hello, World!",
                }
            ],
        )

        content_type = f"multipart/form-data; boundary={boundary}"
        request = make_request(content_type=content_type, body=body)

        fields, files = await parse_multipart(request)

        assert len(files) == 1
        assert "file" in files
        assert files["file"].filename == "test.txt"
        assert files["file"].read() == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_parse_multiple_files(self):
        """여러 파일 파싱"""
        boundary = "----Boundary123"
        body = create_multipart_body(
            boundary,
            [
                {
                    "name": "file1",
                    "filename": "test1.txt",
                    "content_type": "text/plain",
                    "content": b"Content 1",
                },
                {
                    "name": "file2",
                    "filename": "test2.txt",
                    "content_type": "text/plain",
                    "content": b"Content 2",
                },
            ],
        )

        content_type = f"multipart/form-data; boundary={boundary}"
        request = make_request(content_type=content_type, body=body)

        fields, files = await parse_multipart(request)

        assert len(files) == 2
        assert files["file1"].read() == b"Content 1"
        assert files["file2"].read() == b"Content 2"

    @pytest.mark.asyncio
    async def test_parse_form_fields(self):
        """폼 필드 파싱"""
        boundary = "----FormBoundary"
        body = create_multipart_body(
            boundary,
            [
                {
                    "name": "username",
                    "content": b"testuser",
                },
                {
                    "name": "email",
                    "content": b"test@example.com",
                },
            ],
        )

        content_type = f"multipart/form-data; boundary={boundary}"
        request = make_request(content_type=content_type, body=body)

        fields, files = await parse_multipart(request)

        assert len(fields) == 2
        assert fields["username"] == "testuser"
        assert fields["email"] == "test@example.com"
        assert len(files) == 0

    @pytest.mark.asyncio
    async def test_parse_mixed_content(self):
        """파일과 폼 필드 혼합"""
        boundary = "----MixedBoundary"
        body = create_multipart_body(
            boundary,
            [
                {
                    "name": "title",
                    "content": b"My Upload",
                },
                {
                    "name": "document",
                    "filename": "doc.pdf",
                    "content_type": "application/pdf",
                    "content": b"%PDF-1.4 fake content",
                },
            ],
        )

        content_type = f"multipart/form-data; boundary={boundary}"
        request = make_request(content_type=content_type, body=body)

        fields, files = await parse_multipart(request)

        assert fields["title"] == "My Upload"
        assert files["document"].filename == "doc.pdf"


# === Integration Tests ===


class TestUploadIntegration:
    """업로드 통합 테스트"""

    @pytest.mark.asyncio
    async def test_large_file_handling(self):
        """큰 파일 처리"""
        # 1MB 파일
        content = b"x" * (1024 * 1024)
        file = create_uploaded_file(filename="large.bin", content=content)

        assert file.size == 1024 * 1024

        # 청크 단위로 읽기
        chunks = []
        chunk_size = 65536
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)

        assert b"".join(chunks) == content

    @pytest.mark.asyncio
    async def test_file_close(self):
        """파일 닫기"""
        file = create_uploaded_file(filename="test.txt", content=b"test")

        # 파일은 열려 있음
        assert file.read() == b"test"

        # 닫은 후에도 안전하게 처리
        file.close()
