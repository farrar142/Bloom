"""AbstractRegistry - 레지스트리 추상 클래스

Registry는 Entry들을 등록하고 관리하는 역할을 합니다.
Entry 리스트 관리, 순회 지원 등을 제공합니다.

Registry 생성 방식:
    1. Manager가 ContainerManager에서 Registry 인스턴스를 검색
    2. 존재하면 해당 Registry 사용
    3. 존재하지 않으면 Manager가 Entry들을 수집하여 자동으로 Registry 생성

사용 예시:
    class StaticFilesRegistry(AbstractRegistry[StaticFileEntry]):
        pass
"""

from abc import ABC
from typing import Generic, TypeVar, Iterator

from .entry import Entry

E = TypeVar("E", bound=Entry)  # Entry type


class AbstractRegistry(ABC, Generic[E]):
    """
    레지스트리 추상 클래스

    Registry는 다음 책임을 가집니다:
    - Entry 리스트 관리
    - 순회 지원

    Registry 생성 방식:
        1. ContainerManager에서 Registry 인스턴스 검색
        2. 존재하면 해당 Registry 사용
        3. 존재하지 않으면 Manager가 Entry들을 수집하여 자동으로 생성

    사용 예시:
        class HandlerRegistry(AbstractRegistry[HandlerEntry]):
            pass
    """

    def __init__(self):
        self._entries: list[E] = []

    def register(self, entry: E) -> None:
        """Entry 등록"""
        self._entries.append(entry)

    def unregister(self, entry: E) -> bool:
        """Entry 등록 해제, 성공 여부 반환"""
        if entry in self._entries:
            self._entries.remove(entry)
            return True
        return False

    def all(self) -> list[E]:
        """모든 Entry 반환"""
        return list(self._entries)

    def first(self) -> E | None:
        """첫 번째 Entry 반환"""
        return self._entries[0] if self._entries else None

    def last(self) -> E | None:
        """마지막 Entry 반환"""
        return self._entries[-1] if self._entries else None

    def clear(self) -> None:
        """레지스트리 초기화"""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self) -> Iterator[E]:
        return iter(self._entries)

    def __contains__(self, entry: E) -> bool:
        return entry in self._entries

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({len(self._entries)} entries)"
