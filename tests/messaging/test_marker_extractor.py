"""MessageParamMarker Registry 테스트"""

import inspect
from typing import Any, Annotated
import pytest
from bloom.web.messaging.params import (
    MessageParamMarker,
    DestinationVariableMarker,
    MessagePayloadMarker,
    MessageHeadersMarker,
    PrincipalMarker,
    SessionIdMarker,
    WebSocketSessionMarker,
    DestinationVariable,
    MessagePayload,
    MessageHeaders,
    Principal,
    SessionId,
    WebSocketSession,
    MessageParameterInfo,
    MessageParameterResolver,
    MessageResolverRegistry,
    DestinationVariableResolver,
    MessagePayloadResolver,
    MessageHeadersResolver,
    PrincipalResolver,
    SessionIdResolver,
    WebSocketSessionResolver,
    get_message_param_marker,
)


class TestMessageParamMarker:
    """MessageParamMarker 테스트"""

    def test_destination_variable_class_getitem(self):
        """DestinationVariable[str] → Annotated[str, DestinationVariableMarker()] 변환"""
        annotation = DestinationVariable[str]
        actual_type, marker = get_message_param_marker(annotation)
        assert actual_type is str
        assert isinstance(marker, DestinationVariableMarker)

    def test_message_payload_class_getitem(self):
        """MessagePayload[dict] → Annotated[dict, MessagePayloadMarker()] 변환"""
        annotation = MessagePayload[dict]
        actual_type, marker = get_message_param_marker(annotation)
        assert actual_type is dict
        assert isinstance(marker, MessagePayloadMarker)

    def test_message_headers_class_getitem(self):
        """MessageHeaders[dict] → Annotated[dict, MessageHeadersMarker()] 변환"""
        annotation = MessageHeaders[dict]
        actual_type, marker = get_message_param_marker(annotation)
        assert actual_type is dict
        assert isinstance(marker, MessageHeadersMarker)

    def test_principal_class_getitem(self):
        """Principal[int] → Annotated[int, PrincipalMarker()] 변환"""
        annotation = Principal[int]
        actual_type, marker = get_message_param_marker(annotation)
        assert actual_type is int
        assert isinstance(marker, PrincipalMarker)

    def test_session_id_class_getitem(self):
        """SessionId[str] → Annotated[str, SessionIdMarker()] 변환"""
        annotation = SessionId[str]
        actual_type, marker = get_message_param_marker(annotation)
        assert actual_type is str
        assert isinstance(marker, SessionIdMarker)

    def test_websocket_session_class_getitem(self):
        """WebSocketSession[Any] → Annotated[Any, WebSocketSessionMarker()] 변환"""
        annotation = WebSocketSession[Any]
        actual_type, marker = get_message_param_marker(annotation)
        assert actual_type is Any
        assert isinstance(marker, WebSocketSessionMarker)

    def test_custom_name_with_annotated(self):
        """Annotated[str, DestinationVariable(name="room_id")] 커스텀 이름 지원"""
        annotation = Annotated[str, DestinationVariableMarker(name="room_id")]
        actual_type, marker = get_message_param_marker(annotation)
        assert actual_type is str
        assert isinstance(marker, DestinationVariableMarker)
        assert marker.name == "room_id"

    def test_no_marker(self):
        """마커 없는 어노테이션"""
        actual_type, marker = get_message_param_marker(str)
        assert actual_type is str
        assert marker is None


class TestMessageParameterInfo:
    """MessageParameterInfo 테스트"""

    def test_from_parameter_with_type_annotation(self):
        """타입 어노테이션에서 ParameterInfo 생성"""
        def func(room: DestinationVariable[str]):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["room"]
        info = MessageParameterInfo.from_parameter(param)

        assert info.name == "room"
        assert info.actual_type is str
        assert isinstance(info.marker, DestinationVariableMarker)
        assert info.has_default is False

    def test_from_parameter_with_default_marker(self):
        """default 값으로 마커 사용"""
        def func(room: str = DestinationVariableMarker(name="room_id")):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["room"]
        info = MessageParameterInfo.from_parameter(param)

        assert info.name == "room"
        assert isinstance(info.marker, DestinationVariableMarker)
        assert info.marker.name == "room_id"
        assert info.has_default is False  # 마커는 default로 취급 안함

    def test_from_parameter_with_default_value(self):
        """실제 default 값"""
        def func(count: int = 10):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["count"]
        info = MessageParameterInfo.from_parameter(param)

        assert info.name == "count"
        assert info.has_default is True
        assert info.default == 10


