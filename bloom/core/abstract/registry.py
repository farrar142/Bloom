"""AbstractRegistry - 레지스트리 추상 클래스

Registry는 항목들을 등록하고 관리하는 역할을 합니다.
리스트 관리, 순회 지원 등을 제공합니다.

Registry 생성 방식:
    1. Manager가 ContainerManager에서 Registry 인스턴스를 검색
    2. 존재하면 해당 Registry 사용
    3. 존재하지 않으면 Manager가 항목들을 수집하여 자동으로 Registry 생성

사용 예시:
    class RouteRegistry(AbstractRegistry[HttpMethodHandlerContainer]):
        pass
"""

from abc import ABC
from typing import Generic, TypeVar, Iterator

T = TypeVar("T")


class AbstractRegistry(ABC, Generic[T]):
    """
    레지스트리 추상 클래스

    Registry는 다음 책임을 가집니다:
    - 항목 리스트 관리
    - 순회 지원

    Registry 생성 방식:
        1. ContainerManager에서 Registry 인스턴스 검색
        2. 존재하면 해당 Registry 사용
        3. 존재하지 않으면 Manager가 항목들을 수집하여 자동으로 생성

    사용 예시:
        class RouteRegistry(AbstractRegistry[HttpMethodHandlerContainer]):
            pass
    """

    def __init__(self):
        self._entries: list[T] = []

    def register(self, item: T) -> None:
        """항목 등록"""
        self._entries.append(item)

    def unregister(self, item: T) -> bool:
        """항목 등록 해제, 성공 여부 반환"""
        if item in self._entries:
            self._entries.remove(item)
            return True
        return False

    def all(self) -> list[T]:
        """모든 항목 반환"""
        return list(self._entries)

    def first(self) -> T | None:
        """첫 번째 항목 반환"""
        return self._entries[0] if self._entries else None

    def last(self) -> T | None:
        """마지막 항목 반환"""
        return self._entries[-1] if self._entries else None

    def clear(self) -> None:
        """레지스트리 초기화"""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[T]:
        return iter(self._entries)

    def __contains__(self, item: T) -> bool:
        return item in self._entries

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({len(self._entries)} items)"
