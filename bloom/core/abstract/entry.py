"""Entry - Registry에 등록되는 항목의 추상 클래스

Manager → Registry → Entry 패턴에서 Entry는
Registry에 등록되어 실제 작업을 수행하는 단위입니다.

사용 예시:
    class StaticFileEntry(Entry[Path]):
        def __init__(self, path_prefix: str, directory: Path):
            super().__init__(directory)
            self.path_prefix = path_prefix

        async def handle(self, request: HttpRequest) -> HttpResponse | None:
            # 파일 서빙 로직
            ...
"""

from abc import ABC
from typing import Generic, TypeVar

T = TypeVar("T")


class Entry(ABC, Generic[T]):
    """
    Registry에 등록되는 항목의 추상 클래스

    Entry는 다음 책임을 가집니다:
    - 실제 작업을 수행하는 단위
    - Registry에 등록되어 Manager에 의해 관리됨
    - 타입 파라미터 T는 Entry가 관리하는 값의 타입

    사용 예시:
        class RouteEntry(Entry[Callable]):
            def __init__(self, path: str, handler: Callable):
                super().__init__(handler)
                self.path = path

            def matches(self, request_path: str) -> bool:
                return request_path.startswith(self.path)

        class MiddlewareEntry(Entry[Middleware]):
            def __init__(self, middleware: Middleware, priority: int = 0):
                super().__init__(middleware)
                self.priority = priority
    """

    def __init__(self, value: T):
        self._value = value

    @property
    def value(self) -> T:
        """Entry가 관리하는 값"""
        return self._value

    def __repr__(self) -> str:
        value_name = getattr(self._value, "__name__", str(self._value))
        return f"{self.__class__.__name__}({value_name})"
