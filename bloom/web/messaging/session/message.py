"""STOMP 스타일 메시지 모델"""

from dataclasses import dataclass, field
from typing import Any
from enum import Enum
import json


class StompCommand(Enum):
    """STOMP 프레임 명령"""

    # 클라이언트 → 서버
    CONNECT = "CONNECT"
    STOMP = "STOMP"  # CONNECT의 별칭
    SUBSCRIBE = "SUBSCRIBE"
    UNSUBSCRIBE = "UNSUBSCRIBE"
    SEND = "SEND"
    DISCONNECT = "DISCONNECT"
    ACK = "ACK"
    NACK = "NACK"

    # 서버 → 클라이언트
    CONNECTED = "CONNECTED"
    MESSAGE = "MESSAGE"
    RECEIPT = "RECEIPT"
    ERROR = "ERROR"


@dataclass
class StompFrame:
    """
    STOMP 프레임

    STOMP 프로토콜 형식:
        COMMAND
        header1:value1
        header2:value2

        body^@

    여기서 ^@는 NULL 문자 (\\x00)
    """

    command: StompCommand
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""

    @classmethod
    def parse(cls, data: str) -> "StompFrame":
        """
        STOMP 프레임 파싱

        Args:
            data: 원시 STOMP 프레임 문자열

        Returns:
            파싱된 StompFrame 객체

        Raises:
            ValueError: 잘못된 STOMP 프레임 형식
        """
        # NULL 문자로 끝나는 경우 제거
        data = data.rstrip("\x00")

        lines = data.split("\n")
        if not lines:
            raise ValueError("Empty STOMP frame")

        # 명령어 파싱
        command_str = lines[0].strip()
        try:
            command = StompCommand(command_str)
        except ValueError:
            raise ValueError(f"Unknown STOMP command: {command_str}")

        # 헤더 파싱
        headers: dict[str, str] = {}
        body_start = 1

        for i, line in enumerate(lines[1:], 1):
            stripped = line.strip()
            if stripped == "":
                body_start = i + 1
                break
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                headers[key.strip()] = value.strip()

        # 바디 파싱
        body = "\n".join(lines[body_start:]) if body_start < len(lines) else ""

        return cls(command, headers, body)

    def encode(self) -> str:
        """
        STOMP 프레임을 문자열로 인코딩

        Returns:
            STOMP 프로토콜 형식 문자열
        """
        lines = [self.command.value]

        for key, value in self.headers.items():
            lines.append(f"{key}:{value}")

        lines.append("")  # 헤더와 바디 구분 빈 줄
        lines.append(self.body)

        return "\n".join(lines) + "\x00"

    def to_bytes(self) -> bytes:
        """UTF-8 인코딩된 바이트로 변환"""
        return self.encode().encode("utf-8")


@dataclass
class Message:
    """
    개발자가 다루는 고수준 메시지

    Spring의 Message<T>와 유사한 인터페이스 제공.
    WebSocket/STOMP 세부사항은 숨기고 순수한 메시지 데이터만 노출.

    Attributes:
        destination: 메시지 목적지 (예: /topic/chat, /queue/user.123)
        payload: 메시지 페이로드 (Any 타입, 직렬화 시 JSON 변환)
        headers: 추가 헤더 정보
        session_id: WebSocket 세션 ID (내부 사용)
        user: 인증된 사용자 식별자
        subscription_id: 구독 ID (응답 시 사용)
    """

    destination: str
    payload: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    session_id: str | None = None
    user: str | None = None
    subscription_id: str | None = None

    def to_json(self) -> str:
        """페이로드를 JSON 문자열로 변환"""
        if self.payload is None:
            return ""
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, ensure_ascii=False, default=str)

    @classmethod
    def from_stomp_frame(
        cls,
        frame: StompFrame,
        session_id: str | None = None,
        user: str | None = None,
    ) -> "Message":
        """
        STOMP 프레임에서 Message 생성

        Args:
            frame: STOMP 프레임
            session_id: 세션 ID
            user: 인증된 사용자

        Returns:
            Message 객체
        """
        destination = frame.headers.get("destination", "")
        subscription_id = frame.headers.get("id")

        # 바디 JSON 파싱 시도
        payload: Any = frame.body
        if frame.body:
            try:
                payload = json.loads(frame.body)
            except json.JSONDecodeError:
                pass  # 원본 문자열 유지

        return cls(
            destination=destination,
            payload=payload,
            headers=frame.headers,
            session_id=session_id,
            user=user,
            subscription_id=subscription_id,
        )

    def to_stomp_frame(
        self, command: StompCommand = StompCommand.MESSAGE
    ) -> StompFrame:
        """
        Message를 STOMP 프레임으로 변환

        Args:
            command: STOMP 명령 (기본: MESSAGE)

        Returns:
            StompFrame 객체
        """
        headers = {**self.headers, "destination": self.destination}

        if self.subscription_id:
            headers["subscription"] = self.subscription_id

        # content-type 설정
        if "content-type" not in headers:
            headers["content-type"] = "application/json"

        return StompFrame(
            command=command,
            headers=headers,
            body=self.to_json(),
        )


__all__ = [
    "StompCommand",
    "StompFrame",
    "Message",
]
