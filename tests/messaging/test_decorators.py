"""메시징 데코레이터 테스트"""

import pytest
import re
from typing import Annotated

from bloom.web.messaging.decorators import (
    MessageMapping,
    SubscribeMapping,
    SendTo,
    MessageController,
    MessageMappingInfo,
    SubscribeMappingInfo,
    SendToInfo,
    MessageControllerInfo,
    get_message_controller_info,
    get_send_to_info,
    _compile_destination_pattern,
    _match_destination,
)


class TestCompileDestinationPattern:
    """_compile_destination_pattern 테스트"""

    def test_simple_pattern(self):
        """단순 패턴"""
        pattern, variables = _compile_destination_pattern("/topic/chat")

        assert variables == []
        assert pattern.match("/topic/chat")
        assert not pattern.match("/topic/other")

    def test_single_variable(self):
        """단일 변수 패턴"""
        pattern, variables = _compile_destination_pattern("/topic/{room}")

        assert variables == ["room"]
        match = pattern.match("/topic/general")
        assert match
        assert match.group(1) == "general"

    def test_multiple_variables(self):
        """다중 변수 패턴"""
        pattern, variables = _compile_destination_pattern("/chat/{room}/{user}")

        assert variables == ["room", "user"]
        match = pattern.match("/chat/general/john")
        assert match
        assert match.groups() == ("general", "john")

    def test_int_type_hint(self):
        """정수 타입 힌트"""
        pattern, variables = _compile_destination_pattern("/user/{id:int}")

        assert variables == ["id"]
        assert pattern.match("/user/123")
        assert not pattern.match("/user/abc")

    def test_path_type_hint(self):
        """경로 타입 힌트"""
        pattern, variables = _compile_destination_pattern("/files/{path:path}")

        assert variables == ["path"]
        match = pattern.match("/files/a/b/c.txt")
        assert match
        assert match.group(1) == "a/b/c.txt"


class TestMatchDestination:
    """_match_destination 테스트"""

    def test_match_success(self):
        """매칭 성공"""
        pattern, variables = _compile_destination_pattern("/chat/{room}/{action}")
        result = _match_destination(pattern, variables, "/chat/general/join")

        assert result == {"room": "general", "action": "join"}

    def test_match_failure(self):
        """매칭 실패"""
        pattern, variables = _compile_destination_pattern("/chat/{room}")
        result = _match_destination(pattern, variables, "/topic/news")

        assert result is None

    def test_match_no_variables(self):
        """변수 없는 패턴"""
        pattern, variables = _compile_destination_pattern("/topic/chat")
        result = _match_destination(pattern, variables, "/topic/chat")

        assert result == {}


class TestMessageMappingDecorator:
    """@MessageMapping 데코레이터 테스트"""

    def test_basic_decoration(self):
        """기본 데코레이션"""

        @MessageMapping("/chat/{room}")
        def handle_chat(room: str):
            pass

        assert hasattr(handle_chat, "__bloom_message_mappings__")
        mappings = handle_chat.__bloom_message_mappings__
        assert len(mappings) == 1

        info = mappings[0]
        assert info.destination == "/chat/{room}"
        assert info.variables == ["room"]
        assert info.method is handle_chat

    def test_multiple_mappings(self):
        """여러 매핑"""

        @MessageMapping("/chat/{room}")
        @MessageMapping("/direct/{user}")
        def handle_message(target: str):
            pass

        mappings = handle_message.__bloom_message_mappings__
        assert len(mappings) == 2

    def test_async_handler(self):
        """비동기 핸들러"""

        @MessageMapping("/async/{id}")
        async def async_handler(id: str):
            pass

        assert hasattr(async_handler, "__bloom_message_mappings__")


class TestSubscribeMappingDecorator:
    """@SubscribeMapping 데코레이터 테스트"""

    def test_basic_decoration(self):
        """기본 데코레이션"""

        @SubscribeMapping("/topic/users/{room}")
        def on_subscribe(room: str):
            return []

        assert hasattr(on_subscribe, "__bloom_subscribe_mappings__")
        mappings = on_subscribe.__bloom_subscribe_mappings__
        assert len(mappings) == 1

        info = mappings[0]
        assert info.destination == "/topic/users/{room}"
        assert info.variables == ["room"]


class TestSendToDecorator:
    """@SendTo 데코레이터 테스트"""

    def test_single_destination(self):
        """단일 destination"""

        @SendTo("/topic/chat")
        def handle():
            return {}

        assert hasattr(handle, "__bloom_send_to__")
        send_to_list = handle.__bloom_send_to__
        assert len(send_to_list) == 1

        info = send_to_list[0]
        assert info.destinations == ["/topic/chat"]
        assert info.broadcast is True

    def test_multiple_destinations(self):
        """다중 destination"""

        @SendTo("/topic/a", "/topic/b")
        def handle():
            return {}

        info = handle.__bloom_send_to__[0]
        assert info.destinations == ["/topic/a", "/topic/b"]

    def test_broadcast_false(self):
        """요청자에게만 전송"""

        @SendTo("/user/reply", broadcast=False)
        def handle():
            return {}

        info = handle.__bloom_send_to__[0]
        assert info.broadcast is False

    def test_combined_with_message_mapping(self):
        """MessageMapping과 함께 사용"""

        @MessageMapping("/chat/{room}")
        @SendTo("/topic/chat/{room}")
        def handle_chat(room: str):
            return {}

        assert hasattr(handle_chat, "__bloom_message_mappings__")
        assert hasattr(handle_chat, "__bloom_send_to__")


class TestMessageControllerDecorator:
    """@MessageController 데코레이터 테스트"""

    def test_basic_controller(self):
        """기본 컨트롤러"""

        @MessageController()
        class ChatController:
            @MessageMapping("/chat")
            def handle(self):
                pass

        info = get_message_controller_info(ChatController)
        assert info is not None
        assert info.destination_prefix == ""
        assert len(info.message_mappings) == 1

    def test_controller_with_prefix(self):
        """prefix가 있는 컨트롤러"""

        @MessageController("/api")
        class ApiController:
            @MessageMapping("/message")
            def handle(self):
                pass

        info = get_message_controller_info(ApiController)
        assert info is not None
        assert info.destination_prefix == "/api"

    def test_controller_with_multiple_handlers(self):
        """여러 핸들러를 가진 컨트롤러"""

        @MessageController()
        class MultiController:
            @MessageMapping("/a")
            def handle_a(self):
                pass

            @SubscribeMapping("/b")
            def handle_b(self):
                pass

            @MessageMapping("/c")
            @SendTo("/topic/c")
            def handle_c(self):
                pass

        info = get_message_controller_info(MultiController)
        assert info is not None
        assert len(info.message_mappings) == 2  # a, c
        assert len(info.subscribe_mappings) == 1  # b


class TestGetSendToInfo:
    """get_send_to_info 함수 테스트"""

    def test_get_send_to(self):
        """SendTo 정보 조회"""

        @SendTo("/topic/test")
        def handler():
            pass

        info_list = get_send_to_info(handler)
        assert len(info_list) == 1
        assert info_list[0].destinations == ["/topic/test"]

    def test_no_send_to(self):
        """SendTo 없는 함수"""

        def handler():
            pass

        info_list = get_send_to_info(handler)
        assert info_list == []


class TestGetMessageControllerInfo:
    """get_message_controller_info 함수 테스트"""

    def test_non_controller(self):
        """컨트롤러가 아닌 클래스"""

        class NotAController:
            pass

        info = get_message_controller_info(NotAController)
        assert info is None
