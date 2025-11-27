"""Element 클래스"""

from typing import Any


class Element[T]:
    def __init__(self):
        self.metadata = dict[str, Any]()

    def __repr__(self) -> str:
        return f"Element(metadata={self.metadata})"
