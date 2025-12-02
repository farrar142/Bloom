"""Factory Chain 및 Builder Chain 테스트"""

import pytest

from bloom import Application
from bloom.core import Component, Factory, Order
from bloom.core.utils import AmbiguousProviderError


# ============================================================================
# 테스트용 타입
# ============================================================================


class Counter:
    """Factory Chain 테스트용 카운터"""

    def __init__(self, value: int = 0):
        self.value = value


class BuilderTarget:
    """Builder Chain 테스트용 대상"""

    val: int = 0


# ============================================================================
# Factory Chain 테스트
# ============================================================================


class TestFactoryChain:
    """Factory Chain 패턴 테스트 (Factory → Factory → Factory)"""

    async def test_factory_chain_with_order(self):
        """@Order로 순서 지정된 Factory Chain"""

        @Component
        class Config:
            @Factory
            def create_counter(self) -> Counter:
                """최초 생성 (Order 없음 = Creator)"""
                return Counter(0)

            @Factory
            @Order(1)
            def add_one(self, counter: Counter) -> Counter:
                """1 추가"""
                counter.value += 1
                return counter

            @Factory
            @Order(2)
            def add_two(self, counter: Counter) -> Counter:
                """2 추가 (마지막 = 최종값)"""
                counter.value += 2
                return counter

        app = Application("test_chain_order")
        await app.scan(Config).ready_async()

        # 최종값만 저장되어야 함
        counter = app.manager.get_instance(Counter)
        assert counter.value == 3  # 0 + 1 + 2

    async def test_factory_chain_auto_order_by_dependency(self):
        """의존성 그래프로 자동 순서 결정"""

        @Component
        class Config:
            @Factory
            def create_counter(self) -> Counter:
                """Creator: Counter 의존성 없음"""
                return Counter(10)

            @Factory
            def modify_counter(self, counter: Counter) -> Counter:
                """Modifier: Counter 의존성 있음"""
                counter.value += 5
                return counter

        app = Application("test_chain_auto")
        await app.scan(Config).ready_async()

        counter = app.manager.get_instance(Counter)
        assert counter.value == 15  # 10 + 5

    async def test_factory_chain_mixed_order(self):
        """@Order와 의존성 기반 혼합"""

        @Component
        class Config:
            @Factory
            def create(self) -> Counter:
                """Creator (Order 없음, 의존성 없음 → 먼저)"""
                return Counter(0)

            @Factory
            @Order(10)
            def step_ten(self, c: Counter) -> Counter:
                """Order 10"""
                c.value += 10
                return c

            @Factory
            @Order(5)
            def step_five(self, c: Counter) -> Counter:
                """Order 5 (Order 10보다 먼저)"""
                c.value += 5
                return c

        app = Application("test_chain_mixed")
        await app.scan(Config).ready_async()

        counter = app.manager.get_instance(Counter)
        # 순서: create(0) → step_five(+5) → step_ten(+10)
        assert counter.value == 15


# ============================================================================
# Builder Chain 테스트
# ============================================================================


class TestBuilderChain:
    """Builder Chain 패턴 테스트 (Component → Factory → Factory)"""

    async def test_builder_chain_with_component(self):
        """Component를 Factory가 수정"""

        @Component
        class Target:
            val: int = 0

        @Component
        class Config:
            @Factory
            @Order(1)
            def enhance1(self, target: Target) -> Target:
                target.val += 1
                return target

            @Factory
            @Order(2)
            def enhance2(self, target: Target) -> Target:
                target.val += 2
                return target

        app = Application("test_builder")
        await app.scan(Target, Config).ready_async()

        target = app.manager.get_instance(Target)
        assert target.val == 3  # 0 + 1 + 2


# ============================================================================
# Ambiguous Provider 에러 테스트
# ============================================================================


class TestAmbiguousProvider:
    """Ambiguous Provider Anti-pattern 감지 테스트"""

    async def test_ambiguous_provider_error(self):
        """동일 타입 Creator가 2개 이상이고 Modifier가 있으면 에러"""

        class Value:
            val: int = 0

        @Component
        class BadConfig:
            @Factory
            def create1(self) -> Value:
                """Creator 1"""
                return Value()

            @Factory
            def create2(self) -> Value:
                """Creator 2 (충돌!)"""
                v = Value()
                v.val = 100
                return v

            @Factory
            def modify(self, value: Value) -> Value:
                """Modifier - 어떤 Creator의 결과를 받아야 하는지 모호"""
                value.val += 1
                return value

        app = Application("test_ambiguous")
        app.scan(BadConfig)

        with pytest.raises(AmbiguousProviderError) as exc_info:
            await app.ready_async()

        # 에러 메시지에 충돌 Factory 목록 포함
        error_msg = str(exc_info.value)
        assert "create1" in error_msg or "create2" in error_msg
        assert "Value" in error_msg

    async def test_multiple_creators_without_modifier_is_ok(self):
        """Modifier가 없으면 여러 Creator도 허용 - get_instances로 모두 조회 가능"""

        class Service:
            name: str = ""

        @Component
        class Config:
            @Factory
            def create_a(self) -> Service:
                s = Service()
                s.name = "A"
                return s

            @Factory
            def create_b(self) -> Service:
                s = Service()
                s.name = "B"
                return s

        app = Application("test_multi_creator")
        await app.scan(Config).ready_async()

        # 둘 다 등록됨 - get_instances로 모두 조회
        services = app.manager.get_instances(Service)
        assert len(services) == 2
        names = {s.name for s in services}
        assert names == {"A", "B"}


