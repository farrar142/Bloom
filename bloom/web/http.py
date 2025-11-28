"""HTTP 요청/응답 모델"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from io import IOBase, BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, BinaryIO

if TYPE_CHECKING:
    from bloom.web.auth import Authentication
    from bloom.web.params.types import UploadedFile

# 스트리밍 제너레이터 타입
StreamGenerator = AsyncIterator[bytes | str]


@dataclass
class HttpRequest:
    """HTTP 요청 객체"""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    files: dict[str, list[UploadedFile]] = field(default_factory=dict)
    auth: "Authentication | None" = None

    @property
    def json(self) -> Any:
        """JSON 바디 파싱"""
        import json

        if self.body:
            return json.loads(self.body.decode("utf-8"))
        return None

    @property
    def text(self) -> str:
        """텍스트 바디"""
        return self.body.decode("utf-8") if self.body else ""


@dataclass
class HttpResponse:
    """HTTP 응답 객체"""

    status_code: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = "application/json"

    @classmethod
    def ok(cls, body: Any = None) -> "HttpResponse":
        """200 OK 응답"""
        return cls(status_code=200, body=body)

    @classmethod
    def created(cls, body: Any = None) -> "HttpResponse":
        """201 Created 응답"""
        return cls(status_code=201, body=body)

    @classmethod
    def no_content(cls) -> "HttpResponse":
        """204 No Content 응답"""
        return cls(status_code=204)

    @classmethod
    def bad_request(cls, message: str = "Bad Request") -> "HttpResponse":
        """400 Bad Request 응답"""
        return cls(status_code=400, body={"error": message})

    @classmethod
    def not_found(cls, message: str = "Not Found") -> "HttpResponse":
        """404 Not Found 응답"""
        return cls(status_code=404, body={"error": message})

    @classmethod
    def internal_error(cls, message: str = "Internal Server Error") -> "HttpResponse":
        """500 Internal Server Error 응답"""
        return cls(status_code=500, body={"error": message})

    def to_json(self) -> bytes:
        """JSON 직렬화"""
        import json

        if self.body is None:
            return b""
        return json.dumps(self.body, ensure_ascii=False).encode("utf-8")


@dataclass
class StreamingResponse:
    """
    스트리밍 HTTP 응답

    AsyncGenerator를 통해 청크 단위로 데이터를 전송합니다.
    SSE, 대용량 파일 다운로드, 실시간 데이터 스트리밍에 유용합니다.

    사용 예시:
        @Get("/stream")
        async def stream_data(self) -> StreamingResponse:
            async def generate():
                for i in range(10):
                    yield f"data: {i}\\n\\n"
                    await asyncio.sleep(0.1)
            return StreamingResponse(generate())

        # SSE 예시
        @Get("/events")
        async def sse_events(self) -> StreamingResponse:
            return StreamingResponse.sse(event_generator())
    """

    content: StreamGenerator
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = "text/plain"

    @classmethod
    def sse(
        cls,
        content: StreamGenerator,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> "StreamingResponse":
        """
        Server-Sent Events (SSE) 스트리밍 응답

        Args:
            content: SSE 형식의 데이터를 생성하는 AsyncGenerator
            status_code: HTTP 상태 코드
            headers: 추가 헤더

        Returns:
            SSE content-type이 설정된 StreamingResponse
        """
        sse_headers = headers or {}
        sse_headers.setdefault("Cache-Control", "no-cache")
        sse_headers.setdefault("Connection", "keep-alive")
        return cls(
            content=content,
            status_code=status_code,
            headers=sse_headers,
            content_type="text/event-stream",
        )

    @classmethod
    def file(
        cls,
        content: StreamGenerator,
        filename: str,
        content_type: str = "application/octet-stream",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> "StreamingResponse":
        """
        파일 다운로드용 스트리밍 응답

        Args:
            content: 파일 데이터를 생성하는 AsyncGenerator
            filename: 다운로드 파일명
            content_type: MIME 타입
            status_code: HTTP 상태 코드
            headers: 추가 헤더

        Returns:
            Content-Disposition이 설정된 StreamingResponse
        """
        file_headers = headers or {}
        file_headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return cls(
            content=content,
            status_code=status_code,
            headers=file_headers,
            content_type=content_type,
        )

    async def __aiter__(self) -> AsyncIterator[bytes]:
        """청크 단위로 데이터 반환"""
        async for chunk in self.content:
            if isinstance(chunk, str):
                yield chunk.encode("utf-8")
            else:
                yield chunk


class FileResponse(StreamingResponse):
    """
    파일 객체를 스트리밍하는 HTTP 응답

    File 객체, BytesIO, 또는 파일 경로를 받아서 자동으로 스트리밍합니다.

    사용 예시:
        # 파일 경로로 생성
        @Get("/download")
        async def download(self) -> FileResponse:
            return FileResponse("data/report.csv")

        # BytesIO로 생성
        @Get("/export")
        async def export(self) -> FileResponse:
            buffer = BytesIO()
            buffer.write(b"CSV data here")
            buffer.seek(0)
            return FileResponse(buffer, filename="export.csv")

        # 열린 파일 객체로 생성
        @Get("/read")
        async def read_file(self) -> FileResponse:
            with open("data.bin", "rb") as f:
                return FileResponse(f, filename="data.bin")
    """

    def __init__(
        self,
        file: str | Path | BinaryIO | BytesIO,
        filename: str | None = None,
        content_type: str | None = None,
        chunk_size: int = 64 * 1024,  # 64KB
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        attachment: bool = True,
    ):
        """
        Args:
            file: 파일 경로, Path 객체, 또는 파일류 객체 (BytesIO, 열린 파일 등)
            filename: 다운로드 파일명 (경로에서 자동 추출 가능)
            content_type: MIME 타입 (자동 감지 가능)
            chunk_size: 청크 크기 (기본 64KB)
            status_code: HTTP 상태 코드
            headers: 추가 헤더
            attachment: Content-Disposition을 attachment로 설정 (다운로드 유도)
        """
        self._file = file
        self._chunk_size = chunk_size
        self._should_close = False

        # 파일명 결정
        if filename is None:
            if isinstance(file, (str, Path)):
                filename = Path(file).name
            elif hasattr(file, "name"):
                filename = Path(file.name).name
            else:
                filename = "download"

        # MIME 타입 결정
        if content_type is None:
            content_type, _ = mimetypes.guess_type(filename)
            if content_type is None:
                content_type = "application/octet-stream"

        # 헤더 설정
        file_headers = dict(headers) if headers else {}
        if attachment:
            file_headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        else:
            file_headers["Content-Disposition"] = f'inline; filename="{filename}"'

        # 부모 클래스 초기화
        super().__init__(
            content=self._generate_chunks(),
            status_code=status_code,
            headers=file_headers,
            content_type=content_type,
        )

    async def _generate_chunks(self) -> AsyncIterator[bytes]:
        """파일을 청크 단위로 읽어서 반환"""
        file_obj: BinaryIO | BytesIO

        if isinstance(self._file, (str, Path)):
            # 파일 경로인 경우 열기
            file_obj = open(self._file, "rb")
            self._should_close = True
        else:
            file_obj = self._file
            # BytesIO나 이미 열린 파일은 직접 닫지 않음
            self._should_close = False

        try:
            while True:
                chunk = file_obj.read(self._chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            if self._should_close:
                file_obj.close()
