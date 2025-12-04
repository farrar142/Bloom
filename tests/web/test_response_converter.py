"""Response Converter Registry 테스트"""

import pytest
from bloom.web.response import Response, JSONResponse
from bloom.web.routing.response_converter import (
    ResponseConverter,
    ResponseConverterRegistry,
    ResponseTypeConverter,
    DictResponseConverter,
    StringResponseConverter,
    DefaultResponseConverter,
)


class TestResponseConverterRegistry:
    """ResponseConverterRegistry 테스트"""

    def test_registry_has_default_converters(self):
        """기본 컨버터들이 등록되어 있어야 함"""
        registry = ResponseConverterRegistry()
        # 기본 컨버터 확인
        assert registry.find_converter(Response("test")) is not None
        assert registry.find_converter({"key": "value"}) is not None
        assert registry.find_converter("hello") is not None
        assert registry.find_converter(123) is not None  # default converter

    def test_response_type_converter_supports(self):
        """Response 타입 컨버터 supports 테스트"""
        converter = ResponseTypeConverter()
        assert converter.supports(Response("test")) is True
        assert converter.supports(JSONResponse({"key": "value"})) is True
        assert converter.supports("string") is False
        assert converter.supports({"dict": "value"}) is False

    def test_response_type_converter_convert(self):
        """Response 타입 컨버터 convert 테스트"""
        converter = ResponseTypeConverter()
        response = Response("test")
        result = converter.convert(response)
        assert result is response  # 동일 객체 반환

    def test_dict_response_converter_supports(self):
        """Dict 컨버터 supports 테스트"""
        converter = DictResponseConverter()
        assert converter.supports({"key": "value"}) is True
        assert converter.supports({}) is True
        assert converter.supports("string") is False
        assert converter.supports([1, 2, 3]) is False  # list는 dict가 아님

    def test_dict_response_converter_convert(self):
        """Dict 컨버터 convert 테스트"""
        converter = DictResponseConverter()
        result = converter.convert({"message": "hello"})
        assert isinstance(result, JSONResponse)

    def test_string_response_converter_supports(self):
        """String 컨버터 supports 테스트"""
        converter = StringResponseConverter()
        assert converter.supports("hello") is True
        assert converter.supports("") is True
        assert converter.supports(123) is False
        assert converter.supports({"dict": "value"}) is False

    def test_string_response_converter_convert(self):
        """String 컨버터 convert 테스트"""
        converter = StringResponseConverter()
        result = converter.convert("hello world")
        assert isinstance(result, Response)
        assert result.media_type == "text/plain"

    def test_default_response_converter_supports(self):
        """Default 컨버터는 모든 것을 지원해야 함"""
        converter = DefaultResponseConverter()
        assert converter.supports(123) is True
        assert converter.supports([1, 2, 3]) is True
        assert converter.supports(None) is True
        assert converter.supports(object()) is True

    def test_default_response_converter_convert(self):
        """Default 컨버터는 JSONResponse로 변환"""
        converter = DefaultResponseConverter()
        result = converter.convert([1, 2, 3])
        assert isinstance(result, JSONResponse)

    def test_registry_priority(self):
        """컨버터 우선순위 테스트 - 먼저 등록된 것이 우선"""
        registry = ResponseConverterRegistry()

        # Response 객체는 ResponseTypeConverter가 처리
        response = Response("test")
        converter = registry.find_converter(response)
        assert isinstance(converter, ResponseTypeConverter)

        # dict는 DictResponseConverter가 처리
        converter = registry.find_converter({"key": "value"})
        assert isinstance(converter, DictResponseConverter)

    def test_registry_add_custom_converter(self):
        """커스텀 컨버터 추가 테스트"""

        class CustomListConverter(ResponseConverter):
            def supports(self, result) -> bool:
                return isinstance(result, list)

            def convert(self, result) -> Response:
                return JSONResponse({"items": result, "count": len(result)})

        registry = ResponseConverterRegistry()
        registry.add_converter(CustomListConverter(), priority=0)  # 최우선

        # list는 이제 CustomListConverter가 처리
        converter = registry.find_converter([1, 2, 3])
        assert isinstance(converter, CustomListConverter)

        result = converter.convert([1, 2, 3])
        assert isinstance(result, JSONResponse)

    def test_registry_convert(self):
        """registry.convert 통합 테스트"""
        registry = ResponseConverterRegistry()

        # Response 객체
        response = Response("test")
        assert registry.convert(response) is response

        # dict
        result = registry.convert({"message": "hello"})
        assert isinstance(result, JSONResponse)

        # string
        result = registry.convert("hello")
        assert isinstance(result, Response)
        assert result.media_type == "text/plain"

        # 기타
        result = registry.convert(12345)
        assert isinstance(result, JSONResponse)
