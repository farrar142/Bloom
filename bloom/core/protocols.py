"""Bloom 프레임워크 공통 프로토콜

타입 안전한 직렬화/역직렬화를 위한 프로토콜을 정의합니다.
"""

from __future__ import annotations

from typing import Protocol, Self, runtime_checkable


@runtime_checkable
class Serializable(Protocol):
    """
    JSON 직렬화/역직렬화 프로토콜

    이 프로토콜을 구현하는 클래스는 to_json()과 from_json()을 제공합니다.

    Example:
        ```python
        from dataclasses import dataclass
        from bloom.core.protocols import Serializable

        @dataclass
        class MyMessage:
            name: str
            value: int

            def to_json(self) -> str:
                return json.dumps({"name": self.name, "value": self.value})

            @classmethod
            def from_json(cls, data: str) -> "MyMessage":
                obj = json.loads(data)
                return cls(name=obj["name"], value=obj["value"])

        # 사용
        msg = MyMessage(name="test", value=42)
        json_str = msg.to_json()
        restored = MyMessage.from_json(json_str)
        ```
    """

    def to_json(self) -> str:
        """객체를 JSON 문자열로 직렬화"""
        ...

    @classmethod
    def from_json(cls, data: str) -> Self:
        """JSON 문자열에서 객체 역직렬화"""
        ...
