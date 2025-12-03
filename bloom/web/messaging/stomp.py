"""STOMP 프로토콜 파서

STOMP (Simple Text Oriented Messaging Protocol) 프레임을 파싱하고 생성합니다.
https://stomp.github.io/stomp-specification-1.2.html

STOMP Frame 구조:
    COMMAND
    header1:value1
    header2:value2

    Body content here^@

    ^@ = NULL 문자 (프레임 종료)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StompCommand(Enum):
    """STOMP 명령어"""

    # Client commands
    CONNECT = "CONNECT"
    STOMP = "STOMP"  # CONNECT와 동일
    SEND = "SEND"
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    ACK = "ACK"
    NACK = "NACK"
    BEGIN = "BEGIN"
    COMMIT = "COMMIT"
    ABORT = "ABORT"
    DISCONNECT = "DISCONNECT"

    # Server commands
    CONNECTED = "CONNECTED"
    MESSAGE = "MESSAGE"
    RECEIPT = "RECEIPT"
    ERROR = "ERROR"


class StompError(Exception):
    """STOMP 프로토콜 에러"""

    def __init__(self, message: str, details: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


@dataclass
class StompFrame:
    """STOMP 프레임

    STOMP 메시지의 단위입니다.

    Attributes:
        command: STOMP 명령어
        headers: 헤더 딕셔너리
        body: 메시지 본문
    """

    command: StompCommand
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    # 자주 사용되는 헤더 접근자
    @property
    def destination(self) -> str | None:
        """destination 헤더"""
        return self.headers.get("destination")

    @property
    def content_type(self) -> str:
        """content-type 헤더 (기본 text/plain)"""
        return self.headers.get("content-type", "text/plain")

    @property
    def content_length(self) -> int | None:
        """content-length 헤더"""
        length = self.headers.get("content-length")
        return int(length) if length else None

    @property
    def message_id(self) -> str | None:
        """message-id 헤더"""
        return self.headers.get("message-id")

    @property
    def subscription(self) -> str | None:
        """subscription 헤더"""
        return self.headers.get("subscription")

    @property
    def receipt_id(self) -> str | None:
        """receipt-id 헤더"""
        return self.headers.get("receipt-id")

    @property
    def id(self) -> str | None:
        """id 헤더 (구독/구독취소용)"""
        return self.headers.get("id")

    def serialize(self) -> str:
        """프레임을 문자열로 직렬화

        Returns:
            STOMP 프레임 문자열 (NULL 종료 문자 포함)
        """
        lines = [self.command.value]

        # 헤더 직렬화 (값에 포함된 특수문자 이스케이프)
        for key, value in self.headers.items():
            escaped_value = self._escape_header_value(value)
            lines.append(f"{key}:{escaped_value}")

        lines.append("")  # 빈 줄 (헤더와 본문 구분)
        lines.append(self.body)

        return "\n".join(lines) + "\x00"

    def serialize_bytes(self) -> bytes:
        """프레임을 바이트로 직렬화"""
        return self.serialize().encode("utf-8")

    @staticmethod
    def _escape_header_value(value: str) -> str:
        """헤더 값 이스케이프"""
        return (
            value.replace("\\", "\\\\")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace(":", "\\c")
        )

    @staticmethod
    def _unescape_header_value(value: str) -> str:
        """헤더 값 언이스케이프"""
        result = []
        i = 0
        while i < len(value):
            if value[i] == "\\" and i + 1 < len(value):
                next_char = value[i + 1]
                if next_char == "r":
                    result.append("\r")
                elif next_char == "n":
                    result.append("\n")
                elif next_char == "c":
                    result.append(":")
                elif next_char == "\\":
                    result.append("\\")
                else:
                    result.append(value[i])
                    result.append(next_char)
                i += 2
            else:
                result.append(value[i])
                i += 1
        return "".join(result)

    def __repr__(self) -> str:
        return (
            f"StompFrame(command={self.command.name}, "
            f"headers={self.headers}, body={self.body[:50]!r}...)"
        )


class StompProtocol:
    """STOMP 프로토콜 처리기

    STOMP 프레임의 파싱과 생성을 담당합니다.

    Examples:
        protocol = StompProtocol()

        # 파싱
        frame = protocol.parse("CONNECT\\naccept-version:1.2\\n\\n\\x00")

        # 생성
        frame = protocol.create_message("/topic/chat", "Hello!")
        data = frame.serialize()
    """

    SUPPORTED_VERSIONS = ["1.2", "1.1", "1.0"]
    DEFAULT_VERSION = "1.2"

    def __init__(self, version: str = DEFAULT_VERSION):
        self.version = version
        self._buffer = ""

    def parse(self, data: str) -> StompFrame | None:
        """문자열에서 STOMP 프레임 파싱

        Args:
            data: STOMP 프레임 문자열

        Returns:
            파싱된 StompFrame 또는 None (불완전한 프레임)

        Raises:
            StompError: 프로토콜 에러
        """
        self._buffer += data

        # NULL 문자로 프레임 종료 확인
        null_pos = self._buffer.find("\x00")
        if null_pos == -1:
            return None  # 아직 완전한 프레임이 아님

        frame_data = self._buffer[:null_pos]
        self._buffer = self._buffer[null_pos + 1 :].lstrip("\n\r")  # 다음 프레임을 위해

        return self._parse_frame(frame_data)

    def parse_bytes(self, data: bytes) -> StompFrame | None:
        """바이트에서 STOMP 프레임 파싱"""
        return self.parse(data.decode("utf-8"))

    def _parse_frame(self, data: str) -> StompFrame:
        """프레임 데이터 파싱"""
        lines = data.split("\n")

        if not lines:
            raise StompError("Empty frame")

        # 명령어 파싱
        command_str = lines[0].strip()
        if not command_str:
            raise StompError("Missing command")

        try:
            command = StompCommand(command_str)
        except ValueError:
            raise StompError(f"Unknown command: {command_str}")

        # 헤더 파싱
        headers: dict[str, str] = {}
        body_start = 1

        for i, line in enumerate(lines[1:], start=1):
            if line == "":
                body_start = i + 1
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key] = StompFrame._unescape_header_value(value)
            body_start = i + 1

        # 본문 파싱
        body = "\n".join(lines[body_start:])

        # content-length가 있으면 그 길이만큼만 본문으로
        content_length = headers.get("content-length")
        if content_length:
            body = body[: int(content_length)]

        return StompFrame(command=command, headers=headers, body=body)

    def has_complete_frame(self) -> bool:
        """버퍼에 완전한 프레임이 있는지 확인"""
        return "\x00" in self._buffer

    def clear_buffer(self) -> None:
        """버퍼 초기화"""
        self._buffer = ""

    # === 프레임 생성 헬퍼 ===

    @staticmethod
    def create_connect(
        accept_version: str = "1.2",
        host: str | None = None,
        login: str | None = None,
        passcode: str | None = None,
        heart_beat: tuple[int, int] | None = None,
    ) -> StompFrame:
        """CONNECT 프레임 생성"""
        headers = {"accept-version": accept_version}
        if host:
            headers["host"] = host
        if login:
            headers["login"] = login
        if passcode:
            headers["passcode"] = passcode
        if heart_beat:
            headers["heart-beat"] = f"{heart_beat[0]},{heart_beat[1]}"

        return StompFrame(command=StompCommand.CONNECT, headers=headers)

    @staticmethod
    def create_connected(
        version: str = "1.2",
        session: str | None = None,
        server: str | None = None,
        heart_beat: tuple[int, int] | None = None,
    ) -> StompFrame:
        """CONNECTED 프레임 생성"""
        headers = {"version": version}
        if session:
            headers["session"] = session
        if server:
            headers["server"] = server
        if heart_beat:
            headers["heart-beat"] = f"{heart_beat[0]},{heart_beat[1]}"

        return StompFrame(command=StompCommand.CONNECTED, headers=headers)

    @staticmethod
    def create_send(
        destination: str,
        body: str = "",
        content_type: str = "text/plain",
        headers: dict[str, str] | None = None,
    ) -> StompFrame:
        """SEND 프레임 생성"""
        frame_headers = {"destination": destination, "content-type": content_type}
        if headers:
            frame_headers.update(headers)
        if body:
            frame_headers["content-length"] = str(len(body.encode("utf-8")))

        return StompFrame(command=StompCommand.SEND, headers=frame_headers, body=body)

    @staticmethod
    def create_subscribe(
        destination: str,
        subscription_id: str,
        ack: str = "auto",
    ) -> StompFrame:
        """SUBSCRIBE 프레임 생성"""
        return StompFrame(
            command=StompCommand.SUBSCRIBE,
            headers={
                "id": subscription_id,
                "destination": destination,
                "ack": ack,
            },
        )

    @staticmethod
    def create_unsubscribe(subscription_id: str) -> StompFrame:
        """UNSUBSCRIBE 프레임 생성"""
        return StompFrame(
            command=StompCommand.UNSUBSCRIBE,
            headers={"id": subscription_id},
        )

    @staticmethod
    def create_message(
        destination: str,
        body: str,
        message_id: str,
        subscription: str,
        content_type: str = "application/json",
        headers: dict[str, str] | None = None,
    ) -> StompFrame:
        """MESSAGE 프레임 생성 (서버 → 클라이언트)"""
        frame_headers = {
            "destination": destination,
            "message-id": message_id,
            "subscription": subscription,
            "content-type": content_type,
            "content-length": str(len(body.encode("utf-8"))),
        }
        if headers:
            frame_headers.update(headers)

        return StompFrame(
            command=StompCommand.MESSAGE, headers=frame_headers, body=body
        )

    @staticmethod
    def create_receipt(receipt_id: str) -> StompFrame:
        """RECEIPT 프레임 생성"""
        return StompFrame(
            command=StompCommand.RECEIPT,
            headers={"receipt-id": receipt_id},
        )

    @staticmethod
    def create_error(
        message: str,
        details: str | None = None,
        receipt_id: str | None = None,
    ) -> StompFrame:
        """ERROR 프레임 생성"""
        headers = {"message": message}
        if receipt_id:
            headers["receipt-id"] = receipt_id

        body = details or ""
        if body:
            headers["content-type"] = "text/plain"
            headers["content-length"] = str(len(body.encode("utf-8")))

        return StompFrame(command=StompCommand.ERROR, headers=headers, body=body)

    @staticmethod
    def create_disconnect(receipt: str | None = None) -> StompFrame:
        """DISCONNECT 프레임 생성"""
        headers = {}
        if receipt:
            headers["receipt"] = receipt

        return StompFrame(command=StompCommand.DISCONNECT, headers=headers)
