"""bloom.web.upload - 파일 업로드 처리"""

from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, BinaryIO, TYPE_CHECKING

if TYPE_CHECKING:
    from .request import HttpRequest


@dataclass
class UploadedFile:
    """
    업로드된 파일 객체.

    multipart/form-data로 업로드된 파일을 표현합니다.
    파일 IO 인터페이스를 제공하여 읽기/쓰기가 가능합니다.

    사용 예:
        @PostMapping("/upload")
        async def upload(file: UploadedFile):
            content = await file.read()
            await file.save("/path/to/save")
            return {"filename": file.filename, "size": file.size}
    """

    filename: str
    """원본 파일명"""

    content_type: str = "application/octet-stream"
    """파일의 Content-Type"""

    headers: dict[str, str] = field(default_factory=dict)
    """파일 파트의 헤더"""

    _file: BinaryIO = field(default_factory=lambda: io.BytesIO())
    """내부 파일 객체"""

    _size: int | None = None
    """파일 크기 (캐싱)"""

    # === File-like Interface ===

    def read(self, size: int = -1) -> bytes:
        """파일 읽기"""
        return self._file.read(size)

    def write(self, data: bytes) -> int:
        """파일 쓰기"""
        return self._file.write(data)

    def seek(self, offset: int, whence: int = 0) -> int:
        """파일 위치 이동"""
        return self._file.seek(offset, whence)

    def tell(self) -> int:
        """현재 파일 위치"""
        return self._file.tell()

    def close(self) -> None:
        """파일 닫기"""
        self._file.close()

    # === Properties ===

    @property
    def size(self) -> int:
        """파일 크기 (bytes)"""
        if self._size is None:
            current_pos = self._file.tell()
            self._file.seek(0, 2)  # EOF
            self._size = self._file.tell()
            self._file.seek(current_pos)
        return self._size

    @property
    def extension(self) -> str:
        """파일 확장자 (점 포함, 예: .jpg)"""
        _, ext = os.path.splitext(self.filename)
        return ext.lower()

    # === Async Methods ===

    async def aread(self, size: int = -1) -> bytes:
        """비동기 파일 읽기 (현재는 동기 래퍼)"""
        return self.read(size)

    async def awrite(self, data: bytes) -> int:
        """비동기 파일 쓰기 (현재는 동기 래퍼)"""
        return self.write(data)

    async def save(self, path: str) -> int:
        """
        파일을 지정된 경로에 저장.

        Args:
            path: 저장할 파일 경로

        Returns:
            저장된 바이트 수
        """
        self.seek(0)
        content = self.read()

        with open(path, "wb") as f:
            return f.write(content)

    async def save_temp(self, suffix: str | None = None, delete: bool = False) -> str:
        """
        임시 파일로 저장.

        Args:
            suffix: 파일 확장자 (예: '.jpg')
            delete: 닫을 때 자동 삭제 여부

        Returns:
            임시 파일 경로
        """
        if suffix is None:
            suffix = self.extension

        self.seek(0)
        content = self.read()

        fd, path = tempfile.mkstemp(suffix=suffix)
        try:
            os.write(fd, content)
        finally:
            os.close(fd)

        return path

    # === Context Manager ===

    def __enter__(self) -> "UploadedFile":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    async def __aenter__(self) -> "UploadedFile":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # === Iteration ===

    def __iter__(self):
        """청크 단위 반복"""
        self.seek(0)
        while True:
            chunk = self.read(8192)  # 8KB chunks
            if not chunk:
                break
            yield chunk

    async def __aiter__(self):
        """비동기 청크 단위 반복"""
        self.seek(0)
        while True:
            chunk = self.read(8192)
            if not chunk:
                break
            yield chunk

    def __repr__(self) -> str:
        return f"<UploadedFile {self.filename!r} ({self.size} bytes)>"


