"""LazyProxy 엣지케이스 테스트

LazyProxy의 극단적인 상황 테스트.
Component 간 의존성은 자동으로 LazyProxy가 주입됨.
manager.initialize() 호출 후에 안전하게 접근 가능.
"""

import pytest
import asyncio
from dataclasses import dataclass
from typing import ClassVar

from bloom.core import (
    Component,
    Configuration,
    Factory,
    get_container_manager,
    reset_container_manager,
)
from bloom.core.scope import ScopeEnum
from bloom.core.decorators import register_factories_from_configuration


# =============================================================================
# Mock Classes
# =============================================================================


@dataclass
class TrackedSingleton:
    """추적되는 싱글톤"""

    id: int


@dataclass
class SharedSingleton:
    """공유되는 싱글톤"""

    id: int


@dataclass
class Calculator:
    """계산기"""

    def add(self, a: int, b: int) -> int:
        return a + b

    def multiply(self, a: int, b: int) -> int:
        return a * b


@dataclass
class DataHolder:
    """데이터 홀더"""

    _value: str

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, v: str):
        self._value = v


# =============================================================================
# Tests
# =============================================================================


class TestLazyProxySingletonBehavior:
    """LazyProxy 싱글톤 동작 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_singleton_resolved_once(self):
        """싱글톤은 한 번만 resolve"""
        resolve_count = {"count": 0}

        @Configuration
        class SingleConfig:
            @Factory(scope=ScopeEnum.SINGLETON)
            def tracked_singleton(self) -> TrackedSingleton:
                resolve_count["count"] += 1
                return TrackedSingleton(id=resolve_count["count"])

        @Component
        class Consumer:
            singleton: TrackedSingleton

            def get_id(self) -> int:
                return self.singleton.id

        manager = get_container_manager()
        register_factories_from_configuration(SingleConfig, manager)
        resolve_count["count"] = 0
        await manager.initialize()  # 모든 SINGLETON 생성

        consumer = manager.get_instance(Consumer)

        # 여러 번 접근
        ids = [consumer.get_id() for _ in range(100)]

        # 모두 같은 인스턴스
        assert all(id == 1 for id in ids)
        assert resolve_count["count"] == 1

    @pytest.mark.asyncio
    async def test_multiple_components_share_singleton(self):
        """여러 컴포넌트가 싱글톤 공유"""

        @Configuration
        class SharedConfig:
            _id: ClassVar[int] = 0

            @Factory(scope=ScopeEnum.SINGLETON)
            def shared_singleton(self) -> SharedSingleton:
                SharedConfig._id += 1
                return SharedSingleton(id=SharedConfig._id)

        @Component
        class ConsumerA:
            singleton: SharedSingleton

            def get_id(self) -> int:
                return self.singleton.id

        @Component
        class ConsumerB:
            singleton: SharedSingleton

            def get_id(self) -> int:
                return self.singleton.id

        @Component
        class ConsumerC:
            singleton: SharedSingleton

            def get_id(self) -> int:
                return self.singleton.id

        manager = get_container_manager()
        register_factories_from_configuration(SharedConfig, manager)
        SharedConfig._id = 0
        await manager.initialize()

        a = manager.get_instance(ConsumerA)
        b = manager.get_instance(ConsumerB)
        c = manager.get_instance(ConsumerC)

        # 모두 같은 싱글톤 공유
        assert a.get_id() == b.get_id() == c.get_id() == 1


class TestLazyProxyCircularDependency:
    """LazyProxy 순환 의존성 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_circular_reference_resolution(self):
        """순환 참조 해결"""

        @Component
        class ServiceA:
            service_b: "ServiceB"

            def get_b_value(self) -> str:
                return self.service_b.value

            @property
            def value(self) -> str:
                return "A"

        @Component
        class ServiceB:
            service_a: ServiceA

            def get_a_value(self) -> str:
                return self.service_a.value

            @property
            def value(self) -> str:
                return "B"

        manager = get_container_manager()
        await manager.initialize()

        a = manager.get_instance(ServiceA)
        b = manager.get_instance(ServiceB)

        # 순환 참조 가능
        assert a.get_b_value() == "B"
        assert b.get_a_value() == "A"

    @pytest.mark.asyncio
    async def test_three_way_circular_dependency(self):
        """3자 순환 의존성"""

        @Component
        class ServiceX:
            y: "ServiceY"

            def get_y_value(self) -> str:
                return self.y.value

            @property
            def value(self) -> str:
                return "X"

        @Component
        class ServiceY:
            z: "ServiceZ"

            def get_z_value(self) -> str:
                return self.z.value

            @property
            def value(self) -> str:
                return "Y"

        @Component
        class ServiceZ:
            x: ServiceX

            def get_x_value(self) -> str:
                return self.x.value

            @property
            def value(self) -> str:
                return "Z"

        manager = get_container_manager()
        await manager.initialize()

        x = manager.get_instance(ServiceX)
        y = manager.get_instance(ServiceY)
        z = manager.get_instance(ServiceZ)

        # 3자 순환 참조
        assert x.get_y_value() == "Y"
        assert y.get_z_value() == "Z"
        assert z.get_x_value() == "X"


