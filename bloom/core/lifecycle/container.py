"""LifecycleHandlerContainer - 라이프사이클 핸들러 컨테이너

@PostConstruct, @PreDestroy 메서드를 담는 컨테이너입니다.
"""

from enum import Enum
from typing import Callable

from bloom.core.container import Element, HandlerContainer


class LifecycleType(Enum):
    """라이프사이클 타입"""

    POST_CONSTRUCT = "post_construct"
    PRE_DESTROY = "pre_destroy"


class LifecycleTypeElement[T](Element[T]):
    """라이프사이클 타입을 담는 Element"""

    def __init__(self, lifecycle_type: LifecycleType):
        super().__init__()
        self.metadata["lifecycle_type"] = lifecycle_type

    @property
    def lifecycle_type(self) -> LifecycleType:
        return self.metadata["lifecycle_type"]


class LifecycleHandlerContainer[**P, R](HandlerContainer[P, R]):
    """
    라이프사이클 핸들러 컨테이너

    @PostConstruct, @PreDestroy 메서드를 관리합니다.

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

    def __init__(self, handler_method: Callable[P, R]):
        super().__init__(handler_method)

    @property
    def lifecycle_type(self) -> LifecycleType | None:
        """라이프사이클 타입 반환"""
        return self.get_metadata("lifecycle_type")  # type: ignore

    def is_post_construct(self) -> bool:
        """@PostConstruct 메서드인지 확인"""
        return self.lifecycle_type == LifecycleType.POST_CONSTRUCT

    def is_pre_destroy(self) -> bool:
        """@PreDestroy 메서드인지 확인"""
        return self.lifecycle_type == LifecycleType.PRE_DESTROY

    def __repr__(self) -> str:
        owner = self.owner_cls.__name__ if self.owner_cls else "Unknown"
        lifecycle = self.lifecycle_type.value if self.lifecycle_type else "Unknown"
        return (
            f"LifecycleHandlerContainer("
            f"method={self.handler_method.__name__}, "
            f"lifecycle={lifecycle}, "
            f"owner={owner})"
        )
