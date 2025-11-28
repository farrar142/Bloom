"""인메모리 메시지 브로커"""

from __future__ import annotations

import asyncio
import fnmatch
import re
from dataclasses import dataclass, field
from typing import Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from .message import Message

# 메시지 전송 콜백 타입
SendCallback = Callable[["Message"], Awaitable[None]]


@dataclass
class Subscription:
    """
    구독 정보

    Attributes:
        id: 구독 ID (클라이언트가 지정)
        destination: 구독 목적지 패턴 (예: /topic/chat, /topic/chat.*)
        session_id: WebSocket 세션 ID
        user: 인증된 사용자 (옵션)
        send_callback: 메시지 전송 콜백
    """

    id: str
    destination: str
    session_id: str
    user: str | None = None
    send_callback: SendCallback | None = None

    def matches(self, destination: str) -> bool:
        """
        목적지가 이 구독의 패턴과 일치하는지 확인

        지원하는 패턴:
            - /topic/chat: 정확한 일치
            - /topic/chat.*: 한 레벨 와일드카드
            - /topic/chat.**: 다중 레벨 와일드카드

        Args:
            destination: 확인할 목적지

        Returns:
            일치 여부
        """
        pattern = self.destination

        # 정확한 일치
        if pattern == destination:
            return True

        # ** 와일드카드 (다중 레벨)
        if "**" in pattern:
            regex_pattern = pattern.replace(".", r"\.").replace("**", ".*")
            return bool(re.match(f"^{regex_pattern}$", destination))

        # * 와일드카드 (한 레벨)
        if "*" in pattern:
            regex_pattern = pattern.replace(".", r"\.").replace("*", r"[^.]+")
            return bool(re.match(f"^{regex_pattern}$", destination))

        return False


