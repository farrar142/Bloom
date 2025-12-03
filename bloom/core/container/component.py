"""ComponentContainer 클래스"""

from .base import Container


class ComponentContainer[T](Container[T]):
    def __init__(self, target: type[T]):
        from .element import PriorityElement

        super().__init__(target)
        # PriorityElement 추가 (priority 30)
        self.add_element(PriorityElement(30))
