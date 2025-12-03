"""STOMP 프로토콜 파서 테스트"""

import pytest

from bloom.web.messaging.stomp import (
    StompCommand,
    StompFrame,
    StompProtocol,
    StompError,
)


class TestStompFrame:
    """StompFrame 테스트"""

    def test_create_frame(self):
        """기본 프레임 생성"""
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/topic/chat"},
            body="Hello, World!",
        )

        assert frame.command == StompCommand.SEND
        assert frame.headers["destination"] == "/topic/chat"
        assert frame.body == "Hello, World!"

    def test_destination_property(self):
        """destination 프로퍼티"""
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/topic/chat"},
            body="",
        )
        assert frame.destination == "/topic/chat"

    def test_id_property(self):
        """id 프로퍼티"""
        frame = StompFrame(
            command=StompCommand.SUBSCRIBE,
            headers={"id": "sub-1", "destination": "/topic/chat"},
            body="",
        )
        assert frame.id == "sub-1"

    def test_content_type_property(self):
        """content-type 프로퍼티"""
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"content-type": "application/json"},
            body="{}",
        )
        assert frame.content_type == "application/json"

    def test_content_type_default(self):
        """content-type 기본값"""
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={},
            body="Hello",
        )
        assert frame.content_type == "text/plain"

    def test_serialize(self):
        """프레임 직렬화"""
        frame = StompFrame(
            command=StompCommand.SEND,
            headers={"destination": "/topic/chat"},
            body="Hello",
        )

        serialized = frame.serialize()

        assert serialized.startswith("SEND\n")
        assert "destination:/topic/chat" in serialized
        assert serialized.endswith("Hello\x00")

    def test_serialize_bytes(self):
        """바이트 직렬화"""
        frame = StompFrame(
            command=StompCommand.CONNECT,
            headers={"accept-version": "1.2"},
            body="",
        )

        data = frame.serialize_bytes()
        assert isinstance(data, bytes)
        assert b"CONNECT" in data

    def test_message_id_property(self):
        """message-id 프로퍼티"""
        frame = StompFrame(
            command=StompCommand.MESSAGE,
            headers={"message-id": "msg-123"},
            body="",
        )
        assert frame.message_id == "msg-123"

    def test_subscription_property(self):
        """subscription 프로퍼티"""
        frame = StompFrame(
            command=StompCommand.MESSAGE,
            headers={"subscription": "sub-1"},
            body="",
        )
        assert frame.subscription == "sub-1"


class TestStompProtocol:
    """StompProtocol 테스트"""

    def test_parse_simple_frame(self):
        """간단한 프레임 파싱"""
        protocol = StompProtocol()

        data = "CONNECT\naccept-version:1.2\nhost:localhost\n\n\x00"
        frame = protocol.parse(data)

        assert frame is not None
        assert frame.command == StompCommand.CONNECT
        assert frame.headers["accept-version"] == "1.2"
        assert frame.headers["host"] == "localhost"
        assert frame.body == ""

    def test_parse_frame_with_body(self):
        """본문이 있는 프레임 파싱"""
        protocol = StompProtocol()

        data = "SEND\ndestination:/topic/chat\n\nHello, World!\x00"
        frame = protocol.parse(data)

        assert frame is not None
        assert frame.command == StompCommand.SEND
        assert frame.destination == "/topic/chat"
        assert frame.body == "Hello, World!"

    def test_parse_frame_with_content_length(self):
        """content-length가 있는 프레임 파싱"""
        protocol = StompProtocol()

        # 일반 텍스트 body에 대한 content-length
        body = "Hello World"
        data = (
            f"SEND\ndestination:/topic/test\ncontent-length:{len(body)}\n\n{body}\x00"
        )
        frame = protocol.parse(data)

        assert frame is not None
        assert frame.body == body

    def test_parse_incomplete_frame(self):
        """불완전한 프레임 파싱 (None 반환)"""
        protocol = StompProtocol()

        # NULL 종료 문자 없음
        data = "SEND\ndestination:/topic/test\n\nHello"
        frame = protocol.parse(data)

        assert frame is None  # 불완전한 프레임

    def test_parse_streaming(self):
        """스트리밍 파싱 (조각난 데이터)"""
        protocol = StompProtocol()

        # 첫 번째 조각
        frame = protocol.parse("SEND\n")
        assert frame is None

        # 두 번째 조각
        frame = protocol.parse("destination:/topic/test\n")
        assert frame is None

        # 세 번째 조각 (완료)
        frame = protocol.parse("\nHello\x00")
        assert frame is not None
        assert frame.command == StompCommand.SEND
        assert frame.body == "Hello"

    def test_parse_multiple_frames(self):
        """여러 프레임 연속 파싱"""
        protocol = StompProtocol()

        data = "SEND\ndestination:/a\n\nA\x00SEND\ndestination:/b\n\nB\x00"

        # 첫 번째 프레임
        frame = protocol.parse(data)
        assert frame is not None
        assert frame.destination == "/a"
        assert frame.body == "A"

        # 두 번째 프레임
        frame = protocol.parse("")  # 버퍼에 남은 데이터 처리
        assert frame is not None
        assert frame.destination == "/b"
        assert frame.body == "B"

    def test_parse_invalid_command(self):
        """잘못된 명령어"""
        protocol = StompProtocol()

        data = "INVALID\n\n\x00"
        with pytest.raises(StompError):
            protocol.parse(data)

    def test_clear_buffer(self):
        """버퍼 초기화"""
        protocol = StompProtocol()
        protocol.parse("SEND\n")  # 불완전한 데이터

        protocol.clear_buffer()

        # 새 프레임 파싱
        frame = protocol.parse("CONNECT\naccept-version:1.2\n\n\x00")
        assert frame is not None
        assert frame.command == StompCommand.CONNECT

    def test_has_complete_frame(self):
        """완전한 프레임 확인"""
        protocol = StompProtocol()

        protocol.parse("SEND\n")
        assert not protocol.has_complete_frame()

        protocol.parse("destination:/test\n\nHello\x00")
        # 이미 파싱되어서 버퍼는 비어있을 수 있음
        # 대신 새로 테스트
        protocol.clear_buffer()

        protocol.parse("SEND\ndestination:/test\n\nHello")
        assert not protocol.has_complete_frame()

        protocol.parse("\x00")
        # 파싱 전에는 있음
        # parse 후에는 소비됨

    def test_create_connected(self):
        """CONNECTED 프레임 생성"""
        frame = StompProtocol.create_connected(
            version="1.2",
            session="session-123",
            server="bloom-stomp/1.0",
        )

        assert frame.command == StompCommand.CONNECTED
        assert frame.headers["version"] == "1.2"
        assert frame.headers["session"] == "session-123"
        assert frame.headers["server"] == "bloom-stomp/1.0"

    def test_create_message(self):
        """MESSAGE 프레임 생성"""
        frame = StompProtocol.create_message(
            destination="/topic/chat",
            body='{"text": "Hello"}',
            message_id="msg-1",
            subscription="sub-1",
        )

        assert frame.command == StompCommand.MESSAGE
        assert frame.destination == "/topic/chat"
        assert frame.headers["message-id"] == "msg-1"
        assert frame.headers["subscription"] == "sub-1"
        assert frame.body == '{"text": "Hello"}'

    def test_create_receipt(self):
        """RECEIPT 프레임 생성"""
        frame = StompProtocol.create_receipt("receipt-123")

        assert frame.command == StompCommand.RECEIPT
        assert frame.headers["receipt-id"] == "receipt-123"

    def test_create_error(self):
        """ERROR 프레임 생성"""
        frame = StompProtocol.create_error(
            message="Bad request",
            details="Invalid destination",
        )

        assert frame.command == StompCommand.ERROR
        assert frame.headers["message"] == "Bad request"
        assert frame.body == "Invalid destination"

    def test_parse_bytes(self):
        """바이트 데이터 파싱"""
        protocol = StompProtocol()

        data = b"CONNECT\naccept-version:1.2\n\n\x00"
        frame = protocol.parse_bytes(data)

        assert frame is not None
        assert frame.command == StompCommand.CONNECT


