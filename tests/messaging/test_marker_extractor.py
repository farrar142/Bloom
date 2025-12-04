"""MessageParamMarker Registry 테스트"""

import inspect
from typing import Any
import pytest
from bloom.web.messaging.params import (
    MessageParamMarker,
    DestinationVariableMarker,
    MessagePayloadMarker,
    MessageHeadersMarker,
    PrincipalMarker,
    SessionIdMarker,
    WebSocketSessionMarker,
    Destination,
    Payload,
    Headers,
    PrincipalParam,
    SessionIdParam,
    WebSocketSessionParam,
    MessageParamMarkerExtractor,
    MarkerExtractorRegistry,
    DestinationVariableExtractor,
    MessagePayloadExtractor,
    MessageHeadersExtractor,
    PrincipalExtractor,
    SessionIdExtractor,
    WebSocketSessionExtractor,
)


class TestMarkerExtractorRegistry:
    """MarkerExtractorRegistry 테스트"""

    def test_registry_has_default_extractors(self):
        """기본 추출기들이 등록되어 있어야 함"""
        registry = MarkerExtractorRegistry()
        
        # 테스트용 파라미터 생성
        def sample_func(
            room_id: str = Destination(),
            payload: dict = Payload(),
            headers: dict = Headers(),
            principal: Any = PrincipalParam(),
            session_id: str = SessionIdParam(),
            ws_session: Any = WebSocketSessionParam(),
        ):
            pass

        sig = inspect.signature(sample_func)
        
        for name, param in sig.parameters.items():
            extractor = registry.find_extractor(param)
            assert extractor is not None, f"No extractor found for {name}"

    def test_destination_variable_extractor_supports(self):
        """DestinationVariable 추출기 supports 테스트"""
        extractor = DestinationVariableExtractor()

        def func(room_id: str = Destination()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["room_id"]
        
        assert extractor.supports(param) is True

    def test_destination_variable_extractor_not_supports(self):
        """다른 타입은 지원하지 않아야 함"""
        extractor = DestinationVariableExtractor()

        def func(payload: dict = Payload()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["payload"]
        
        assert extractor.supports(param) is False

    def test_destination_variable_extractor_extract(self):
        """DestinationVariable 추출기 extract 테스트"""
        extractor = DestinationVariableExtractor()

        def func(room_id: str = Destination()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["room_id"]
        
        marker = extractor.extract(param)
        assert isinstance(marker, DestinationVariableMarker)

    def test_payload_extractor_supports(self):
        """Payload 추출기 supports 테스트"""
        extractor = MessagePayloadExtractor()

        def func(data: dict = Payload()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["data"]
        
        assert extractor.supports(param) is True

    def test_payload_extractor_extract(self):
        """Payload 추출기 extract 테스트"""
        extractor = MessagePayloadExtractor()

        def func(data: dict = Payload()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["data"]
        
        marker = extractor.extract(param)
        assert isinstance(marker, MessagePayloadMarker)

    def test_headers_extractor_supports(self):
        """Headers 추출기 supports 테스트"""
        extractor = MessageHeadersExtractor()

        def func(h: dict = Headers()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["h"]
        
        assert extractor.supports(param) is True

    def test_headers_extractor_extract(self):
        """Headers 추출기 extract 테스트"""
        extractor = MessageHeadersExtractor()

        def func(h: dict = Headers()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["h"]
        
        marker = extractor.extract(param)
        assert isinstance(marker, MessageHeadersMarker)

    def test_principal_extractor_supports(self):
        """Principal 추출기 supports 테스트"""
        extractor = PrincipalExtractor()

        def func(user: Any = PrincipalParam()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["user"]
        
        assert extractor.supports(param) is True

    def test_principal_extractor_extract(self):
        """Principal 추출기 extract 테스트"""
        extractor = PrincipalExtractor()

        def func(user: Any = PrincipalParam()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["user"]
        
        marker = extractor.extract(param)
        assert isinstance(marker, PrincipalMarker)

    def test_session_id_extractor_supports(self):
        """SessionId 추출기 supports 테스트"""
        extractor = SessionIdExtractor()

        def func(sid: str = SessionIdParam()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["sid"]
        
        assert extractor.supports(param) is True

    def test_session_id_extractor_extract(self):
        """SessionId 추출기 extract 테스트"""
        extractor = SessionIdExtractor()

        def func(sid: str = SessionIdParam()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["sid"]
        
        marker = extractor.extract(param)
        assert isinstance(marker, SessionIdMarker)

    def test_websocket_session_extractor_supports(self):
        """WebSocketSession 추출기 supports 테스트"""
        extractor = WebSocketSessionExtractor()

        def func(ws: Any = WebSocketSessionParam()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["ws"]
        
        assert extractor.supports(param) is True

    def test_websocket_session_extractor_extract(self):
        """WebSocketSession 추출기 extract 테스트"""
        extractor = WebSocketSessionExtractor()

        def func(ws: Any = WebSocketSessionParam()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["ws"]
        
        marker = extractor.extract(param)
        assert isinstance(marker, WebSocketSessionMarker)

    def test_registry_find_extractor(self):
        """레지스트리에서 올바른 추출기 찾기"""
        registry = MarkerExtractorRegistry()

        def func(
            room_id: str = Destination(),
            payload: dict = Payload(),
        ):
            pass

        sig = inspect.signature(func)

        dest_extractor = registry.find_extractor(sig.parameters["room_id"])
        assert isinstance(dest_extractor, DestinationVariableExtractor)

        payload_extractor = registry.find_extractor(sig.parameters["payload"])
        assert isinstance(payload_extractor, MessagePayloadExtractor)

    def test_registry_extract(self):
        """레지스트리 extract 통합 테스트"""
        registry = MarkerExtractorRegistry()

        def func(room_id: str = Destination()):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["room_id"]

        marker = registry.extract(param)
        assert isinstance(marker, DestinationVariableMarker)

    def test_registry_returns_none_for_unknown_param(self):
        """알 수 없는 파라미터에 대해 None 반환"""
        registry = MarkerExtractorRegistry()

        def func(unknown: str = "default"):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["unknown"]

        extractor = registry.find_extractor(param)
        assert extractor is None

    def test_registry_add_custom_extractor(self):
        """커스텀 추출기 추가 테스트"""
        
        class CustomMarker(MessageParamMarker):
            pass

        class CustomExtractor(MessageParamMarkerExtractor):
            def supports(self, param: inspect.Parameter) -> bool:
                return param.name == "custom_param"

            def extract(self, param: inspect.Parameter) -> MessageParamMarker:
                return CustomMarker()

        registry = MarkerExtractorRegistry()
        registry.add_extractor(CustomExtractor(), priority=0)

        def func(custom_param: str = "test"):
            pass

        sig = inspect.signature(func)
        param = sig.parameters["custom_param"]

        extractor = registry.find_extractor(param)
        assert isinstance(extractor, CustomExtractor)

        marker = extractor.extract(param)
        assert isinstance(marker, CustomMarker)
