"""bloom.testing.mock - Mock 유틸리티"""

from __future__ import annotations

from typing import TypeVar, Generic, Any
from unittest.mock import MagicMock, AsyncMock

T = TypeVar("T")


class MockBean(Generic[T]):
    """
    MockBean 타입 마커.

    테스트 클래스의 필드 타입 힌트로 사용하면,
    BloomTestCase가 자동으로 Mock 객체를 생성하고 DI 컨테이너에 등록합니다.

    사용 예:
        class MyTest(BloomTestCase):
            repo: MockBean[UserRepository]

            async def test_users(self):
                self.repo.find_all.return_value = [{"id": 1}]
                # ...
    """

    pass


class MockSTOMP:
    """
    STOMP 프로토콜 Mock 클라이언트.

    테스트에서 실제 메시지 브로커 없이 STOMP 통신을 시뮬레이션합니다.

    사용 예:
        stomp = MockSTOMP()
        await stomp.connect()

        received = []
        await stomp.subscribe("/topic/test", lambda f: received.append(f))

        stomp.simulate_message("/topic/test", {"data": "hello"})
        assert len(received) == 1
    """

    def __init__(self):
        self.connected = False
        self._subscriptions: dict[str, list] = {}
        self._sent_messages: list[tuple[str, Any]] = []

    async def connect(self, headers: dict[str, str] | None = None) -> None:
        """STOMP 연결"""
        self.connected = True

    async def disconnect(self) -> None:
        """STOMP 연결 해제"""
        self.connected = False
        self._subscriptions.clear()

    async def subscribe(
        self,
        destination: str,
        callback,
        headers: dict[str, str] | None = None,
    ) -> str:
        """
        대상 구독.

        Args:
            destination: 구독할 대상 (예: "/topic/test")
            callback: 메시지 수신 시 호출될 콜백
            headers: 추가 헤더

        Returns:
            구독 ID
        """
        if destination not in self._subscriptions:
            self._subscriptions[destination] = []
        self._subscriptions[destination].append(callback)
        return f"sub-{len(self._subscriptions)}"

    async def unsubscribe(self, subscription_id: str) -> None:
        """구독 해제"""
        pass

    async def send(
        self,
        destination: str,
        body: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        메시지 전송.

        Args:
            destination: 대상 (예: "/app/test")
            body: 메시지 본문
            headers: 추가 헤더
        """
        self._sent_messages.append((destination, body))

    def simulate_message(
        self,
        destination: str,
        body: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        메시지 수신 시뮬레이션.

        테스트에서 메시지 브로커로부터 메시지를 받은 것처럼 시뮬레이션합니다.

        Args:
            destination: 대상
            body: 메시지 본문
            headers: 헤더
        """
        callbacks = self._subscriptions.get(destination, [])
        for callback in callbacks:
            callback(body)

    async def wait_for_message(self, timeout: float = 1.0) -> None:
        """메시지 대기 (테스트용 - 실제로는 아무것도 안 함)"""
        pass

    @property
    def sent_messages(self) -> list[tuple[str, Any]]:
        """전송된 메시지 목록"""
        return self._sent_messages.copy()

    def assert_sent(self, destination: str, body: Any = None) -> None:
        """메시지 전송 확인"""
        for dest, msg_body in self._sent_messages:
            if dest == destination:
                if body is None or msg_body == body:
                    return
        raise AssertionError(f"Message not sent to {destination}")

    def reset(self) -> None:
        """Mock 상태 리셋"""
        self._sent_messages.clear()
        self._subscriptions.clear()