class MultipartParser:
    """
    multipart/form-data 파서.

    RFC 7578 기반으로 multipart 요청을 파싱합니다.
    """

    def __init__(self, content_type: str, body: bytes) -> None:
        self.content_type = content_type
        self.body = body
        self.boundary = self._extract_boundary()

    def _extract_boundary(self) -> bytes:
        """Content-Type에서 boundary 추출"""
        for part in self.content_type.split(";"):
            part = part.strip()
            if part.startswith("boundary="):
                boundary = part[9:]
                # 따옴표 제거
                if boundary.startswith('"') and boundary.endswith('"'):
                    boundary = boundary[1:-1]
                return boundary.encode("utf-8")
        raise ValueError("No boundary found in Content-Type")

    def parse(self) -> tuple[dict[str, str], dict[str, UploadedFile]]:
        """
        multipart 본문 파싱.

        Returns:
            (form_fields, files) 튜플
            - form_fields: 일반 폼 필드 {name: value}
            - files: 파일 필드 {name: UploadedFile}
        """
        form_fields: dict[str, str] = {}
        files: dict[str, UploadedFile] = {}

        # 파트 분리
        delimiter = b"--" + self.boundary
        parts = self.body.split(delimiter)

        for part in parts:
            # 빈 파트, 종료 마커 스킵
            part = part.strip(b"\r\n")
            if not part or part == b"--":
                continue

            # 헤더와 본문 분리
            if b"\r\n\r\n" in part:
                header_section, body = part.split(b"\r\n\r\n", 1)
            elif b"\n\n" in part:
                header_section, body = part.split(b"\n\n", 1)
            else:
                continue

            # 헤더 파싱
            headers = self._parse_headers(
                header_section.decode("utf-8", errors="replace")
            )

            # Content-Disposition에서 name, filename 추출
            disposition = headers.get("content-disposition", "")
            name = self._extract_param(disposition, "name")
            filename = self._extract_param(disposition, "filename")

            if not name:
                continue

            # 파일인지 일반 필드인지 구분
            if filename:
                content_type = headers.get("content-type", "application/octet-stream")
                file_obj = io.BytesIO(body)
                uploaded_file = UploadedFile(
                    filename=filename,
                    content_type=content_type,
                    headers=headers,
                    _file=file_obj,
                )
                files[name] = uploaded_file
            else:
                # 일반 폼 필드
                form_fields[name] = body.decode("utf-8", errors="replace")

        return form_fields, files

    def _parse_headers(self, header_section: str) -> dict[str, str]:
        """헤더 섹션 파싱"""
        headers: dict[str, str] = {}
        for line in header_section.split("\n"):
            line = line.strip("\r")
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        return headers

    def _extract_param(self, header: str, param_name: str) -> str | None:
        """헤더에서 파라미터 값 추출 (예: name="field1")"""
        import re

        # name="value" 또는 name=value 패턴 매칭
        pattern = rf'{param_name}=(?:"([^"]*)"|([^;\s]*))'
        match = re.search(pattern, header)
        if match:
            return match.group(1) or match.group(2)
        return None


async def parse_multipart(
    request: "HttpRequest",
) -> tuple[dict[str, str], dict[str, UploadedFile]]:
    """
    요청에서 multipart/form-data 파싱.

    Args:
        request: HTTP 요청 객체

    Returns:
        (form_fields, files) 튜플

    사용 예:
        fields, files = await parse_multipart(request)
        file = files.get("upload")
        if file:
            await file.save("/uploads/" + file.filename)
    """
    content_type = request.content_type
    if not content_type or "multipart/form-data" not in content_type:
        raise ValueError("Content-Type must be multipart/form-data")

    body = await request.body()
    parser = MultipartParser(content_type, body)
    return parser.parse()


# === Convenience Functions ===


def create_uploaded_file(
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> UploadedFile:
    """
    테스트용 UploadedFile 생성 헬퍼.

    Args:
        filename: 파일명
        content: 파일 내용
        content_type: MIME 타입

    Returns:
        UploadedFile 인스턴스
    """
    file_obj = io.BytesIO(content)
    return UploadedFile(
        filename=filename,
        content_type=content_type,
        _file=file_obj,
    )
