"""Element 클래스"""

from typing import Any


class Element[T]:
    def __init__(self):
        self.metadata = dict[str, Any]()

    def __repr__(self) -> str:
        return f"Element(metadata={self.metadata})"


class OrderElement(Element):
    """
    Factory/Handler의 실행 순서를 지정하는 Element

    동일 타입을 반환하는 여러 Factory가 있을 때 실행 순서를 결정합니다.
    숫자가 낮을수록 먼저 실행됩니다.

    사용 예시:
        @Component
        class Config:
            @Factory
            def create(self) -> MyType:
                return MyType()

            @Factory
            @Order(1)
            def modify1(self, val: MyType) -> MyType:
                val.x += 1
                return val

            @Factory
            @Order(2)
            def modify2(self, val: MyType) -> MyType:
                val.x += 2
                return val
    """

    def __init__(self, order: int):
        super().__init__()
        self.metadata["order"] = order

    @property
    def order(self) -> int:
        return self.metadata.get("order", 0)
