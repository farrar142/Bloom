"""bloom.core.scope - 스코프 정의"""

from enum import Enum, auto


class ScopeEnum(Enum):
    """컴포넌트 인스턴스 스코프"""

    SINGLETON = auto()  # 앱 전체에서 단일 인스턴스
    REQUEST = auto()  # HTTP 요청마다 새 인스턴스
    CALL = auto()  # @Handler 메서드 호출마다 새 인스턴스
