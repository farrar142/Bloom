"""메시지 브로커

메시지 구독/발행을 관리하는 브로커 구현입니다.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, TYPE_CHECKING
from collections import defaultdict

if TYPE_CHECKING:
    from .websocket import WebSocketSession


@dataclass
class Subscription:
    """구독 정보"""

    id: str
    destination: str
    session_id: str
    session: "WebSocketSession"
    ack_mode: str = "auto"  # auto, client, client-individual

    # 메타데이터
    created_at: float = field(default_factory=lambda: __import__("time").time())
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class Message:
    """브로커 메시지"""

    destination: str
    body: Any
    headers: dict[str, str] = field(default_factory=dict)

    # 메타데이터
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=lambda: __import__("time").time())

    def to_json(self) -> str:
        """JSON 직렬화"""
        if isinstance(self.body, str):
            return self.body
        return json.dumps(self.body, ensure_ascii=False, default=str)


class MessageBroker(ABC):
    """메시지 브로커 인터페이스

    구독/발행 패턴을 구현합니다.
    """

    @abstractmethod
    async def register_session(self, session: "WebSocketSession") -> None:
        """세션 등록"""
        pass

    @abstractmethod
    async def unregister_session(self, session_id: str) -> None:
        """세션 해제"""
        pass

    @abstractmethod
    async def subscribe(
        self,
        destination: str,
        subscription_id: str,
        session: "WebSocketSession",
        ack_mode: str = "auto",
    ) -> Subscription:
        """destination 구독"""
        pass

    @abstractmethod
    async def unsubscribe(self, subscription_id: str, session_id: str) -> bool:
        """구독 취소"""
        pass

    @abstractmethod
    async def unsubscribe_all(self, session_id: str) -> int:
        """세션의 모든 구독 취소"""
        pass

    @abstractmethod
    async def publish(
        self, destination: str, message: Any, headers: dict[str, str] | None = None
    ) -> int:
        """메시지 발행 (모든 구독자에게)

        Returns:
            전송된 구독자 수
        """
        pass

    @abstractmethod
    async def send_to_session(
        self,
        session_id: str,
        destination: str,
        message: Any,
        headers: dict[str, str] | None = None,
    ) -> bool:
        """특정 세션에만 메시지 전송"""
        pass

    @abstractmethod
    def get_subscriptions(self, destination: str) -> list[Subscription]:
        """destination의 구독 목록 조회"""
        pass

    @abstractmethod
    def get_session_subscriptions(self, session_id: str) -> list[Subscription]:
        """세션의 구독 목록 조회"""
        pass


class SimpleBroker(MessageBroker):
    """인메모리 심플 브로커

    단일 프로세스용 메시지 브로커입니다.
    프로덕션에서는 Redis 등을 사용하는 브로커로 교체해야 합니다.

    Examples:
        broker = SimpleBroker()

        # 구독
        sub = await broker.subscribe("/topic/chat", "sub-1", session)

        # 발행
        await broker.publish("/topic/chat", {"text": "Hello!"})

        # 구독 취소
        await broker.unsubscribe("sub-1", session.session_id)
    """

    def __init__(self):
        # destination -> list[Subscription]
        self._subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        # session_id -> list[Subscription]
        self._session_subscriptions: dict[str, list[Subscription]] = defaultdict(list)
        # subscription_id -> Subscription
        self._subscription_by_id: dict[str, Subscription] = {}
        # session_id -> WebSocketSession
        self._sessions: dict[str, "WebSocketSession"] = {}
        # Lock for thread safety
        self._lock = asyncio.Lock()

    async def register_session(self, session: "WebSocketSession") -> None:
        """세션 등록"""
        async with self._lock:
            self._sessions[session.session_id] = session

    async def unregister_session(self, session_id: str) -> None:
        """세션 해제"""
        async with self._lock:
            # 세션의 모든 구독 해제
            await self._unsubscribe_all_internal(session_id)
            self._sessions.pop(session_id, None)

    async def subscribe(
        self,
        destination: str,
        subscription_id: str,
        session: "WebSocketSession",
        ack_mode: str = "auto",
    ) -> Subscription:
        """destination 구독"""
        async with self._lock:
            # 기존 구독 확인
            if subscription_id in self._subscription_by_id:
                return self._subscription_by_id[subscription_id]

            sub = Subscription(
                id=subscription_id,
                destination=destination,
                session_id=session.session_id,
                session=session,
                ack_mode=ack_mode,
            )

            self._subscriptions[destination].append(sub)
            self._session_subscriptions[session.session_id].append(sub)
            self._subscription_by_id[subscription_id] = sub
            self._sessions[session.session_id] = session

            return sub

    async def unsubscribe(self, subscription_id: str, session_id: str) -> bool:
        """구독 취소"""
        async with self._lock:
            sub = self._subscription_by_id.pop(subscription_id, None)
            if not sub:
                return False

            # destination에서 제거
            dest_subs = self._subscriptions.get(sub.destination, [])
            self._subscriptions[sub.destination] = [
                s for s in dest_subs if s.id != subscription_id
            ]

            # session에서 제거
            session_subs = self._session_subscriptions.get(session_id, [])
            self._session_subscriptions[session_id] = [
                s for s in session_subs if s.id != subscription_id
            ]

            return True

    async def unsubscribe_all(self, session_id: str) -> int:
        """세션의 모든 구독 취소"""
        async with self._lock:
            return await self._unsubscribe_all_internal(session_id)

    async def _unsubscribe_all_internal(self, session_id: str) -> int:
        """세션의 모든 구독 취소 (락 내부용)"""
        subs = self._session_subscriptions.pop(session_id, [])
        count = len(subs)

        for sub in subs:
            self._subscription_by_id.pop(sub.id, None)
            dest_subs = self._subscriptions.get(sub.destination, [])
            self._subscriptions[sub.destination] = [
                s for s in dest_subs if s.id != sub.id
            ]

        return count

    async def publish(
        self,
        destination: str,
        message: Any,
        headers: dict[str, str] | None = None,
    ) -> int:
        """메시지 발행"""
        msg = Message(destination=destination, body=message, headers=headers or {})

        # 패턴 매칭 구독 찾기
        matching_subs = self._find_matching_subscriptions(destination)

        sent_count = 0
        for sub in matching_subs:
            try:
                await self._send_message_to_subscription(sub, msg)
                sent_count += 1
            except Exception:
                # 전송 실패 시 로깅만 하고 계속
                pass

        return sent_count

    async def send_to_session(
        self,
        session_id: str,
        destination: str,
        message: Any,
        headers: dict[str, str] | None = None,
    ) -> bool:
        """특정 세션에만 메시지 전송"""
        session = self._sessions.get(session_id)
        if not session:
            return False

        msg = Message(destination=destination, body=message, headers=headers or {})

        try:
            from .stomp import StompProtocol

            # 세션의 해당 destination 구독 찾기
            session_subs = self._session_subscriptions.get(session_id, [])
            matching_sub = None
            for sub in session_subs:
                if self._match_destination(sub.destination, destination):
                    matching_sub = sub
                    break

            if matching_sub:
                await self._send_message_to_subscription(matching_sub, msg)
            else:
                # 구독이 없어도 직접 전송 (user queue 등)
                frame = StompProtocol.create_message(
                    destination=destination,
                    body=msg.to_json(),
                    message_id=msg.message_id,
                    subscription="direct",
                )
                await session.send_text(frame.serialize())

            return True
        except Exception:
            return False

    def _find_matching_subscriptions(self, destination: str) -> list[Subscription]:
        """destination과 매칭되는 모든 구독 찾기"""
        result = []

        for sub_dest, subs in self._subscriptions.items():
            if self._match_destination(sub_dest, destination):
                result.extend(subs)

        return result

    def _match_destination(self, pattern: str, destination: str) -> bool:
        """destination 패턴 매칭

        지원 패턴:
        - 정확한 매칭: /topic/chat
        - 와일드카드 *: /topic/* (한 레벨)
        - 와일드카드 **: /topic/** (모든 레벨)
        """
        if pattern == destination:
            return True

        pattern_parts = pattern.split("/")
        dest_parts = destination.split("/")

        i = 0
        for i, p_part in enumerate(pattern_parts):
            if p_part == "**":
                return True
            if i >= len(dest_parts):
                return False
            if p_part == "*":
                continue
            if p_part != dest_parts[i]:
                return False

        return len(pattern_parts) == len(dest_parts)

    async def _send_message_to_subscription(
        self, sub: Subscription, msg: Message
    ) -> None:
        """구독자에게 메시지 전송"""
        from .stomp import StompProtocol

        frame = StompProtocol.create_message(
            destination=msg.destination,
            body=msg.to_json(),
            message_id=msg.message_id,
            subscription=sub.id,
            headers=msg.headers,
        )

        await sub.session.send_text(frame.serialize())

    def get_subscriptions(self, destination: str) -> list[Subscription]:
        """destination의 구독 목록 조회"""
        return list(self._subscriptions.get(destination, []))

    def get_session_subscriptions(self, session_id: str) -> list[Subscription]:
        """세션의 구독 목록 조회"""
        return list(self._session_subscriptions.get(session_id, []))

    def get_all_destinations(self) -> list[str]:
        """모든 활성 destination 목록"""
        return list(self._subscriptions.keys())

    def get_subscription_count(self, destination: str) -> int:
        """destination의 구독자 수"""
        return len(self._subscriptions.get(destination, []))

    def get_total_subscriptions(self) -> int:
        """전체 구독 수"""
        return len(self._subscription_by_id)

    def get_session_count(self) -> int:
        """연결된 세션 수"""
        return len(self._sessions)