# ============================================================================
# 엣지 케이스 테스트
# ============================================================================


class TestEdgeCases:
    """엣지 케이스 테스트"""

    async def test_single_factory_no_chain(self):
        """Factory가 하나뿐이면 체인 아님"""

        @Component
        class Config:
            @Factory
            def create(self) -> Counter:
                return Counter(42)

        app = Application("test_single")
        await app.scan(Config).ready_async()

        counter = app.manager.get_instance(Counter)
        assert counter.value == 42

    async def test_chain_with_different_types(self):
        """다른 타입을 반환하는 Factory들은 체인이 아님"""

        class TypeA:
            val: int = 1

        class TypeB:
            val: int = 2

        @Component
        class Config:
            @Factory
            def create_a(self) -> TypeA:
                return TypeA()

            @Factory
            def create_b(self, a: TypeA) -> TypeB:
                b = TypeB()
                b.val = a.val + 10
                return b

        app = Application("test_diff_types")
        await app.scan(Config).ready_async()

        a = app.manager.get_instance(TypeA)
        b = app.manager.get_instance(TypeB)
        assert a.val == 1
        assert b.val == 11

    async def test_order_zero(self):
        """Order(0)도 유효"""

        @Component
        class Config:
            @Factory
            @Order(0)
            def create(self) -> Counter:
                return Counter(0)

            @Factory
            @Order(1)
            def modify(self, c: Counter) -> Counter:
                c.value += 1
                return c

        app = Application("test_order_zero")
        await app.scan(Config).ready_async()

        counter = app.manager.get_instance(Counter)
        assert counter.value == 1

    async def test_negative_order(self):
        """음수 Order도 유효"""

        @Component
        class Config:
            @Factory
            @Order(-100)
            def first(self) -> Counter:
                return Counter(100)

            @Factory
            @Order(0)
            def second(self, c: Counter) -> Counter:
                c.value += 1
                return c

        app = Application("test_negative_order")
        await app.scan(Config).ready_async()

        counter = app.manager.get_instance(Counter)
        assert counter.value == 101


# ============================================================================
# 다이아몬드형 의존성 테스트
# ============================================================================


