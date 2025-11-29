"""MethodAdviceRegistry - 어드바이스 수집 및 조회"""

from typing import TYPE_CHECKING

from ..abstract import AbstractRegistry

if TYPE_CHECKING:
    from ..container import HandlerContainer
    from .base import MethodAdvice


class MethodAdviceRegistry(AbstractRegistry["MethodAdvice"]):
    """
    MethodAdvice를 수집하고 조회하는 Registry

    모든 등록된 Advice 중에서 특정 Container에 적용 가능한 것들을 찾습니다.
    """

    def find_applicable(self, container: "HandlerContainer") -> list["MethodAdvice"]:
        """
        주어진 컨테이너에 적용 가능한 어드바이스 목록을 반환합니다.

        Container의 Element 순서에 맞게 정렬됩니다.

        Args:
            container: 핸들러 컨테이너

        Returns:
            적용 가능한 어드바이스 리스트 (Element 순서대로)
        """
        # 1. supports() 체크로 적용 가능한 어드바이스 필터링
        applicable = [advice for advice in self._entries if advice.supports(container)]

        if not applicable:
            return []

        # 2. Container의 Element 순서에 맞게 정렬
        # Element 순서: 데코레이터 실행 순서 (아래→위)
        element_order = self._get_element_order(container, applicable)

        return sorted(applicable, key=lambda a: element_order.get(a, float("inf")))

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