class TestLazyProxyMethodDelegation:
    """LazyProxy 메서드 위임 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_sync_method_delegation(self):
        """동기 메서드 위임"""

        @Configuration
        class MethodConfig:
            @Factory(scope=ScopeEnum.SINGLETON)
            def calculator(self) -> Calculator:
                return Calculator()

        @Component
        class MathService:
            calc: Calculator

            def compute(self, a: int, b: int) -> tuple[int, int]:
                return self.calc.add(a, b), self.calc.multiply(a, b)

        manager = get_container_manager()
        register_factories_from_configuration(MethodConfig, manager)
        await manager.initialize()

        svc = manager.get_instance(MathService)

        result = svc.compute(3, 4)
        assert result == (7, 12)

    @pytest.mark.asyncio
    async def test_property_delegation(self):
        """프로퍼티 위임"""

        @Configuration
        class PropConfig:
            @Factory(scope=ScopeEnum.SINGLETON)
            def data_holder(self) -> DataHolder:
                return DataHolder(_value="initial")

        @Component
        class DataConsumer:
            holder: DataHolder

            def get_value(self) -> str:
                return self.holder.value

            def set_value(self, v: str):
                self.holder.value = v

        manager = get_container_manager()
        register_factories_from_configuration(PropConfig, manager)
        await manager.initialize()

        consumer = manager.get_instance(DataConsumer)

        assert consumer.get_value() == "initial"
        consumer.set_value("updated")
        assert consumer.get_value() == "updated"


class TestLazyProxyChainResolution:
    """LazyProxy 체인 해결 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_deep_lazy_chain(self):
        """깊은 LazyProxy 체인"""

        @Component
        class Level1:
            @property
            def value(self) -> str:
                return "L1"

        @Component
        class Level2:
            l1: Level1

            @property
            def value(self) -> str:
                return f"{self.l1.value}->L2"

        @Component
        class Level3:
            l2: Level2

            @property
            def value(self) -> str:
                return f"{self.l2.value}->L3"

        @Component
        class Level4:
            l3: Level3

            @property
            def value(self) -> str:
                return f"{self.l3.value}->L4"

        @Component
        class Level5:
            l4: Level4

            @property
            def value(self) -> str:
                return f"{self.l4.value}->L5"

        manager = get_container_manager()
        await manager.initialize()

        l5 = manager.get_instance(Level5)

        assert l5.value == "L1->L2->L3->L4->L5"


class TestLazyProxyConcurrency:
    """LazyProxy 동시성 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_concurrent_first_access(self):
        """동시 첫 접근"""
        resolve_count = {"count": 0}

        @dataclass
        class ConcSingleton:
            id: int

        @Configuration
        class ConcConfig:
            @Factory(scope=ScopeEnum.SINGLETON)
            def concurrent_singleton(self) -> ConcSingleton:
                resolve_count["count"] += 1
                return ConcSingleton(id=resolve_count["count"])

        @Component
        class ConcConsumer:
            singleton: ConcSingleton

            async def get_id(self) -> int:
                await asyncio.sleep(0.001)
                return self.singleton.id

        manager = get_container_manager()
        register_factories_from_configuration(ConcConfig, manager)
        resolve_count["count"] = 0
        await manager.initialize()  # initialize에서 모든 SINGLETON 생성

        consumer = manager.get_instance(ConcConsumer)

        # 동시에 접근
        results = await asyncio.gather(*[consumer.get_id() for _ in range(50)])

        # 모두 같은 인스턴스 (싱글톤 보장)
        assert all(r == results[0] for r in results)


class TestLazyProxySpecialMethods:
    """LazyProxy 특수 메서드 테스트"""

    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        reset_container_manager()
        yield
        manager = get_container_manager()
        await manager.scope_manager.destroy_singletons()
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_callable_proxy(self):
        """호출 가능한 객체의 프록시"""

        class CallableObj:
            def __call__(self, x: int) -> int:
                return x * 2

        @Configuration
        class CallConfig:
            @Factory(scope=ScopeEnum.SINGLETON)
            def callable_obj(self) -> CallableObj:
                return CallableObj()

        @Component
        class CallConsumer:
            obj: CallableObj

            def call_it(self, x: int) -> int:
                return self.obj(x)

        manager = get_container_manager()
        register_factories_from_configuration(CallConfig, manager)
        await manager.initialize()

        consumer = manager.get_instance(CallConsumer)

        result = consumer.call_it(5)
        assert result == 10
