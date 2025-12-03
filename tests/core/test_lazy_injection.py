"""@Component의 LazyProxy를 통한 순환 의존성 자동 해결 테스트"""

import pytest

from bloom.core import (
    Component,
    Scope,
    get_container_manager,
    reset_container_manager,
    LazyProxy,
)


class TestLazyCircularDependency:
    """
    @Component의 LazyProxy를 통한 순환 의존성 해결 테스트.

    Factory 없이 @Component만으로도 순환 의존성이 해결되어야 함.
    LazyProxy 덕분에 실제 접근 시점까지 resolve가 지연됨.
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전 manager 리셋"""
        reset_container_manager()
        yield
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_two_way_circular_with_lazy_proxy(self):
        """
        2자 순환 의존성을 LazyProxy로 해결.

        ServiceA <-> ServiceB 상호 참조
        """

        @Component
        class ServiceA:
            b: "ServiceB"
            name: str = "A"

            def get_b_name(self) -> str:
                return self.b.name

        @Component
        class ServiceB:
            a: "ServiceA"
            name: str = "B"

            def get_a_name(self) -> str:
                return self.a.name

        manager = get_container_manager()

        # initialize()로 모든 SINGLETON 인스턴스 생성
        # LazyProxy 덕분에 순환 의존성이 문제되지 않음
        await manager.initialize()

        a = manager.get_instance(ServiceA)
        b = manager.get_instance(ServiceB)

        # LazyProxy를 통한 상호 참조 작동
        assert a.get_b_name() == "B"
        assert b.get_a_name() == "A"

        # 실제 인스턴스 확인 (LazyProxy가 resolve됨)
        assert a.b.name == "B"
        assert b.a.name == "A"

    @pytest.mark.asyncio
    async def test_three_way_circular_with_lazy_proxy(self):
        """
        3자 순환 의존성을 LazyProxy로 해결.

        A -> B -> C -> A
        """

        @Component
        class CircularA:
            c: "CircularC"
            name: str = "A"

        @Component
        class CircularB:
            a: "CircularA"
            name: str = "B"

        @Component
        class CircularC:
            b: "CircularB"
            name: str = "C"

        manager = get_container_manager()
        await manager.initialize()

        a = manager.get_instance(CircularA)
        b = manager.get_instance(CircularB)
        c = manager.get_instance(CircularC)

        # 순환 체인 검증
        assert b.a.name == "A"
        assert c.b.name == "B"
        assert a.c.name == "C"

        # 전체 순환 탐색 (LazyProxy가 투명하게 동작)
        assert a.c.b.a.name == "A"
        assert b.a.c.b.name == "B"
        assert c.b.a.c.name == "C"

    @pytest.mark.asyncio
    async def test_lazy_proxy_is_transparent(self):
        """
        LazyProxy가 투명하게 동작하는지 확인.
        메서드 호출, 속성 접근 등이 정상 작동.
        """

        @Component
        class TransparentA:
            b: "TransparentB"
            value: int = 100

            def multiply(self, x: int) -> int:
                return self.value * x

            def get_b_value(self) -> int:
                return self.b.value

        @Component
        class TransparentB:
            a: "TransparentA"
            value: int = 200

            def add(self, x: int) -> int:
                return self.value + x

            def get_a_multiplied(self, x: int) -> int:
                return self.a.multiply(x)

        manager = get_container_manager()
        await manager.initialize()

        a = manager.get_instance(TransparentA)
        b = manager.get_instance(TransparentB)

        # 직접 메서드 호출
        assert a.multiply(3) == 300
        assert b.add(50) == 250

        # LazyProxy를 통한 메서드 호출
        assert a.get_b_value() == 200
        assert b.get_a_multiplied(5) == 500

    @pytest.mark.asyncio
    async def test_lazy_proxy_same_instance(self):
        """
        LazyProxy가 SINGLETON 스코프에서 동일 인스턴스를 반환하는지.
        """

        @Component
        class SingletonA:
            b: "SingletonB"

        @Component
        class SingletonB:
            a: "SingletonA"

        manager = get_container_manager()
        await manager.initialize()

        a1 = manager.get_instance(SingletonA)
        a2 = manager.get_instance(SingletonA)
        b1 = manager.get_instance(SingletonB)
        b2 = manager.get_instance(SingletonB)

        # 동일 인스턴스
        assert a1 is a2
        assert b1 is b2

        # LazyProxy를 통해 얻은 인스턴스도 동일
        assert a1.b is b1 or a1.b._lp_resolve() is b1  # LazyProxy 또는 실제 인스턴스
        assert b1.a is a1 or b1.a._lp_resolve() is a1

    @pytest.mark.asyncio
    async def test_lazy_proxy_repr(self):
        """LazyProxy의 repr이 올바르게 표시되는지."""

        @Component
        class ReprServiceA:
            b: "ReprServiceB"

        @Component
        class ReprServiceB:
            a: "ReprServiceA"

        manager = get_container_manager()
        await manager.initialize()

        service_a = manager.get_instance(ReprServiceA)

        # service_a.b는 LazyProxy일 수 있음
        b_ref = service_a.b
        if isinstance(b_ref, LazyProxy):
            repr_str = repr(b_ref)
            assert "LazyProxy" in repr_str
            assert "ReprServiceB" in repr_str

    @pytest.mark.asyncio
    async def test_deep_circular_chain(self):
        """
        깊은 순환 체인 테스트 (5개 컴포넌트).
        """

        @Component
        class ChainA:
            e: "ChainE"
            name: str = "A"

        @Component
        class ChainB:
            a: "ChainA"
            name: str = "B"

        @Component
        class ChainC:
            b: "ChainB"
            name: str = "C"

        @Component
        class ChainD:
            c: "ChainC"
            name: str = "D"

        @Component
        class ChainE:
            d: "ChainD"
            name: str = "E"

        manager = get_container_manager()
        await manager.initialize()

        a = manager.get_instance(ChainA)

        # 전체 순환 탐색
        assert a.e.d.c.b.a.name == "A"
        assert a.e.d.c.b.a.e.name == "E"

    @pytest.mark.asyncio
    async def test_mixed_lazy_and_direct_fields(self):
        """
        LazyProxy 필드와 일반 필드가 혼합된 경우.
        """

        @Component
        class MixedA:
            b: "MixedB"
            value: int = 42
            name: str = "MixedA"

        @Component
        class MixedB:
            a: "MixedA"
            items: list[str] = None  # 일반 필드 (None 기본값)

            def __init__(self):
                self.items = ["x", "y", "z"]

        manager = get_container_manager()
        await manager.initialize()

        a = manager.get_instance(MixedA)
        b = manager.get_instance(MixedB)

        # 일반 필드
        assert a.value == 42
        assert a.name == "MixedA"
        assert b.items == ["x", "y", "z"]

        # LazyProxy 필드
        assert a.b.items == ["x", "y", "z"]
        assert b.a.value == 42
