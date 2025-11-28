"""메시징 템플릿 - 어디서든 메시지 발행"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .session import SimpleBroker

from .session import Message


class SimpMessagingTemplate:
    """
    Simple Messaging Template

    Spring의 SimpMessagingTemplate과 동일한 역할.
    서비스 레이어나 어디서든 메시지를 발행할 수 있게 해주는 헬퍼 클래스.

    DI를 통해 주입받아 사용:
        @Component
        class NotificationService:
            messaging: SimpMessagingTemplate  # 자동 주입!

            async def notify_user(self, user_id: str, data: dict):
                await self.messaging.convert_and_send_to_user(
                    user_id, "/queue/notifications", data
                )

    브로커를 통해 메시지를 발행하며, 구독자가 없어도 예외 없이 동작함.
    """

    def __init__(self, broker: "SimpleBroker"):
        """
        Args:
            broker: 메시지 브로커 인스턴스
        """
        self._broker = broker

    async def convert_and_send(
        self,
        destination: str,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> int:
        """
        페이로드를 메시지로 변환하여 목적지로 전송

        Args:
            destination: 메시지 목적지 (예: "/topic/chat", "/queue/orders")
            payload: 메시지 페이로드 (JSON 직렬화 가능한 객체)
            headers: 추가 헤더 (옵션)

        Returns:
            전송된 구독자 수
        """
        message = Message(
            destination=destination,
            payload=payload,
            headers=headers or {},
        )
        return await self._broker.publish(message)

    async def convert_and_send_to_user(
        self,
        user: str,
        destination: str,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> int:
        """
        특정 사용자에게 메시지 전송

        내부적으로 /user/{user}{destination} 형식으로 변환됨.

        Args:
            user: 대상 사용자 ID
            destination: 사용자별 목적지 (예: "/queue/notifications")
            payload: 메시지 페이로드
            headers: 추가 헤더 (옵션)

        Returns:
            전송된 세션 수
        """
        message = Message(
            destination=destination,
            payload=payload,
            headers=headers or {},
            user=user,
        )
        return await self._broker.send_to_user(user, destination, message)

    async def send(self, message: Message) -> int:
        """
        Message 객체 직접 전송

        Args:
            message: 전송할 Message 객체

        Returns:
            전송된 구독자 수
        """
        return await self._broker.publish(message)

    @property
    def broker(self) -> "SimpleBroker":
        """브로커 인스턴스 접근 (고급 사용)"""
        return self._broker
