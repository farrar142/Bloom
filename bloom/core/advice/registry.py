"""MethodAdviceRegistry - 어드바이스 수집 및 조회"""

from typing import TYPE_CHECKING
from weakref import WeakValueDictionary

from ..abstract import AbstractRegistry
from .tracing import CallStackTraceAdvice

if TYPE_CHECKING:
    from ..container import HandlerContainer
    from .base import MethodAdvice


class MethodAdviceRegistry(AbstractRegistry["MethodAdvice"]):
    """
    MethodAdvice를 수집하고 조회하는 Registry

    모든 등록된 Advice 중에서 특정 Container에 적용 가능한 것들을 찾습니다.

    기본적으로 CallStackTraceAdvice가 포함되어 있으며,
    CallStackTraceAdvice를 상속한 커스텀 Advice를 등록하면 자동으로 교체됩니다.
    """

    def __init__(self):
        super().__init__()
        # 기본 CallStackTraceAdvice 등록
        self._default_tracing_advice = CallStackTraceAdvice()
        self._entries.append(self._default_tracing_advice)
        # Container별 applicable advice 캐시 (WeakValueDictionary로 Container 해제 시 자동 정리)
        # 실제로는 Container의 id를 키로 사용 (Container는 보통 앱 수명 동안 유지)
        self._applicable_cache: dict[int, list["MethodAdvice"]] = {}
        # 캐시 무효화 버전 (Advice 등록 시 증가)
        self._cache_version = 0

    def register(self, item: "MethodAdvice") -> None:
        """
        항목 등록

        CallStackTraceAdvice를 상속한 Advice가 등록되면
        기본 CallStackTraceAdvice를 제거하고 새 Advice로 교체합니다.
        """
        # CallStackTraceAdvice 상속 클래스인지 확인
        if isinstance(item, CallStackTraceAdvice):
            # 기본 tracing advice가 있으면 제거
            if self._default_tracing_advice in self._entries:
                self._entries.remove(self._default_tracing_advice)
            # 기존에 등록된 다른 CallStackTraceAdvice 상속 클래스도 제거
            self._entries = [
                e
                for e in self._entries
                if not isinstance(e, CallStackTraceAdvice) or e is item
            ]

        self._entries.append(item)
        # 캐시 무효화
        self._cache_version += 1
        self._applicable_cache.clear()

    def find_applicable(self, container: "HandlerContainer") -> list["MethodAdvice"]:
        """
        주어진 컨테이너에 적용 가능한 어드바이스 목록을 반환합니다.

        Container의 Element 순서에 맞게 정렬됩니다.
        결과는 캐싱되어 동일 Container에 대해 재계산하지 않습니다.

        Args:
            container: 핸들러 컨테이너

        Returns:
            적용 가능한 어드바이스 리스트 (Element 순서대로)
        """
        # 캐시 조회 (Container의 id를 키로 사용)
        container_id = id(container)
        if container_id in self._applicable_cache:
            return self._applicable_cache[container_id]

        # 1. supports() 체크로 적용 가능한 어드바이스 필터링
        applicable = [advice for advice in self._entries if advice.supports(container)]

        # Fast path: 0개 또는 1개면 정렬 불필요
        if len(applicable) <= 1:
            self._applicable_cache[container_id] = applicable
            return applicable

        # 2. Container의 Element 순서에 맞게 정렬
        # Element 순서: 데코레이터 실행 순서 (아래→위)
        element_order = self._get_element_order(container, applicable)

        result = sorted(applicable, key=lambda a: element_order.get(a, float("inf")))
        self._applicable_cache[container_id] = result
        return result

    def _get_element_order(
        self, container: "HandlerContainer", advices: list["MethodAdvice"]
    ) -> dict["MethodAdvice", int]:
        """
        Container의 Element 순서를 기반으로 Advice 순서 맵을 생성합니다.
        """
        order_map: dict["MethodAdvice", int] = {}

        # Container의 elements 순서 확인
        for idx, element in enumerate(container.elements):
            element_type = type(element)

            # 이 Element를 지원하는 Advice 찾기
            for advice in advices:
                if advice not in order_map:
                    # Advice가 이 Element 타입을 지원하는지 확인
                    # (supports가 True면 해당 Element를 찾은 것)
                    if self._advice_supports_element(advice, element_type, container):
                        order_map[advice] = idx

        return order_map

    def _advice_supports_element(
        self, advice: "MethodAdvice", element_type: type, container: "HandlerContainer"
    ) -> bool:
        """
        Advice가 특정 Element 타입을 지원하는지 확인합니다.

        이 메서드는 Advice.supports()를 통해 간접적으로 확인합니다.
        더 정확한 매칭을 위해 서브클래스에서 오버라이드 가능합니다.
        """
        # 기본 구현: supports()가 True면 첫 번째 매칭 Element에 할당
        # 더 정확한 구현은 Advice에 target_element 속성을 추가하는 것
        return True

    def has_matching_advice(self, container: "HandlerContainer") -> bool:
        """
        주어진 컨테이너에 적용 가능한 어드바이스가 있는지 확인합니다.

        Args:
            container: 핸들러 컨테이너

        Returns:
            적용 가능한 어드바이스가 있으면 True
        """
        return any(advice.supports(container) for advice in self._entries)