class TestMessageResolverRegistry:
    """MessageResolverRegistry 테스트"""

    def test_registry_has_default_resolvers(self):
        """기본 리졸버들이 등록되어 있어야 함"""
        registry = MessageResolverRegistry()

        # 테스트용 파라미터 생성
        def sample_func(
            room_id: DestinationVariable[str],
            payload: MessagePayload[dict],
            headers: MessageHeaders[dict],
            principal: Principal[int],
            session_id: SessionId[str],
            ws_session: WebSocketSession[Any],
        ):
            pass

        sig = inspect.signature(sample_func)

        for name, param in sig.parameters.items():
            info = MessageParameterInfo.from_parameter(param)
            resolver = registry.find_resolver(info)
            assert resolver is not None, f"No resolver found for {name}"

    def test_destination_variable_resolver_supports(self):
        """DestinationVariable 리졸버 supports 테스트"""
        resolver = DestinationVariableResolver()

        def func(room_id: DestinationVariable[str]):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["room_id"]
        info = MessageParameterInfo.from_parameter(param)

        assert resolver.supports(info) is True

    def test_destination_variable_resolver_not_supports(self):
        """다른 타입은 지원하지 않아야 함"""
        resolver = DestinationVariableResolver()

        def func(payload: MessagePayload[dict]):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["payload"]
        info = MessageParameterInfo.from_parameter(param)

        assert resolver.supports(info) is False

    def test_registry_find_resolver(self):
        """레지스트리에서 올바른 리졸버 찾기"""
        registry = MessageResolverRegistry()

        def func(
            room_id: DestinationVariable[str],
            payload: MessagePayload[dict],
        ):
            pass

        sig = inspect.signature(func)

        dest_info = MessageParameterInfo.from_parameter(sig.parameters["room_id"])
        dest_resolver = registry.find_resolver(dest_info)
        assert isinstance(dest_resolver, DestinationVariableResolver)

        payload_info = MessageParameterInfo.from_parameter(sig.parameters["payload"])
        payload_resolver = registry.find_resolver(payload_info)
        assert isinstance(payload_resolver, MessagePayloadResolver)

    def test_registry_returns_none_for_unknown_param(self):
        """알 수 없는 파라미터에 대해 None 반환"""
        registry = MessageResolverRegistry()

        def func(unknown: str):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["unknown"]
        info = MessageParameterInfo.from_parameter(param)

        resolver = registry.find_resolver(info)
        assert resolver is None

    def test_registry_add_custom_resolver(self):
        """커스텀 리졸버 추가 테스트"""

        class CustomMarker(MessageParamMarker):
            pass

        class CustomResolver(MessageParameterResolver):
            def supports(self, param: MessageParameterInfo) -> bool:
                return isinstance(param.marker, CustomMarker)

            async def resolve(self, param: MessageParameterInfo, context: Any) -> Any:
                return "custom_value"

        registry = MessageResolverRegistry()
        registry.add_resolver(CustomResolver(), priority=0)

        def func(custom: Annotated[str, CustomMarker()]):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["custom"]
        info = MessageParameterInfo.from_parameter(param)

        resolver = registry.find_resolver(info)
        assert isinstance(resolver, CustomResolver)


class TestResolverExecution:
    """리졸버 실행 테스트"""

    @pytest.mark.asyncio
    async def test_destination_variable_resolve(self):
        """DestinationVariable 리졸버 실행"""
        resolver = DestinationVariableResolver()

        def func(room_id: DestinationVariable[str]):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["room_id"]
        info = MessageParameterInfo.from_parameter(param)

        class MockContext:
            path_variables = {"room_id": "test_room"}

        result = await resolver.resolve(info, MockContext())
        assert result == "test_room"

    @pytest.mark.asyncio
    async def test_message_payload_resolve(self):
        """MessagePayload 리졸버 실행"""
        resolver = MessagePayloadResolver()

        def func(data: MessagePayload[dict]):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["data"]
        info = MessageParameterInfo.from_parameter(param)

        class MockContext:
            payload = {"message": "hello"}

        result = await resolver.resolve(info, MockContext())
        assert result == {"message": "hello"}

    @pytest.mark.asyncio
    async def test_message_headers_resolve(self):
        """MessageHeaders 리졸버 실행"""
        resolver = MessageHeadersResolver()

        def func(headers: MessageHeaders[dict]):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["headers"]
        info = MessageParameterInfo.from_parameter(param)

        class MockContext:
            headers = {"content-type": "application/json"}

        result = await resolver.resolve(info, MockContext())
        assert result == {"content-type": "application/json"}

    @pytest.mark.asyncio
    async def test_message_headers_resolve_specific(self):
        """MessageHeaders 특정 헤더 리졸버 실행"""
        resolver = MessageHeadersResolver()

        def func(ct: Annotated[str, MessageHeadersMarker(name="content-type")]):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["ct"]
        info = MessageParameterInfo.from_parameter(param)

        class MockContext:
            headers = {"content-type": "application/json"}

        result = await resolver.resolve(info, MockContext())
        assert result == "application/json"

    @pytest.mark.asyncio
    async def test_registry_resolve(self):
        """레지스트리 resolve 통합 테스트"""
        registry = MessageResolverRegistry()

        def func(room_id: DestinationVariable[str]):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["room_id"]
        info = MessageParameterInfo.from_parameter(param)

        class MockContext:
            path_variables = {"room_id": "test_room"}

        result = await registry.resolve(info, MockContext())
        assert result == "test_room"