class TestDiamondFactoryChain:
    """다이아몬드형 의존성 구조 테스트
    
    Case 1: A → A2, A → B → A3 (같은 타입의 분기)
           A
          / \
        A2   B
          \ /
          A3
          
    Case 2: A → A2, A → B → B2 (다른 타입으로 분기)
           A
          / \
        A2   B
             |
            B2
    """

    async def test_diamond_same_type_converging(self):
        """
        같은 타입으로 수렴하는 다이아몬드 패턴

        Counter(0) -Order(1)-> +1 -Order(3)-> +10 = 11
                  \-Order(2)-> *2 -/

        실제로는 순차적으로 실행: 0 → +1 → *2 → +10 = 12
        """

        @Component
        class DiamondConfig:
            @Factory
            def create(self) -> Counter:
                """초기값 0"""
                return Counter(0)

            @Factory
            @Order(1)
            def add_one(self, c: Counter) -> Counter:
                """1 추가"""
                c.value += 1
                return c

            @Factory
            @Order(2)
            def multiply_two(self, c: Counter) -> Counter:
                """2 곱하기"""
                c.value *= 2
                return c

            @Factory
            @Order(3)
            def add_ten(self, c: Counter) -> Counter:
                """10 추가 (최종)"""
                c.value += 10
                return c

        app = Application("test_diamond_converge")
        await app.scan(DiamondConfig).ready_async()

        counter = app.manager.get_instance(Counter)
        # 순서: create(0) → add_one(+1=1) → multiply_two(*2=2) → add_ten(+10=12)
        assert counter.value == 12

    async def test_diamond_different_types_branch(self):
        """
        다른 타입으로 분기하는 다이아몬드 패턴

        Counter(0) ─────────────────→ +1 = Counter(1)
              └──→ create Multiplier(counter.value * 2) = Multiplier(0)
                            └──→ enhance Multiplier(*3) = Multiplier(0)
        """

        class Multiplier:
            def __init__(self, factor: int = 1):
                self.factor = factor

        @Component
        class DiamondConfig:
            @Factory
            def create_counter(self) -> Counter:
                """Counter 생성"""
                return Counter(5)

            @Factory
            @Order(1)
            def modify_counter(self, c: Counter) -> Counter:
                """Counter 수정"""
                c.value += 10
                return c

            @Factory
            def create_multiplier(self, c: Counter) -> Multiplier:
                """Counter 값을 기반으로 Multiplier 생성"""
                return Multiplier(c.value * 2)

            @Factory
            @Order(1)
            def enhance_multiplier(self, m: Multiplier) -> Multiplier:
                """Multiplier 강화"""
                m.factor *= 3
                return m

        app = Application("test_diamond_branch")
        await app.scan(DiamondConfig).ready_async()

        counter = app.manager.get_instance(Counter)
        multiplier = app.manager.get_instance(Multiplier)

        # Counter: 5 → +10 = 15
        assert counter.value == 15
        # Multiplier: 15 * 2 = 30 → *3 = 90
        assert multiplier.factor == 90

    async def test_diamond_with_intermediate_type(self):
        """
        중간 타입을 거치는 다이아몬드 패턴

        Counter(0) → Transformer → Counter(*2) = Counter(0)
              └────→ +5 = Counter(5) (먼저 실행)

        실행 순서:
        1. create() → Counter(0)
        2. add_five(Counter) → Counter(5)  (Order 1)
        3. create_transformer(Counter) → Transformer(5)
        4. transform(Transformer, Counter) → Counter(10) (Order 2)
        """

        class Transformer:
            def __init__(self, base_value: int):
                self.base_value = base_value

            def apply(self, counter: Counter) -> Counter:
                counter.value = self.base_value * 2
                return counter

        @Component
        class ComplexConfig:
            @Factory
            def create(self) -> Counter:
                return Counter(0)

            @Factory
            @Order(1)
            def add_five(self, c: Counter) -> Counter:
                c.value += 5
                return c

            @Factory
            def create_transformer(self, c: Counter) -> Transformer:
                # Counter(5)를 받아서 Transformer 생성
                return Transformer(c.value)

            @Factory
            @Order(2)
            def transform(self, t: Transformer, c: Counter) -> Counter:
                # Transformer로 Counter 변환
                return t.apply(c)

        app = Application("test_intermediate")
        await app.scan(ComplexConfig).ready_async()

        counter = app.manager.get_instance(Counter)
        transformer = app.manager.get_instance(Transformer)

        # Transformer: base_value = 5 (Counter 수정 후 값)
        assert transformer.base_value == 5
        # Counter: 5 * 2 = 10 (transform에서 변환)
        assert counter.value == 10

    async def test_long_chain_with_multiple_branches(self):
        """
        긴 체인에서 여러 분기 테스트

        Counter(1) → *2 → +3 → *4 → +5 = ((1*2)+3)*4+5 = 25
        """

        @Component
        class LongChainConfig:
            @Factory
            def step0(self) -> Counter:
                return Counter(1)

            @Factory
            @Order(1)
            def step1(self, c: Counter) -> Counter:
                c.value *= 2  # 1 * 2 = 2
                return c

            @Factory
            @Order(2)
            def step2(self, c: Counter) -> Counter:
                c.value += 3  # 2 + 3 = 5
                return c

            @Factory
            @Order(3)
            def step3(self, c: Counter) -> Counter:
                c.value *= 4  # 5 * 4 = 20
                return c

            @Factory
            @Order(4)
            def step4(self, c: Counter) -> Counter:
                c.value += 5  # 20 + 5 = 25
                return c

        app = Application("test_long_chain")
        await app.scan(LongChainConfig).ready_async()

        counter = app.manager.get_instance(Counter)
        assert counter.value == 25

    async def test_parallel_independent_chains(self):
        """
        독립적인 병렬 체인 테스트

        Counter(10) → +5 = 15
        Multiplier(2) → *3 = 6

        서로 독립적으로 동작
        """

        class Multiplier:
            def __init__(self, factor: int = 1):
                self.factor = factor

        @Component
        class ParallelConfig:
            @Factory
            def create_counter(self) -> Counter:
                return Counter(10)

            @Factory
            @Order(1)
            def modify_counter(self, c: Counter) -> Counter:
                c.value += 5
                return c

            @Factory
            def create_multiplier(self) -> Multiplier:
                return Multiplier(2)

            @Factory
            @Order(1)
            def modify_multiplier(self, m: Multiplier) -> Multiplier:
                m.factor *= 3
                return m

        app = Application("test_parallel")
        await app.scan(ParallelConfig).ready_async()

        counter = app.manager.get_instance(Counter)
        multiplier = app.manager.get_instance(Multiplier)

        assert counter.value == 15
        assert multiplier.factor == 6
