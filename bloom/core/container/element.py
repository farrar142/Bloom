"""Element 클래스"""

from typing import Any


class Element[T]:
    def __init__(self):
        self.metadata = dict[str, Any]()

    def __repr__(self) -> str:
        return f"Element(metadata={self.metadata})"


class OrderElement(Element):
    """
    Factory/Handler의 실행 순서를 지정하는 Element

    동일 타입을 반환하는 여러 Factory가 있을 때 실행 순서를 결정합니다.
    숫자가 낮을수록 먼저 실행됩니다.

    사용 예시:
        @Component
        class Config:
            @Factory
            def create(self) -> MyType:
                return MyType()

            @Factory
            @Order(1)
            def modify1(self, val: MyType) -> MyType:
                val.x += 1
                return val

            @Factory
            @Order(2)
            def modify2(self, val: MyType) -> MyType:
                val.x += 2
                return val
    """

    def __init__(self, order: int):
        super().__init__()
        self.metadata["order"] = order

    @property
    def order(self) -> int:
        return self.metadata.get("order", 0)


# =============================================================================
# Scope 시스템
# =============================================================================

from enum import Enum


class Scope(Enum):
    """컴포넌트 인스턴스의 생명주기 범위

    - SINGLETON: 애플리케이션 전체에서 단일 인스턴스 (기본값)
    - PROTOTYPE: 주입될 때마다 새 인스턴스 생성
    - REQUEST: HTTP 요청마다 새 인스턴스 (웹 컨텍스트에서만)
    """

    SINGLETON = "singleton"
    PROTOTYPE = "prototype"
    REQUEST = "request"


class PrototypeMode(Enum):
    """PROTOTYPE 스코프의 인스턴스 캐싱 모드

    - DEFAULT: 매번 새 인스턴스 생성 (Spring 동일)
    - CALL_SCOPED: 같은 핸들러 호출 내에서는 같은 인스턴스 반환
    """

    DEFAULT = "default"
    CALL_SCOPED = "call_scoped"


class ScopeElement(Element):
    """
    컴포넌트의 Scope를 지정하는 Element

    사용 예시:
        @Component
        @Scope(Scope.PROTOTYPE)
        class MyService:
            pass

        # 같은 핸들러 호출 내에서는 같은 인스턴스 반환
        @Component
        @Scope(Scope.PROTOTYPE, mode=PrototypeMode.CALL_SCOPED)
        class ScopedResource:
            pass
    """

    def __init__(self, scope: Scope, mode: PrototypeMode = PrototypeMode.DEFAULT):
        super().__init__()
        self.metadata["scope"] = scope
        self.metadata["prototype_mode"] = mode

    @property
    def scope(self) -> Scope:
        return self.metadata.get("scope", Scope.SINGLETON)

    @property
    def prototype_mode(self) -> PrototypeMode:
        """
        PROTOTYPE 스코프의 캐싱 모드

        - DEFAULT: 매번 새 인스턴스 생성
        - CALL_SCOPED: 같은 핸들러 호출 내에서 같은 인스턴스 반환
        """
        return self.metadata.get("prototype_mode", PrototypeMode.DEFAULT)
