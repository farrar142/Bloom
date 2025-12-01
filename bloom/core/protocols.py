"""Bloom 프레임워크 공통 프로토콜

타입 안전한 직렬화/역직렬화를 위한 프로토콜을 정의합니다.
라이프사이클 관리를 위한 프로토콜도 정의합니다.
"""

from __future__ import annotations

from typing import Any, Protocol, Self, runtime_checkable


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


@runtime_checkable
class Initializable(Protocol):
    """
    초기화 프로토콜 - @PostConstruct 대안

    이 프로토콜을 구현하면 DI 컨테이너가 인스턴스 생성 후
    자동으로 initialize()를 호출합니다.

    Example:
        ```python
        @Component
        class DatabaseConnection(Initializable):
            config: Config

            def initialize(self) -> None:
                self.connection = create_connection(self.config.url)
        ```
    """

    def initialize(self) -> None:
        """인스턴스 초기화 (의존성 주입 후 호출)"""
        ...


@runtime_checkable
class Closeable(Protocol):
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

    def close(self) -> None:
        """리소스 정리"""
        ...


@runtime_checkable
class AutoCloseable(Initializable, Closeable, Protocol):
    """
    초기화 + 정리 프로토콜 조합

    Java의 AutoCloseable과 유사하게, 리소스의 전체 라이프사이클을 관리합니다.

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
        ```
    """

    pass


@runtime_checkable
class ContextManageable(Protocol):
    """
    Python 컨텍스트 매니저 프로토콜

    with 문과 함께 사용 가능한 객체입니다.
    DI 컨테이너는 __exit__를 PreDestroy로 사용할 수 있습니다.

    Example:
        ```python
        @Component
        class Transaction(ContextManageable):
            def __enter__(self) -> "Transaction":
                self.begin()
                return self

            def __exit__(self, *args) -> None:
                if args[0]:  # 예외 발생
                    self.rollback()
                else:
                    self.commit()
        ```
    """

    def __enter__(self) -> Self:
        """컨텍스트 진입"""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """컨텍스트 종료"""
        ...
