"""메시지 매핑 레지스트리

MessageMapping과 SubscribeMapping을 PathTrie로 관리합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from bloom.web.routing.trie import PathTrie, TrieMatch, PathIncluded

if TYPE_CHECKING:
    from .decorators import MessageMappingInfo, SubscribeMappingInfo, MessageControllerInfo


# =============================================================================
# PathIncluded Wrappers
# =============================================================================


@dataclass
class MessageMappingEntry(PathIncluded):
    """MessageMapping을 PathTrie에 저장하기 위한 래퍼"""

    path: str  # destination
    info: "MessageMappingInfo"
    controller_class: type
    method: Callable[..., Any]


@dataclass
class SubscribeMappingEntry(PathIncluded):
    """SubscribeMapping을 PathTrie에 저장하기 위한 래퍼"""

    path: str  # destination
    info: "SubscribeMappingInfo"
    controller_class: type
    method: Callable[..., Any]


# =============================================================================
# Match Results
# =============================================================================


@dataclass
class MessageHandlerMatch:
    """MessageMapping 매칭 결과"""

    entry: MessageMappingEntry
    path_params: dict[str, str] = field(default_factory=dict)

    @property
    def handler(self) -> Callable[..., Any]:
        return self.entry.method

    @property
    def controller_class(self) -> type:
        return self.entry.controller_class

    @property
    def destination(self) -> str:
        return self.entry.info.destination


@dataclass
class SubscribeHandlerMatch:
    """SubscribeMapping 매칭 결과"""

    entry: SubscribeMappingEntry
    path_params: dict[str, str] = field(default_factory=dict)

    @property
    def handler(self) -> Callable[..., Any]:
        return self.entry.method

    @property
    def controller_class(self) -> type:
        return self.entry.controller_class

    @property
    def destination(self) -> str:
        return self.entry.info.destination


# =============================================================================
# Registry
# =============================================================================


class MessageMappingRegistry:
    """MessageMapping/SubscribeMapping 레지스트리

    PathTrie를 사용하여 destination 기반 핸들러 매칭을 수행합니다.

    사용 예:
        registry = MessageMappingRegistry()

        @MessageController("/app")
        class ChatController:
            @MessageMapping("/chat/{room}")
            async def handle_chat(self, room: str):
                pass

        registry.register_controller(ChatController)

        # 매칭
        result = registry.find_message_handler("/app/chat/general")
        if result:
            print(result.path_params)  # {"room": "general"}
    """

    def __init__(self) -> None:
        self._message_trie: PathTrie[MessageMappingEntry] = PathTrie()
        self._subscribe_trie: PathTrie[SubscribeMappingEntry] = PathTrie()
        self._controllers: list[type] = []

    def register_controller(self, controller_class: type) -> None:
        """컨트롤러 등록

        Args:
            controller_class: @MessageController로 데코레이트된 클래스
        """
        from .decorators import get_message_controller_info

        info = get_message_controller_info(controller_class)
        if info is None:
            raise ValueError(f"{controller_class.__name__} is not a MessageController")

        self._controllers.append(controller_class)

        # MessageMapping 등록
        for mapping in info.message_mappings:
            entry = MessageMappingEntry(
                path=mapping.destination,
                info=mapping,
                controller_class=controller_class,
                method=mapping.method,
            )
            self._message_trie.insert(entry)

        # SubscribeMapping 등록
        for mapping in info.subscribe_mappings:
            entry = SubscribeMappingEntry(
                path=mapping.destination,
                info=mapping,
                controller_class=controller_class,
                method=mapping.method,
            )
            self._subscribe_trie.insert(entry)

    def find_message_handler(self, destination: str) -> MessageHandlerMatch | None:
        """MessageMapping 핸들러 찾기

        Args:
            destination: 매칭할 destination (예: "/app/chat/general")

        Returns:
            매칭 결과 또는 None
        """
        result = self._message_trie.find(destination)
        if result is None:
            return None

        return MessageHandlerMatch(
            entry=result.item,
            path_params=result.path_params,
        )

    def find_subscribe_handler(self, destination: str) -> SubscribeHandlerMatch | None:
        """SubscribeMapping 핸들러 찾기

        Args:
            destination: 매칭할 destination (예: "/app/notifications/user123")

        Returns:
            매칭 결과 또는 None
        """
        result = self._subscribe_trie.find(destination)
        if result is None:
            return None

        return SubscribeHandlerMatch(
            entry=result.item,
            path_params=result.path_params,
        )

    def get_all_message_mappings(self) -> list[MessageMappingEntry]:
        """모든 MessageMapping 조회"""
        return self._message_trie.get_all()

    def get_all_subscribe_mappings(self) -> list[SubscribeMappingEntry]:
        """모든 SubscribeMapping 조회"""
        return self._subscribe_trie.get_all()

    def get_controllers(self) -> list[type]:
        """등록된 모든 컨트롤러 조회"""
        return list(self._controllers)

    def clear(self) -> None:
        """레지스트리 초기화"""
        self._message_trie = PathTrie()
        self._subscribe_trie = PathTrie()
        self._controllers.clear()
