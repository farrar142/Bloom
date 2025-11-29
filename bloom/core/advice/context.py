"""InvocationContext - 메서드 호출 컨텍스트"""

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..container import HandlerContainer


@dataclass
class InvocationContext:
    """
    메서드 호출 시 전달되는 컨텍스트 정보

    Advice에서 메서드 호출에 필요한 정보에 접근할 수 있습니다.
    """

    container: "HandlerContainer"
    """핸들러 컨테이너"""

    instance: Any
    """메서드가 바인딩된 인스턴스"""

    args: tuple[Any, ...]
    """위치 인자"""

    kwargs: dict[str, Any]
    """키워드 인자"""

    attributes: dict[str, Any] = field(default_factory=dict)
    """Advice 간 데이터 공유용 속성 (before에서 저장, after에서 사용)"""

    def set_attribute(self, key: str, value: Any) -> None:
        """속성 저장"""
        self.attributes[key] = value

    def get_attribute(self, key: str, default: Any = None) -> Any:
        """속성 조회"""
        return self.attributes.get(key, default)
