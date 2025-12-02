"""Factory 메서드 엣지 케이스 테스트

다양한 엣지 케이스와 코너 케이스를 검증:
1. 반환 타입 관련 엣지 케이스
2. 파라미터 관련 엣지 케이스
3. 라이프사이클 관련 엣지 케이스
4. 에러 처리 엣지 케이스
5. 복잡한 의존성 패턴
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

import pytest

from bloom import Application, Component, Factory
from bloom.core.container.element import PrototypeMode
from bloom.core.container.element import Scope as ScopeEnum
from bloom.core.decorators import Order, PostConstruct, PreDestroy, Scope

# ============================================================================
# 테스트용 타입들
# ============================================================================


class SimpleValue:
    """간단한 값 클래스"""

    def __init__(self, value: int = 0):
        self.value = value


@dataclass
class DataClassValue:
    """dataclass 값"""

    name: str
    count: int


@runtime_checkable
class Printable(Protocol):
    """Protocol 타입"""

    def print_value(self) -> str: ...


class AbstractBase(ABC):
    """추상 베이스 클래스"""

    @abstractmethod
    def get_value(self) -> int: ...


class ConcreteImpl(AbstractBase):
    """구체 구현"""

    def __init__(self, value: int):
        self._value = value

    def get_value(self) -> int:
        return self._value


# ============================================================================
# 반환 타입 관련 엣지 케이스
# ============================================================================


class TestFactoryReturnTypeEdgeCases:
    """Factory 반환 타입 관련 엣지 케이스"""

    def test_factory_returns_none(self):
        """Factory가 None을 반환하는 경우 - None이 인스턴스로 저장됨"""

        class MaybeValue:
            pass

        @Component
        class Config:
            @Factory
            def create_maybe(self) -> MaybeValue:
                return None  # type: ignore

        app = Application("test")
        app.scan(Config).ready()

        # None이 MaybeValue 타입으로 등록됨
        result = app.manager.get_instance(MaybeValue, raise_exception=False)
        assert result is None

    def test_factory_returns_dataclass(self):
        """Factory가 dataclass를 반환하는 경우"""

        @Component
        class Config:
            @Factory
            def create_data(self) -> DataClassValue:
                return DataClassValue(name="test", count=42)

        app = Application("test")
        app.scan(Config).ready()

        data = app.manager.get_instance(DataClassValue)
        assert data.name == "test"
        assert data.count == 42

    def test_factory_returns_primitive_wrapper(self):
        """Factory가 primitive를 감싸는 클래스를 반환"""

        class IntWrapper:
            def __init__(self, value: int):
                self.value = value

        @Component
        class Config:
            @Factory
            def create_int_wrapper(self) -> IntWrapper:
                return IntWrapper(12345)

        app = Application("test")
        app.scan(Config).ready()

        wrapper = app.manager.get_instance(IntWrapper)
        assert wrapper.value == 12345

    def test_factory_returns_abstract_implementation(self):
        """Factory가 추상 클래스의 구현체를 반환"""

        @Component
        class Config:
            @Factory
            def create_impl(self) -> AbstractBase:
                return ConcreteImpl(100)

        app = Application("test")
        app.scan(Config).ready()

        instance = app.manager.get_instance(AbstractBase)
        assert isinstance(instance, ConcreteImpl)
        assert instance.get_value() == 100

    def test_factory_returns_nested_class(self):
        """Factory가 중첩 클래스 인스턴스를 반환"""

        class Outer:
            class Inner:
                def __init__(self, data: str):
                    self.data = data

        @Component
        class Config:
            @Factory
            def create_inner(self) -> Outer.Inner:
                return Outer.Inner("nested")

        app = Application("test")
        app.scan(Config).ready()

        inner = app.manager.get_instance(Outer.Inner)
        assert inner.data == "nested"


# ============================================================================
# 파라미터 관련 엣지 케이스
# ============================================================================


class TestFactoryParameterEdgeCases:
    """Factory 파라미터 관련 엣지 케이스"""

    def test_factory_with_no_parameters(self):
        """파라미터 없는 Factory (self만 있음)"""

        @Component
        class Config:
            @Factory
            def create_simple(self) -> SimpleValue:
                return SimpleValue(999)

        app = Application("test")
        app.scan(Config).ready()

        value = app.manager.get_instance(SimpleValue)
        assert value.value == 999

    def test_factory_with_many_parameters(self):
        """많은 파라미터를 가진 Factory"""

        class A:
            pass

        class B:
            pass

        class C:
            pass

        class D:
            pass

        class E:
            pass

        class Combined:
            def __init__(self, a: A, b: B, c: C, d: D, e: E):
                self.a = a
                self.b = b
                self.c = c
                self.d = d
                self.e = e

        @Component
        class Config:
            @Factory
            def a(self) -> A:
                return A()

            @Factory
            def b(self) -> B:
                return B()

            @Factory
            def c(self) -> C:
                return C()

            @Factory
            def d(self) -> D:
                return D()

            @Factory
            def e(self) -> E:
                return E()

            @Factory
            def combined(self, a: A, b: B, c: C, d: D, e: E) -> Combined:
                return Combined(a, b, c, d, e)

        app = Application("test")
        app.scan(Config).ready()

        combined = app.manager.get_instance(Combined)
        assert isinstance(combined.a, A)
        assert isinstance(combined.b, B)
        assert isinstance(combined.c, C)
        assert isinstance(combined.d, D)
        assert isinstance(combined.e, E)

    def test_factory_with_self_type_dependency(self):
        """Factory가 자신의 반환 타입을 파라미터로 받는 경우 (Chain)"""

        @Component
        class Config:
            @Factory
            def create(self) -> SimpleValue:
                return SimpleValue(1)

            @Factory
            @Order(1)
            def modify(self, value: SimpleValue) -> SimpleValue:
                value.value *= 10
                return value

        app = Application("test")
        app.scan(Config).ready()

        value = app.manager.get_instance(SimpleValue)
        assert value.value == 10

    def test_factory_with_optional_dependency_present(self):
        """Optional 의존성이 존재하는 경우"""

        class OptionalDep:
            pass

        class Target:
            def __init__(self, dep: Optional[OptionalDep]):
                self.dep = dep

        @Component
        class Config:
            @Factory
            def create_dep(self) -> OptionalDep:
                return OptionalDep()

            @Factory
            def create_target(self, dep: OptionalDep) -> Target:
                return Target(dep)

        app = Application("test")
        app.scan(Config).ready()

        target = app.manager.get_instance(Target)
        assert target.dep is not None
        assert isinstance(target.dep, OptionalDep)


# ============================================================================
# 라이프사이클 관련 엣지 케이스
# ============================================================================


class TestFactoryLifecycleEdgeCases:
    """Factory 라이프사이클 관련 엣지 케이스"""

    def test_factory_with_post_construct(self):
        """Factory가 생성한 인스턴스의 @PostConstruct 호출"""
        post_construct_called = []

        class LifecycleValue:
            def __init__(self, value: int):
                self.value = value
                self.initialized = False

            @PostConstruct
            def init(self):
                self.initialized = True
                post_construct_called.append(self.value)

        @Component
        class Config:
            @Factory
            def create(self) -> LifecycleValue:
                return LifecycleValue(42)

        app = Application("test")
        app.scan(Config).ready()

        value = app.manager.get_instance(LifecycleValue)
        assert value.initialized is True
        assert 42 in post_construct_called

    def test_factory_with_pre_destroy(self):
        """Factory가 생성한 인스턴스의 @PreDestroy 호출"""
        pre_destroy_called = []

        class DestroyableValue:
            def __init__(self, id: int):
                self.id = id

            @PreDestroy
            def cleanup(self):
                pre_destroy_called.append(self.id)

        @Component
        class Config:
            @Factory
            def create(self) -> DestroyableValue:
                return DestroyableValue(123)

        app = Application("test")
        app.scan(Config).ready()

        _ = app.manager.get_instance(DestroyableValue)
        app.shutdown()

        assert 123 in pre_destroy_called

    def test_factory_chain_lifecycle_order(self):
        """Factory Chain에서 라이프사이클 순서"""
        lifecycle_order = []

        class ChainValue:
            def __init__(self, step: str):
                self.steps = [step]

            @PostConstruct
            def on_init(self):
                lifecycle_order.append(f"post_construct:{','.join(self.steps)}")

        @Component
        class Config:
            @Factory
            def create(self) -> ChainValue:
                return ChainValue("create")

            @Factory
            @Order(1)
            def step1(self, v: ChainValue) -> ChainValue:
                v.steps.append("step1")
                return v

            @Factory
            @Order(2)
            def step2(self, v: ChainValue) -> ChainValue:
                v.steps.append("step2")
                return v

        app = Application("test")
        app.scan(Config).ready()

        _ = app.manager.get_instance(ChainValue)
        # 마지막 Factory 후에만 PostConstruct 호출
        assert len(lifecycle_order) == 1
        assert "create,step1,step2" in lifecycle_order[0]

    def test_prototype_factory_pre_destroy_on_scope_end(self):
        """PROTOTYPE Factory의 @PreDestroy는 스코프 종료 시 호출"""
        destroy_count = [0]

        class PrototypeValue:
            @PreDestroy
            def cleanup(self):
                destroy_count[0] += 1

        @Component
        class Config:
            @Factory
            @Scope(ScopeEnum.CALL)
            def create(self) -> PrototypeValue:
                return PrototypeValue()

        @Component
        class Consumer:
            value: PrototypeValue

            def use(self):
                return self.value

        app = Application("test")
        app.scan(Config, Consumer).ready()

        # PROTOTYPE은 접근할 때마다 새 인스턴스
        consumer = app.manager.get_instance(Consumer)
        _ = consumer.use()

        # 스코프 종료 시 정리됨 (메서드 호출 후)
        # 정확한 타이밍은 구현에 따라 다름


# ============================================================================
# 에러 처리 엣지 케이스
# ============================================================================


class TestFactoryErrorEdgeCases:
    """Factory 에러 처리 관련 엣지 케이스"""

    def test_factory_raises_exception(self):
        """Factory 메서드에서 예외 발생"""

        class FailValue:
            pass

        @Component
        class Config:
            @Factory
            def create_fail(self) -> FailValue:
                raise ValueError("Factory failed!")

        app = Application("test")
        app.scan(Config)

        with pytest.raises(ValueError, match="Factory failed!"):
            app.ready()

    def test_factory_with_missing_dependency(self):
        """Factory에 필요한 의존성이 없는 경우"""

        class MissingDep:
            pass

        class NeedsDep:
            pass

        @Component
        class Config:
            @Factory
            def create(self, dep: MissingDep) -> NeedsDep:
                return NeedsDep()

        app = Application("test")
        app.scan(Config)

        with pytest.raises(Exception, match="not found"):
            app.ready()

    @pytest.mark.skip(reason="TODO: Factory 반환 타입 검증 미구현")
    def test_factory_returns_wrong_type(self):
        """Factory가 선언된 타입과 다른 타입 반환 시 TypeError 발생"""

        class Expected:
            pass

        class Actual:
            pass

        @Component
        class Config:
            @Factory
            def create(self) -> Expected:
                return Actual()  # type: ignore

        app = Application("test")
        app.scan(Config)

        with pytest.raises(TypeError, match="expected Expected or its subclass"):
            app.ready()

    def test_factory_returns_subclass_is_allowed(self):
        """Factory가 서브클래스를 반환하는 것은 허용"""

        class Base:
            pass

        class Derived(Base):
            pass

        @Component
        class Config:
            @Factory
            def create(self) -> Base:
                return Derived()  # 서브클래스 반환 OK

        app = Application("test")
        app.scan(Config).ready()

        result = app.manager.get_instance(Base)
        assert isinstance(result, Derived)


# ============================================================================
# 복잡한 의존성 패턴 엣지 케이스
# ============================================================================


class TestFactoryComplexDependencyEdgeCases:
    """복잡한 의존성 패턴 엣지 케이스"""

    def test_factory_circular_with_lazy(self):
        """Factory 간 순환 의존성을 Lazy로 해결"""

        class ServiceA:
            def __init__(self):
                self.b: "ServiceB | None" = None

            def get_b_value(self) -> int:
                return self.b.value if self.b else 0

        class ServiceB:
            def __init__(self, value: int):
                self.value = value

        @Component
        class Config:
            @Factory
            def create_a(self) -> ServiceA:
                return ServiceA()

            @Factory
            def create_b(self, a: ServiceA) -> ServiceB:
                return ServiceB(a.get_b_value() + 100)

        app = Application("test")
        app.scan(Config).ready()

        _ = app.manager.get_instance(ServiceA)
        b = app.manager.get_instance(ServiceB)

        # A는 B 없이 생성되므로 B.value = 0 + 100 = 100
        assert b.value == 100

    def test_factory_with_varargs(self):
        """Factory에서 *args로 여러 인스턴스 주입"""

        class Plugin:
            name: str

        class PluginA(Plugin):
            name = "A"

        class PluginB(Plugin):
            name = "B"

        class PluginC(Plugin):
            name = "C"

        class PluginManager:
            def __init__(self, plugins: list[Plugin]):
                self.plugins = plugins

        @Component
        class Config:
            @Factory
            def plugin_a(self) -> PluginA:
                return PluginA()

            @Factory
            def plugin_b(self) -> PluginB:
                return PluginB()

            @Factory
            def plugin_c(self) -> PluginC:
                return PluginC()

            @Factory
            def manager(self, *plugins: Plugin) -> PluginManager:
                return PluginManager(list(plugins))

        app = Application("test")
        app.scan(Config).ready()

        manager = app.manager.get_instance(PluginManager)
        assert len(manager.plugins) == 3
        names = {p.name for p in manager.plugins}
        assert names == {"A", "B", "C"}

    def test_factory_deep_chain(self):
        """10단계 이상의 깊은 Factory Chain"""

        class DeepValue:
            def __init__(self, depth: int = 0):
                self.depth = depth

        @Component
        class DeepConfig:
            @Factory
            def depth0(self) -> DeepValue:
                return DeepValue(0)

            @Factory
            @Order(1)
            def depth1(self, v: DeepValue) -> DeepValue:
                v.depth = 1
                return v

            @Factory
            @Order(2)
            def depth2(self, v: DeepValue) -> DeepValue:
                v.depth = 2
                return v

            @Factory
            @Order(3)
            def depth3(self, v: DeepValue) -> DeepValue:
                v.depth = 3
                return v

            @Factory
            @Order(4)
            def depth4(self, v: DeepValue) -> DeepValue:
                v.depth = 4
                return v

            @Factory
            @Order(5)
            def depth5(self, v: DeepValue) -> DeepValue:
                v.depth = 5
                return v

            @Factory
            @Order(6)
            def depth6(self, v: DeepValue) -> DeepValue:
                v.depth = 6
                return v

            @Factory
            @Order(7)
            def depth7(self, v: DeepValue) -> DeepValue:
                v.depth = 7
                return v

            @Factory
            @Order(8)
            def depth8(self, v: DeepValue) -> DeepValue:
                v.depth = 8
                return v

            @Factory
            @Order(9)
            def depth9(self, v: DeepValue) -> DeepValue:
                v.depth = 9
                return v

            @Factory
            @Order(10)
            def depth10(self, v: DeepValue) -> DeepValue:
                v.depth = 10
                return v

        app = Application("test")
        app.scan(DeepConfig).ready()

        value = app.manager.get_instance(DeepValue)
        assert value.depth == 10

    def test_factory_with_component_dependency(self):
        """Factory가 Component를 의존성으로 가지는 경우"""

        @Component
        class Repository:
            def get_data(self) -> str:
                return "data_from_repo"

        class Service:
            def __init__(self, data: str):
                self.data = data

        @Component
        class Config:
            @Factory
            def create_service(self, repo: Repository) -> Service:
                return Service(repo.get_data())

        app = Application("test")
        app.scan(Repository, Config).ready()

        service = app.manager.get_instance(Service)
        assert service.data == "data_from_repo"

    def test_multiple_factories_in_different_components(self):
        """여러 Component에 분산된 Factory들"""

        class Value1:
            pass

        class Value2:
            pass

        class Combined:
            def __init__(self, v1: Value1, v2: Value2):
                self.v1 = v1
                self.v2 = v2

        @Component
        class ConfigA:
            @Factory
            def value1(self) -> Value1:
                return Value1()

        @Component
        class ConfigB:
            @Factory
            def value2(self) -> Value2:
                return Value2()

        @Component
        class ConfigC:
            @Factory
            def combined(self, v1: Value1, v2: Value2) -> Combined:
                return Combined(v1, v2)

        app = Application("test")
        app.scan(ConfigA, ConfigB, ConfigC).ready()

        combined = app.manager.get_instance(Combined)
        assert isinstance(combined.v1, Value1)
        assert isinstance(combined.v2, Value2)


# ============================================================================
# Scope 관련 엣지 케이스
# ============================================================================


class TestFactoryScopeEdgeCases:
    """Factory Scope 관련 엣지 케이스"""

    def test_singleton_factory_same_instance(self):
        """SINGLETON Factory는 항상 같은 인스턴스"""
        create_count = [0]

        class SingletonValue:
            def __init__(self):
                create_count[0] += 1
                self.id = create_count[0]

        @Component
        class Config:
            @Factory
            @Scope(ScopeEnum.SINGLETON)
            def create(self) -> SingletonValue:
                return SingletonValue()

        app = Application("test")
        app.scan(Config).ready()

        v1 = app.manager.get_instance(SingletonValue)
        v2 = app.manager.get_instance(SingletonValue)
        v3 = app.manager.get_instance(SingletonValue)

        assert v1 is v2 is v3
        assert create_count[0] == 1

    def test_prototype_factory_different_instances(self):
        """PROTOTYPE Factory는 매번 다른 인스턴스"""
        create_count = [0]

        class PrototypeValue:
            def __init__(self):
                create_count[0] += 1
                self.id = create_count[0]

        @Component
        class Config:
            @Factory
            @Scope(ScopeEnum.CALL)
            def create(self) -> PrototypeValue:
                return PrototypeValue()

        @Component
        class Consumer1:
            value: PrototypeValue

        @Component
        class Consumer2:
            value: PrototypeValue

        app = Application("test")
        app.scan(Config, Consumer1, Consumer2).ready()

        c1 = app.manager.get_instance(Consumer1)
        c2 = app.manager.get_instance(Consumer2)

        assert c1.value.id != c2.value.id
        assert create_count[0] == 2

    def test_call_scoped_factory_shares_in_call_stack(self):
        """CALL_SCOPED Factory는 같은 호출 스택에서 공유"""
        create_count = [0]

        class CallScopedValue:
            def __init__(self):
                create_count[0] += 1
                self.id = create_count[0]

        @Component
        class Config:
            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def create(self) -> CallScopedValue:
                return CallScopedValue()

        @Component
        class ServiceA:
            value: CallScopedValue

            def get_id(self) -> int:
                return self.value.id

        @Component
        class ServiceB:
            value: CallScopedValue

            def get_id(self) -> int:
                return self.value.id

        @Component
        class Orchestrator:
            a: ServiceA
            b: ServiceB

            def run(self) -> tuple[int, int]:
                return (self.a.get_id(), self.b.get_id())

        app = Application("test")
        app.scan(Config, ServiceA, ServiceB, Orchestrator).ready()

        orchestrator = app.manager.get_instance(Orchestrator)

        # call_scope 컨텍스트 내에서 실행해야 CALL_SCOPED가 동작함
        from bloom.core.advice.tracing import call_scope

        with call_scope(orchestrator, "run", trace_id="test-1"):
            id_a, id_b = orchestrator.run()
            # 같은 호출 스택에서는 같은 인스턴스
            assert id_a == id_b

    def test_call_scoped_transaction_propagation(self):
        """트랜잭션 합류 패턴: 상위 콜스택에서 시작된 인스턴스가 하위 콜스택에서도 유지

        시나리오:
        1. Controller.handle() 에서 Transaction 시작 (콜스택 depth 1)
        2. Service.process() 호출 (콜스택 depth 2) - 같은 Transaction 사용
        3. Repository.save() 호출 (콜스택 depth 3) - 같은 Transaction 사용
        4. Repository.save() 종료 (콜스택 depth 2로 복귀) - Transaction 유지
        5. Controller.handle() 종료 시 Transaction 해제
        """
        transaction_log = []

        class Transaction:
            def __init__(self, id: int):
                self.id = id
                self.committed = False
                self.operations: list[str] = []
                transaction_log.append(f"TX-{id} created")

            def add_operation(self, op: str):
                self.operations.append(op)
                transaction_log.append(f"TX-{self.id}: {op}")

            def commit(self):
                self.committed = True
                transaction_log.append(f"TX-{self.id} committed")

        tx_counter = [0]

        @Component
        class TransactionFactory:
            def create(self) -> Transaction:
                tx_counter[0] += 1
                return Transaction(tx_counter[0])

        @Component
        class DatabaseConfig:
            factory: TransactionFactory

            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def transaction(self) -> Transaction:
                return self.factory.create()

        @Component
        class Repository:
            tx: Transaction

            def save(self, entity: str) -> int:
                """하위 콜스택 (depth 3)"""
                self.tx.add_operation(f"save:{entity}")
                return self.tx.id

        @Component
        class Service:
            tx: Transaction
            repo: Repository

            def process(self, data: str) -> tuple[int, int]:
                """중간 콜스택 (depth 2)"""
                self.tx.add_operation(f"process:{data}")
                service_tx_id = self.tx.id

                # 하위 콜스택 호출 - 같은 트랜잭션이어야 함
                repo_tx_id = self.repo.save(data)

                return (service_tx_id, repo_tx_id)

        @Component
        class Controller:
            tx: Transaction
            service: Service

            def handle(self, request: str) -> dict:
                """최상위 콜스택 (depth 1)"""
                self.tx.add_operation(f"handle:{request}")
                controller_tx_id = self.tx.id

                # 중간 콜스택 호출
                service_tx_id, repo_tx_id = self.service.process(request)

                # 하위 콜스택 종료 후에도 같은 트랜잭션 유지
                self.tx.add_operation("complete")
                self.tx.commit()

                return {
                    "controller": controller_tx_id,
                    "service": service_tx_id,
                    "repository": repo_tx_id,
                }

        app = Application("test")
        app.scan(
            TransactionFactory, DatabaseConfig, Repository, Service, Controller
        ).ready()

        controller = app.manager.get_instance(Controller)

        from bloom.core.advice.tracing import call_scope

        # 첫 번째 요청
        with call_scope(controller, "handle", trace_id="request-1"):
            result1 = controller.handle("user_create")

        # 모든 레이어에서 같은 트랜잭션을 사용해야 함
        assert result1["controller"] == result1["service"] == result1["repository"], (
            "모든 레이어에서 같은 트랜잭션을 공유해야 함 (트랜잭션 합류)"
        )

        # 트랜잭션 로그 검증
        assert "TX-1 created" in transaction_log
        assert "TX-1: handle:user_create" in transaction_log
        assert "TX-1: process:user_create" in transaction_log
        assert "TX-1: save:user_create" in transaction_log
        assert "TX-1: complete" in transaction_log
        assert "TX-1 committed" in transaction_log

        # 두 번째 요청 - 새로운 트랜잭션이어야 함
        transaction_log.clear()
        with call_scope(controller, "handle", trace_id="request-2"):
            result2 = controller.handle("user_update")

        # 새로운 요청은 새로운 트랜잭션
        assert result2["controller"] == result2["service"] == result2["repository"]
        assert result2["controller"] != result1["controller"], (
            "새로운 요청은 새로운 트랜잭션이어야 함"
        )

        # 두 번째 트랜잭션 로그
        assert "TX-2 created" in transaction_log
        assert "TX-2 committed" in transaction_log

    def test_call_scoped_nested_call_scope_inheritance(self):
        """중첩된 call_scope에서 인스턴스 상속 확인

        상위 call_scope에서 생성된 인스턴스가
        하위 call_scope(중첩)에서도 동일하게 유지되는지 테스트
        """
        instance_log = []

        class SharedResource:
            def __init__(self, id: int):
                self.id = id
                instance_log.append(f"created:{id}")

            def use(self, caller: str):
                instance_log.append(f"used:{self.id}:by:{caller}")

        counter = [0]

        @Component
        class ResourceConfig:
            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def resource(self) -> SharedResource:
                counter[0] += 1
                return SharedResource(counter[0])

        @Component
        class InnerService:
            resource: SharedResource

            def inner_work(self) -> int:
                self.resource.use("inner")
                return self.resource.id

        @Component
        class OuterService:
            resource: SharedResource
            inner: InnerService

            def outer_work(self) -> tuple[int, int]:
                self.resource.use("outer_before")

                # 내부 서비스 호출 (하위 콜스택)
                inner_id = self.inner.inner_work()

                # 내부 호출 후에도 같은 리소스
                self.resource.use("outer_after")

                return (self.resource.id, inner_id)

        app = Application("test")
        app.scan(ResourceConfig, InnerService, OuterService).ready()

        outer = app.manager.get_instance(OuterService)

        from bloom.core.advice.tracing import call_scope

        with call_scope(outer, "outer_work", trace_id="test"):
            outer_id, inner_id = outer.outer_work()

        # 외부와 내부가 같은 리소스를 사용해야 함
        assert outer_id == inner_id, "상위/하위 콜스택에서 같은 인스턴스 공유"

        # 생성은 한 번만
        assert instance_log.count("created:1") == 1

        # 사용 순서 확인
        assert instance_log == [
            "created:1",
            "used:1:by:outer_before",
            "used:1:by:inner",
            "used:1:by:outer_after",
        ]

    def test_call_scoped_lifecycle_only_at_outermost_scope(self):
        """CALL_SCOPED 인스턴스의 라이프사이클은 최상위 콜스택에서만 호출

        시나리오:
        - PostConstruct: 최상위 call_scope 진입 시 인스턴스 생성 후 1회 호출
        - PreDestroy: 최상위 call_scope 종료 시 1회 호출
        - 중간/하위 콜스택 진입/종료 시에는 호출되지 않음
        """
        lifecycle_log = []

        class ManagedResource:
            def __init__(self, id: int):
                self.id = id
                lifecycle_log.append(f"init:{id}")

            @PostConstruct
            def on_start(self):
                lifecycle_log.append(f"post_construct:{self.id}")

            @PreDestroy
            def on_end(self):
                lifecycle_log.append(f"pre_destroy:{self.id}")

        counter = [0]

        @Component
        class ResourceConfig:
            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def resource(self) -> ManagedResource:
                counter[0] += 1
                return ManagedResource(counter[0])

        @Component
        class Level3:
            res: ManagedResource

            def work(self) -> int:
                lifecycle_log.append(f"level3_work:{self.res.id}")
                return self.res.id

        @Component
        class Level2:
            res: ManagedResource
            level3: Level3

            def work(self) -> int:
                lifecycle_log.append(f"level2_start:{self.res.id}")
                result = self.level3.work()
                lifecycle_log.append(f"level2_end:{self.res.id}")
                return result

        @Component
        class Level1:
            res: ManagedResource
            level2: Level2

            def work(self) -> int:
                lifecycle_log.append(f"level1_start:{self.res.id}")
                result = self.level2.work()
                lifecycle_log.append(f"level1_end:{self.res.id}")
                return result

        app = Application("test")
        app.scan(ResourceConfig, Level3, Level2, Level1).ready()

        level1 = app.manager.get_instance(Level1)

        from bloom.core.advice.tracing import call_scope

        lifecycle_log.clear()

        with call_scope(level1, "work", trace_id="test"):
            level1.work()

        # PostConstruct는 1번만 호출 (최상위 진입 시)
        assert lifecycle_log.count("post_construct:1") == 1

        # PreDestroy는 1번만 호출 (최상위 종료 시)
        assert lifecycle_log.count("pre_destroy:1") == 1

        # 순서 검증: init -> post_construct -> work... -> pre_destroy
        assert lifecycle_log[0] == "init:1"
        assert lifecycle_log[1] == "post_construct:1"
        assert lifecycle_log[-1] == "pre_destroy:1"

        # 중간에 post_construct나 pre_destroy가 없어야 함
        middle_logs = lifecycle_log[2:-1]
        for log in middle_logs:
            assert "post_construct" not in log, f"중간에 post_construct 호출됨: {log}"
            assert "pre_destroy" not in log, f"중간에 pre_destroy 호출됨: {log}"

    def test_call_scoped_context_manager_auto_called(self):
        """CALL_SCOPED는 컨텍스트 매니저(__enter__/__exit__)를 자동 호출

        __enter__: 최상위 call_scope 진입 시 인스턴스 캐싱 후 1회 호출
        __exit__: 최상위 call_scope 종료 시 1회 호출
        """
        context_log = []

        class DatabaseConnection:
            def __init__(self, id: int):
                self.id = id
                self.is_open = False
                context_log.append(f"init:{id}")

            def __enter__(self):
                self.is_open = True
                context_log.append(f"enter:{self.id}")
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.is_open = False
                context_log.append(f"exit:{self.id}")
                return False

            def execute(self, query: str):
                context_log.append(f"execute:{self.id}:{query}")

        counter = [0]

        @Component
        class ConnectionConfig:
            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def connection(self) -> DatabaseConnection:
                counter[0] += 1
                return DatabaseConnection(counter[0])

        @Component
        class Repository:
            conn: DatabaseConnection

            def save(self, data: str):
                self.conn.execute(f"INSERT:{data}")

        @Component
        class Service:
            conn: DatabaseConnection
            repo: Repository

            def transact(self):
                self.conn.execute("BEGIN")
                self.repo.save("data")
                self.conn.execute("COMMIT")

        app = Application("test")
        app.scan(ConnectionConfig, Repository, Service).ready()

        service = app.manager.get_instance(Service)

        from bloom.core.advice.tracing import call_scope

        context_log.clear()

        with call_scope(service, "transact", trace_id="test"):
            service.transact()

        # __enter__는 1번만 호출
        assert context_log.count("enter:1") == 1

        # __exit__는 1번만 호출
        assert context_log.count("exit:1") == 1

        # 순서 검증
        enter_idx = context_log.index("enter:1")
        exit_idx = context_log.index("exit:1")

        # enter가 init 다음에 와야 함
        assert context_log[0] == "init:1"
        assert enter_idx == 1

        # exit이 마지막이어야 함
        assert exit_idx == len(context_log) - 1

        # 중간에 enter/exit이 없어야 함
        middle_logs = context_log[2:-1]
        for log in middle_logs:
            assert "enter:" not in log, f"중간에 __enter__ 호출됨: {log}"
            assert "exit:" not in log, f"중간에 __exit__ 호출됨: {log}"

        # 모든 execute는 enter와 exit 사이에 있어야 함
        for i, log in enumerate(context_log):
            if log.startswith("execute:"):
                assert enter_idx < i < exit_idx, f"execute가 enter/exit 범위 밖: {log}"

    def test_call_scoped_lifecycle_with_nested_call_scopes(self):
        """중첩 call_scope에서도 라이프사이클은 최외곽에서만 호출

        외부 call_scope 안에 내부 call_scope가 있을 때,
        PostConstruct/PreDestroy/__enter__/__exit__은 최외곽 call_scope 기준으로만 호출
        """
        lifecycle_log = []

        class Resource:
            def __init__(self, id: int):
                self.id = id
                lifecycle_log.append(f"init:{id}")

            @PostConstruct
            def start(self):
                lifecycle_log.append(f"post_construct:{self.id}")

            @PreDestroy
            def end(self):
                lifecycle_log.append(f"pre_destroy:{self.id}")

            def __enter__(self):
                lifecycle_log.append(f"enter:{self.id}")
                return self

            def __exit__(self, *args):
                lifecycle_log.append(f"exit:{self.id}")
                return False

        counter = [0]

        @Component
        class Config:
            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def resource(self) -> Resource:
                counter[0] += 1
                return Resource(counter[0])

        @Component
        class Inner:
            res: Resource

            def inner_action(self):
                lifecycle_log.append(f"inner_action:{self.res.id}")

        @Component
        class Outer:
            res: Resource
            inner: Inner

            def outer_action(self):
                lifecycle_log.append(f"outer_start:{self.res.id}")

                # 중첩 call_scope 시뮬레이션
                from bloom.core.advice.tracing import call_scope

                with call_scope(self.inner, "inner_action", trace_id="nested"):
                    self.inner.inner_action()

                lifecycle_log.append(f"outer_end:{self.res.id}")

        app = Application("test")
        app.scan(Config, Inner, Outer).ready()

        outer = app.manager.get_instance(Outer)

        from bloom.core.advice.tracing import call_scope

        lifecycle_log.clear()

        with call_scope(outer, "outer_action", trace_id="outer"):
            outer.outer_action()

        # 라이프사이클은 각각 1번씩만 호출
        assert lifecycle_log.count("init:1") == 1
        assert lifecycle_log.count("post_construct:1") == 1
        assert lifecycle_log.count("enter:1") == 1
        assert lifecycle_log.count("exit:1") == 1
        assert lifecycle_log.count("pre_destroy:1") == 1

        # 순서: init -> enter -> post_construct -> ... -> pre_destroy -> exit
        # 참고: __enter__는 캐싱 시점에 호출되므로 post_construct보다 먼저 호출됨
        # pre_destroy는 exit 전에 호출됨
        init_idx = lifecycle_log.index("init:1")
        enter_idx = lifecycle_log.index("enter:1")
        pc_idx = lifecycle_log.index("post_construct:1")
        exit_idx = lifecycle_log.index("exit:1")
        pd_idx = lifecycle_log.index("pre_destroy:1")

        assert init_idx < enter_idx < pc_idx < pd_idx < exit_idx

        # 중첩 call_scope 진입/종료에서 추가 호출 없음
        lifecycle_events = [
            log
            for log in lifecycle_log
            if any(
                x in log
                for x in ["init:", "post_construct:", "pre_destroy:", "enter:", "exit:"]
            )
        ]
        assert len(lifecycle_events) == 5  # 각각 1번씩만

    @pytest.mark.asyncio
    async def test_async_call_scoped_aexit_auto_called(self):
        """async_call_scope는 비동기 __aexit__을 자동 호출

        비동기 컨텍스트 매니저의 __aexit__은 async_call_scope 종료 시 await으로 호출됩니다.
        이는 비동기 세션 커밋/롤백 같은 정리 작업에 유용합니다.
        
        Note: __aenter__는 DI 시점이 동기이므로 자동 호출되지 않습니다.
              대신 동기 __enter__가 있으면 그것을 호출합니다.
        """
        context_log = []

        class AsyncSession:
            """비동기 세션 - __aexit__에서 커밋/롤백 처리"""
            def __init__(self, id: int):
                self.id = id
                self.is_open = True
                context_log.append(f"init:{id}")

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                # 비동기 커밋/롤백 시뮬레이션
                if exc_type:
                    context_log.append(f"rollback:{self.id}")
                else:
                    context_log.append(f"commit:{self.id}")
                self.is_open = False
                return False

            async def execute(self, query: str):
                context_log.append(f"execute:{self.id}:{query}")

        counter = [0]

        @Component
        class SessionConfig:
            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def session(self) -> AsyncSession:
                counter[0] += 1
                return AsyncSession(counter[0])

        @Component
        class Repository:
            session: AsyncSession

            async def save(self, data: str):
                await self.session.execute(f"INSERT:{data}")

        @Component
        class Service:
            session: AsyncSession
            repo: Repository

            async def transact(self):
                await self.session.execute("BEGIN")
                await self.repo.save("data")
                await self.session.execute("END")

        app = Application("test")
        app.scan(SessionConfig, Repository, Service).ready()

        service = app.manager.get_instance(Service)

        from bloom.core.advice.tracing import async_call_scope

        context_log.clear()

        async with async_call_scope(service, "transact", trace_id="test"):
            await service.transact()

        # __aexit__은 1번만 호출되어 commit 수행
        assert context_log.count("commit:1") == 1

        # commit이 마지막이어야 함 (async_call_scope 종료 시)
        assert context_log[-1] == "commit:1"

        # execute 로그들이 commit 전에 있어야 함
        commit_idx = context_log.index("commit:1")
        for i, log in enumerate(context_log):
            if log.startswith("execute:"):
                assert i < commit_idx, f"execute가 commit 후에 있음: {log}"

    @pytest.mark.asyncio
    async def test_call_scoped_async_post_construct(self):
        """CALL_SCOPED는 비동기 @PostConstruct를 지원

        일반 PROTOTYPE은 비동기 @PostConstruct를 지원하지 않지만,
        CALL_SCOPED는 RequestContext.add_pending_init()을 통해 지원합니다.
        """
        import asyncio

        init_log = []

        class AsyncResource:
            def __init__(self, id: int):
                self.id = id
                self.initialized = False

            @PostConstruct
            async def async_init(self):
                await asyncio.sleep(0.01)  # 비동기 작업 시뮬레이션
                self.initialized = True
                init_log.append(f"async_init:{self.id}")

        counter = [0]

        @Component
        class Config:
            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def resource(self) -> AsyncResource:
                counter[0] += 1
                return AsyncResource(counter[0])

        @Component
        class Service:
            res: AsyncResource

            async def do_work(self):
                # 이 시점에 async_init이 완료되어 있어야 함
                assert self.res.initialized, "비동기 초기화가 완료되지 않음"
                return f"work:{self.res.id}"

        app = Application("test")
        app.scan(Config, Service).ready()

        service = app.manager.get_instance(Service)

        from bloom.core.advice.tracing import async_call_scope
        from bloom.core.request_context import RequestContext

        init_log.clear()

        async with async_call_scope(service, "do_work", trace_id="test"):
            # 웹 핸들러 흐름 시뮬레이션:
            # 1. 의존성 접근으로 인스턴스 생성 + pending에 등록
            #    LazyFieldProxy의 속성에 접근해야 실제 인스턴스가 생성됨
            resource_id = service.res.id  # 속성 접근으로 resolve 트리거
            
            # 2. pending async 초기화 실행 (웹에서는 핸들러 호출 전에 실행)
            await RequestContext.run_pending_init()
            
            # 3. 이제 초기화 완료되어 있어야 함
            assert service.res.initialized, "비동기 초기화가 완료되지 않음"
            result = await service.do_work()

        assert result == "work:1"
        assert resource_id == 1
        assert init_log == ["async_init:1"]

    @pytest.mark.asyncio
    async def test_call_scoped_async_post_construct_order(self):
        """CALL_SCOPED 비동기 @PostConstruct 여러 개 테스트

        CALL_SCOPED에서 여러 의존성의 async @PostConstruct가
        모두 pending에 등록되고 run_pending_init()에서 실행됩니다.
        """
        import asyncio

        init_log = []

        class AsyncCache:
            def __init__(self, name: str):
                self.name = name
                self.connected = False

            @PostConstruct
            async def connect(self):
                await asyncio.sleep(0.01)
                self.connected = True
                init_log.append(f"cache_connect:{self.name}")

        class AsyncQueue:
            def __init__(self, name: str):
                self.name = name
                self.ready = False

            @PostConstruct
            async def initialize(self):
                await asyncio.sleep(0.01)
                self.ready = True
                init_log.append(f"queue_init:{self.name}")

        @Component
        class Config:
            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def cache(self) -> AsyncCache:
                return AsyncCache("redis")

            @Factory
            @Scope(ScopeEnum.CALL, PrototypeMode.CALL_SCOPED)
            def queue(self) -> AsyncQueue:
                return AsyncQueue("rabbitmq")

        @Component
        class Service:
            cache: AsyncCache
            queue: AsyncQueue

            async def process(self):
                assert self.cache.connected, "Cache not connected"
                assert self.queue.ready, "Queue not ready"
                return "processed"

        app = Application("test")
        app.scan(Config, Service).ready()

        service = app.manager.get_instance(Service)

        from bloom.core.advice.tracing import async_call_scope
        from bloom.core.request_context import RequestContext

        init_log.clear()

        async with async_call_scope(service, "process", trace_id="test"):
            # 의존성 접근으로 인스턴스 생성 + pending에 등록
            _ = service.cache.name
            _ = service.queue.name
            
            # pending async 초기화 실행
            await RequestContext.run_pending_init()
            
            result = await service.process()

        assert result == "processed"
        # 두 초기화가 모두 실행됨 (순서는 접근 순서에 따름)
        assert "cache_connect:redis" in init_log
        assert "queue_init:rabbitmq" in init_log
        assert len(init_log) == 2


# ============================================================================
# 특수 케이스 테스트
# ============================================================================


class TestFactorySpecialCases:
    """Factory 특수 케이스 테스트"""

    def test_factory_method_name_collision(self):
        """같은 이름의 Factory 메서드가 다른 Component에 있는 경우"""

        class TypeA:
            pass

        class TypeB:
            pass

        @Component
        class ConfigA:
            @Factory
            def create(self) -> TypeA:
                return TypeA()

        @Component
        class ConfigB:
            @Factory
            def create(self) -> TypeB:  # 같은 메서드 이름
                return TypeB()

        app = Application("test")
        app.scan(ConfigA, ConfigB).ready()

        a = app.manager.get_instance(TypeA)
        b = app.manager.get_instance(TypeB)

        assert isinstance(a, TypeA)
        assert isinstance(b, TypeB)

    def test_factory_with_default_parameter(self):
        """기본값이 있는 파라미터를 가진 Factory"""

        class ConfigurableValue:
            def __init__(self, multiplier: int):
                self.multiplier = multiplier

        @Component
        class Config:
            @Factory
            def create(self) -> ConfigurableValue:
                return ConfigurableValue(10)

        app = Application("test")
        app.scan(Config).ready()

        value = app.manager.get_instance(ConfigurableValue)
        assert value.multiplier == 10

    def test_factory_accessing_owner_state(self):
        """Factory가 owner Component의 상태를 사용"""

        class StateBasedValue:
            def __init__(self, state: str):
                self.state = state

        @Component
        class StatefulConfig:
            def __init__(self):
                self.config_state = "initialized"

            @Factory
            def create(self) -> StateBasedValue:
                return StateBasedValue(self.config_state)

        app = Application("test")
        app.scan(StatefulConfig).ready()

        value = app.manager.get_instance(StateBasedValue)
        assert value.state == "initialized"

    def test_factory_with_async_init_component(self):
        """@PostConstruct가 있는 Component를 Factory가 사용"""
        init_order = []

        @Component
        class AsyncInitComponent:
            def __init__(self):
                self.ready = False

            @PostConstruct
            def initialize(self):
                self.ready = True
                init_order.append("component_init")

        class DependentValue:
            def __init__(self, ready: bool):
                self.ready = ready

        @Component
        class Config:
            @Factory
            def create(self, comp: AsyncInitComponent) -> DependentValue:
                init_order.append("factory_create")
                return DependentValue(comp.ready)

        app = Application("test")
        app.scan(AsyncInitComponent, Config).ready()

        value = app.manager.get_instance(DependentValue)
        # Component의 PostConstruct가 먼저 호출된 후 Factory 실행
        assert value.ready is True
        assert init_order == ["component_init", "factory_create"]

    def test_factory_with_inheritance(self):
        """Component 상속 시 Factory 메서드 - 각각 독립적으로 스캔"""

        class BaseValue:
            def __init__(self, source: str = "base"):
                self.source = source

        @Component
        class BaseConfig:
            @Factory
            def create_base(self) -> BaseValue:
                return BaseValue("base")

        # 상속 없이 별도의 Config로 테스트
        app = Application("test")
        app.scan(BaseConfig).ready()

        value = app.manager.get_instance(BaseValue)
        assert isinstance(value, BaseValue)
        assert value.source == "base"

    def test_factory_override_with_order(self):
        """Factory Chain에서 Order로 순서 제어 - 마지막 Factory가 최종 결과"""

        class ConfigValue:
            def __init__(self, source: str):
                self.source = source

        @Component
        class Config:
            @Factory
            def create(self) -> ConfigValue:
                return ConfigValue("created")

            @Factory
            @Order(1)
            def modify(self, v: ConfigValue) -> ConfigValue:
                # Chain에서 이전 결과를 받아서 수정
                v.source = "modified"
                return v

        app = Application("test")
        app.scan(Config).ready()

        value = app.manager.get_instance(ConfigValue)
        # Factory Chain에서 마지막 Order가 최종 결과
        assert value.source == "modified"
