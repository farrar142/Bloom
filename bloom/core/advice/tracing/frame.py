"""CallFrame - 콜스택 프레임 정의"""

from dataclasses import dataclass
import time
from typing import Any


@dataclass(frozen=True)
class CallFrame:
    """
    콜스택 프레임 (불변)

    각 메서드 호출을 나타내는 불변 객체입니다.
    frozen=True로 해시 가능하고 스레드 안전합니다.

    Attributes:
        instance_type: 인스턴스 클래스명
        method_name: 메서드명
        start_time: 호출 시작 시간 (time.time())
        trace_id: 요청별 고유 추적 ID
        depth: 콜스택 깊이 (0부터 시작)
        args_summary: 인자 요약 (디버깅용, 선택적)
    """

    instance_type: str
    method_name: str
    start_time: float
    trace_id: str
    depth: int
    args_summary: str = ""

    @property
    def elapsed_ms(self) -> float:
        """현재까지 경과 시간 (밀리초)"""
        return (time.time() - self.start_time) * 1000

    @property
    def full_name(self) -> str:
        """전체 메서드명 (클래스.메서드)"""
        return f"{self.instance_type}.{self.method_name}"

    def __str__(self) -> str:
        indent = "  " * self.depth
        if self.args_summary:
            return f"{indent}[{self.depth}] {self.full_name}({self.args_summary})"
        return f"{indent}[{self.depth}] {self.full_name}()"

    def __repr__(self) -> str:
        return (
            f"CallFrame(depth={self.depth}, "
            f"method={self.full_name!r}, "
            f"trace_id={self.trace_id!r})"
        )
