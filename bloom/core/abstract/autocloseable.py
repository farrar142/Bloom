from abc import ABC, abstractmethod
from typing import Self


class AutoCloseable(ABC):
    @abstractmethod
    def __enter__(self) -> "Self": ...
    @abstractmethod
    def __exit__(self, exc_type, exc_value, traceback) -> None: ...


class AsyncAutoCloseable(ABC):
    @abstractmethod
    async def __aenter__(self) -> "Self": ...
    @abstractmethod
    async def __aexit__(self, exc_type, exc_value, traceback) -> None: ...