class SimpleBroker:
    """
    인메모리 심플 메시지 브로커

    Spring의 SimpleBrokerMessageHandler와 유사한 기능 제공.

    목적지 프리픽스:
        - /topic/*: 구독한 모든 클라이언트에게 브로드캐스트
        - /queue/*: 라운드로빈으로 하나의 구독자에게 전달
        - /user/{userId}/*: 특정 사용자에게 전달

    사용 예시:
        broker = SimpleBroker()

        # 구독 등록
        await broker.subscribe("sub-1", "/topic/chat", session_id, callback)

        # 메시지 발행
        await broker.publish(Message(destination="/topic/chat", payload={"text": "hi"}))

        # 특정 사용자에게 전송
        await broker.send_to_user("alice", "/queue/notifications", message)
    """

    def __init__(self):
        # destination -> [Subscription]
        self._subscriptions: dict[str, list[Subscription]] = {}
        # session_id -> [subscription_id]
        self._session_subscriptions: dict[str, list[str]] = {}
        # 라운드로빈 인덱스: destination -> index
        self._queue_index: dict[str, int] = {}
        # user -> [session_id]
        self._user_sessions: dict[str, set[str]] = {}
        # 동시성 제어
        self._lock = asyncio.Lock()

    async def subscribe(
        self,
        subscription_id: str,
        destination: str,
        session_id: str,
        send_callback: SendCallback,
        user: str | None = None,
    ) -> Subscription:
        """
        구독 등록

        Args:
            subscription_id: 구독 ID
            destination: 구독할 목적지
            session_id: WebSocket 세션 ID
            send_callback: 메시지 전송 콜백
            user: 인증된 사용자 (옵션)

        Returns:
            생성된 Subscription 객체
        """
        async with self._lock:
            sub = Subscription(
                id=subscription_id,
                destination=destination,
                session_id=session_id,
                user=user,
                send_callback=send_callback,
            )

            # 목적지별 구독 목록에 추가
            if destination not in self._subscriptions:
                self._subscriptions[destination] = []
            self._subscriptions[destination].append(sub)

            # 세션별 구독 목록에 추가
            if session_id not in self._session_subscriptions:
                self._session_subscriptions[session_id] = []
            self._session_subscriptions[session_id].append(subscription_id)

            # 사용자-세션 매핑
            if user:
                if user not in self._user_sessions:
                    self._user_sessions[user] = set()
                self._user_sessions[user].add(session_id)

            return sub

    async def unsubscribe(self, subscription_id: str, session_id: str) -> None:
        """
        구독 해제

        Args:
            subscription_id: 해제할 구독 ID
            session_id: WebSocket 세션 ID
        """
        async with self._lock:
            # 모든 목적지에서 해당 구독 제거
            for dest in list(self._subscriptions.keys()):
                self._subscriptions[dest] = [
                    s for s in self._subscriptions[dest] if s.id != subscription_id
                ]
                # 빈 리스트 정리
                if not self._subscriptions[dest]:
                    del self._subscriptions[dest]

            # 세션의 구독 목록에서 제거
            if session_id in self._session_subscriptions:
                self._session_subscriptions[session_id] = [
                    sid
                    for sid in self._session_subscriptions[session_id]
                    if sid != subscription_id
                ]

    async def disconnect(self, session_id: str) -> None:
        """
        세션 연결 해제 시 모든 구독 정리

        Args:
            session_id: 해제할 세션 ID
        """
        async with self._lock:
            # 세션의 모든 구독 ID 가져오기
            sub_ids = set(self._session_subscriptions.pop(session_id, []))

            # 해당 구독들 모두 제거
            for dest in list(self._subscriptions.keys()):
                self._subscriptions[dest] = [
                    s for s in self._subscriptions[dest] if s.id not in sub_ids
                ]
                if not self._subscriptions[dest]:
                    del self._subscriptions[dest]

            # 사용자-세션 매핑에서 제거
            for user, sessions in list(self._user_sessions.items()):
                sessions.discard(session_id)
                if not sessions:
                    del self._user_sessions[user]

    async def publish(self, message: "Message") -> int:
        """
        메시지 발행

        목적지 프리픽스에 따라 적절한 전송 방식 선택:
            - /topic/*: 브로드캐스트
            - /queue/*: 라운드로빈
            - /user/{userId}/*: 특정 사용자

        Args:
            message: 발행할 메시지

        Returns:
            전송된 구독자 수
        """
        destination = message.destination

        if destination.startswith("/topic/"):
            return await self._broadcast(destination, message)
        elif destination.startswith("/queue/"):
            return await self._send_to_one(destination, message)
        elif destination.startswith("/user/"):
            return await self._send_to_user_destination(destination, message)
        else:
            # 기본: 브로드캐스트
            return await self._broadcast(destination, message)

    async def send_to_user(
        self, user: str, destination: str, message: "Message"
    ) -> int:
        """
        특정 사용자에게 메시지 전송

        Args:
            user: 대상 사용자 ID
            destination: 목적지 (예: /queue/notifications)
            message: 전송할 메시지

        Returns:
            전송된 세션 수
        """
        # 사용자의 모든 세션에 전송
        async with self._lock:
            sessions = self._user_sessions.get(user, set())

        count = 0
        for session_id in sessions:
            # 해당 세션의 구독 중 목적지가 일치하는 것 찾기
            for subs in self._subscriptions.values():
                for sub in subs:
                    if sub.session_id == session_id and sub.matches(destination):
                        if sub.send_callback:
                            # 메시지에 구독 ID 설정
                            message.subscription_id = sub.id
                            await sub.send_callback(message)
                            count += 1

        return count

    async def _broadcast(self, destination: str, message: "Message") -> int:
        """
        모든 매칭 구독자에게 브로드캐스트

        Args:
            destination: 메시지 목적지
            message: 전송할 메시지

        Returns:
            전송된 구독자 수
        """
        count = 0

        # 모든 구독을 순회하며 패턴 매칭
        for pattern, subs in list(self._subscriptions.items()):
            for sub in subs:
                if sub.matches(destination):
                    if sub.send_callback:
                        # 메시지 복사 및 구독 ID 설정
                        msg_copy = Message(
                            destination=message.destination,
                            payload=message.payload,
                            headers=message.headers.copy(),
                            session_id=message.session_id,
                            user=message.user,
                            subscription_id=sub.id,
                        )
                        await sub.send_callback(msg_copy)
                        count += 1

        return count

    async def _send_to_one(self, destination: str, message: "Message") -> int:
        """
        라운드로빈으로 하나의 구독자에게 전송

        Args:
            destination: 메시지 목적지
            message: 전송할 메시지

        Returns:
            전송 성공 시 1, 실패 시 0
        """
        # 매칭되는 모든 구독 수집
        matching_subs: list[Subscription] = []
        for pattern, subs in self._subscriptions.items():
            for sub in subs:
                if sub.matches(destination):
                    matching_subs.append(sub)

        if not matching_subs:
            return 0

        # 라운드로빈 인덱스 관리
        index = self._queue_index.get(destination, 0)
        sub = matching_subs[index % len(matching_subs)]
        self._queue_index[destination] = index + 1

        if sub.send_callback:
            message.subscription_id = sub.id
            await sub.send_callback(message)
            return 1

        return 0

    async def _send_to_user_destination(
        self, destination: str, message: "Message"
    ) -> int:
        """
        /user/{userId}/... 형식의 목적지로 전송

        Args:
            destination: /user/{userId}/queue/... 형식
            message: 전송할 메시지

        Returns:
            전송된 세션 수
        """
        # /user/alice/queue/notifications -> user=alice, dest=/queue/notifications
        parts = destination.split("/")
        if len(parts) < 4:
            return 0

        user = parts[2]
        actual_destination = "/" + "/".join(parts[3:])

        return await self.send_to_user(user, actual_destination, message)

    def get_subscription_count(self, destination: str | None = None) -> int:
        """
        구독자 수 조회

        Args:
            destination: 특정 목적지 (None이면 전체)

        Returns:
            구독자 수
        """
        if destination:
            return len(self._subscriptions.get(destination, []))
        return sum(len(subs) for subs in self._subscriptions.values())

    def get_session_count(self) -> int:
        """활성 세션 수 조회"""
        return len(self._session_subscriptions)


# 순환 import 방지를 위해 여기서 import
from .message import Message