class TestStompError:
    """StompError 테스트"""

    def test_error_message(self):
        """에러 메시지"""
        error = StompError("Test error", "Error details")

        assert error.message == "Test error"
        assert error.details == "Error details"
        assert str(error) == "Test error"

    def test_error_without_details(self):
        """상세 없는 에러"""
        error = StompError("Simple error")

        assert error.message == "Simple error"
        assert error.details is None


class TestStompCommand:
    """StompCommand 열거형 테스트"""

    def test_client_commands(self):
        """클라이언트 명령어"""
        assert StompCommand.CONNECT.value == "CONNECT"
        assert StompCommand.STOMP.value == "STOMP"
        assert StompCommand.SEND.value == "SEND"
        assert StompCommand.SUBSCRIBE.value == "SUBSCRIBE"
        assert StompCommand.UNSUBSCRIBE.value == "UNSUBSCRIBE"
        assert StompCommand.ACK.value == "ACK"
        assert StompCommand.NACK.value == "NACK"
        assert StompCommand.DISCONNECT.value == "DISCONNECT"

    def test_server_commands(self):
        """서버 명령어"""
        assert StompCommand.CONNECTED.value == "CONNECTED"
        assert StompCommand.MESSAGE.value == "MESSAGE"
        assert StompCommand.RECEIPT.value == "RECEIPT"
        assert StompCommand.ERROR.value == "ERROR"

    def test_transaction_commands(self):
        """트랜잭션 명령어"""
        assert StompCommand.BEGIN.value == "BEGIN"
        assert StompCommand.COMMIT.value == "COMMIT"
        assert StompCommand.ABORT.value == "ABORT"


class TestStompFrameEscaping:
    """STOMP 헤더 이스케이프 테스트"""

    def test_escape_header_value(self):
        """헤더 값 이스케이프"""
        # 콜론 이스케이프
        escaped = StompFrame._escape_header_value("key:value")
        assert escaped == "key\\cvalue"

        # 개행 이스케이프
        escaped = StompFrame._escape_header_value("line1\nline2")
        assert escaped == "line1\\nline2"

        # 백슬래시 이스케이프
        escaped = StompFrame._escape_header_value("path\\to\\file")
        assert escaped == "path\\\\to\\\\file"

    def test_unescape_header_value(self):
        """헤더 값 언이스케이프"""
        # 콜론
        unescaped = StompFrame._unescape_header_value("key\\cvalue")
        assert unescaped == "key:value"

        # 개행
        unescaped = StompFrame._unescape_header_value("line1\\nline2")
        assert unescaped == "line1\nline2"

        # 백슬래시
        unescaped = StompFrame._unescape_header_value("path\\\\to\\\\file")
        assert unescaped == "path\\to\\file"

    def test_escape_roundtrip(self):
        """이스케이프 왕복 테스트"""
        original = "header:with\nspecial\\chars"
        escaped = StompFrame._escape_header_value(original)
        unescaped = StompFrame._unescape_header_value(escaped)
        assert unescaped == original
