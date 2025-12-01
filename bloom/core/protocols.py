"""Bloom 프레임워크 공통 프로토콜

타입 안전한 직렬화/역직렬화를 위한 프로토콜을 정의합니다.
라이프사이클 관리를 위한 프로토콜도 정의합니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Coroutine, Protocol, Self, runtime_checkable


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


# =============================================================================
# Lifecycle Protocols - 라이프사이클 관리 프로토콜
# =============================================================================


class Initializable(ABC):
    def initialize(self) -> None:
        """동기 초기화 (의존성 주입 후 호출)"""
        pass

    async def initialize_async(self) -> Coroutine[Any, None, None]:
        """비동기 초기화"""
        ...


class Closeable(ABC):
    """
    리소스 정리 프로토콜 - @PreDestroy 대안

    이 프로토콜을 구현하면 DI 컨테이너가 인스턴스 소멸 시
    자동으로 close()를 호출합니다.

    PROTOTYPE 스코프에서는 메서드 종료 시 자동 호출됩니다.

    Example:
        ```python
        @Component
        @Scope(ScopeEnum.PROTOTYPE)
        class Session(Closeable):
            def close(self) -> None:
                self._connection.close()
        ```
    """

    @abstractmethod
    def close(self) -> None:
        """리소스 정리"""
        ...

    @abstractmethod
    def close_async(self) -> Coroutine[Any, None, None]:
        """비동기 리소스 정리"""
        ...


class AutoCloseable(Closeable, Initializable):
    """
    초기화 + 정리를 위한 추상 클래스

    Java의 AutoCloseable과 유사하게, 리소스의 전체 라이프사이클을 관리합니다.
    동기/비동기 모두 지원합니다.

    Example:
        ```python
        @Component
        @Scope(ScopeEnum.PROTOTYPE, mode=PrototypeMode.CALL_SCOPED)
        class Session(AutoCloseable):
            session_factory: SessionFactory

            def initialize(self) -> None:
                self._raw = self.session_factory.create_raw()

            def close(self) -> None:
                self._raw.close()

        # 비동기 예시
        @Component
        class AsyncDatabasePool(AutoCloseable):
            async def initialize_async(self) -> None:
                self._pool = await asyncpg.create_pool(...)

            async def close_async(self) -> None:
                await self._pool.close()
        ```
    """


class ContextManageable(AutoCloseable):
    """
    Python 컨텍스트 매니저 프로토콜

    with 문과 함께 사용 가능한 객체입니다.
    AutoCloseable을 상속하여 동기/비동기 컨텍스트 매니저를 모두 지원합니다.

    Example:
        ```python
        @Component
        class Transaction(ContextManageable):
            def initialize(self) -> None:
                self.begin()

            def close(self) -> None:
                self.commit()

        # 비동기 예시
        @Component
        class AsyncTransaction(ContextManageable):
            async def initialize_async(self) -> None:
                await self.begin()

            async def close_async(self) -> None:
                await self.commit()
        ```
    """

    def __enter__(self) -> Self:
        """동기 컨텍스트 진입"""
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """동기 컨텍스트 종료"""
        self.close()

    async def __aenter__(self) -> Self:
        """비동기 컨텍스트 진입"""
        await self.initialize_async()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """비동기 컨텍스트 종료"""
        await self.close_async()
