"""라이프사이클 관리 모듈

Manager → Registry → Container(Entry) 패턴을 따릅니다.

- LifecycleManager: 전체 라이프사이클 조율, Container별 핸들러 탐색 및 호출
- LifecycleRegistry: LifecycleHandlerContainer 캐싱
- LifecycleHandlerContainer: @PostConstruct/@PreDestroy 메서드 컨테이너

사용법:
    @Component
    class DatabaseConnection:
        config: Config

        @PostConstruct
        def connect(self):
            self.connection = create_connection(self.config.db_url)

        @PreDestroy
        def disconnect(self):
            self.connection.close()
"""

from .container import (
    LifecycleHandlerContainer,
    LifecycleType,
    LifecycleTypeElement,
)
from .registry import LifecycleRegistry
from .manager import LifecycleManager

__all__ = [
    "LifecycleHandlerContainer",
    "LifecycleType",
    "LifecycleTypeElement",
    "LifecycleRegistry",
    "LifecycleManager",
]
