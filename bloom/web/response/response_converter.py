from abc import ABC, abstractmethod
from typing import Any

from .response import HttpResponse, JSONResponse


class ResponseConverter(ABC):
    """응답 변환기 추상 클래스"""

    @abstractmethod
    def supports(self, result: Any) -> bool:
        """주어진 결과를 처리할 수 있는지 확인"""
        pass

    @abstractmethod
    def convert(self, result: Any) -> HttpResponse:
        """결과를 Response 객체로 변환"""
        pass


class ResponseTypeConverter(ResponseConverter):
    """Response 타입을 그대로 반환하는 컨버터"""

    def supports(self, result: Any) -> bool:
        return isinstance(result, HttpResponse)

    def convert(self, result: Any) -> HttpResponse:
        return result


class DictResponseConverter(ResponseConverter):
    """dict를 JSONResponse로 변환하는 컨버터"""

    def supports(self, result: Any) -> bool:
        return isinstance(result, dict)

    def convert(self, result: Any) -> HttpResponse:
        return JSONResponse(result)


class StringResponseConverter(ResponseConverter):
    """str을 text/plain Response로 변환하는 컨버터"""

    def supports(self, result: Any) -> bool:
        return isinstance(result, str)

    def convert(self, result: Any) -> HttpResponse:
        return HttpResponse(content=result, media_type="text/plain")


class DefaultResponseConverter(ResponseConverter):
    """기본 컨버터 - 모든 것을 JSONResponse로 변환"""

    def supports(self, result: Any) -> bool:
        return True

    def convert(self, result: Any) -> HttpResponse:
        return JSONResponse(result)


class ResponseConverterRegistry:
    """응답 변환기 레지스트리"""

    def __init__(self):
        self._converters: list[tuple[int, ResponseConverter]] = []
        self._register_default_converters()

    def _register_default_converters(self):
        """기본 컨버터 등록"""
        self.add_converter(ResponseTypeConverter(), priority=100)
        self.add_converter(DictResponseConverter(), priority=200)
        self.add_converter(StringResponseConverter(), priority=300)
        self.add_converter(
            DefaultResponseConverter(), priority=1000
        )  # 가장 낮은 우선순위

    def add_converter(self, converter: ResponseConverter, priority: int = 500):
        """컨버터 추가 (낮은 priority가 우선)"""
        self._converters.append((priority, converter))
        self._converters.sort(key=lambda x: x[0])

    def find_converter(self, result: Any) -> ResponseConverter | None:
        """주어진 결과를 처리할 수 있는 컨버터 찾기"""
        for _, converter in self._converters:
            if converter.supports(result):
                return converter
        return None

    def convert(self, result: Any) -> HttpResponse:
        """결과를 Response로 변환"""
        converter = self.find_converter(result)
        if converter:
            return converter.convert(result)
        # 기본적으로 JSONResponse 반환
        return JSONResponse(result)


# 전역 레지스트리 인스턴스
_default_registry = None


def get_response_converter_registry() -> ResponseConverterRegistry:
    """기본 ResponseConverterRegistry 인스턴스 반환"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ResponseConverterRegistry()
    return _default_registry
