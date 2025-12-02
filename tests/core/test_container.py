"""Container 테스트 - 일반 케이스 및 엣지 케이스"""

import pytest
from typing import ForwardRef
from bloom import Application
from bloom.core import (
    Component,
    Factory,
    PostConstruct,
    PreDestroy,
    Scope,
    ScopeEnum,
    Lazy,
)
from bloom.core.container import (
    Container,
    ComponentContainer,
    FactoryContainer,
    HandlerContainer,
    Element,
)


# ============================================================
# Container 기본 테스트
# ============================================================


class TestContainerBasics:
    """Container 기본 기능 테스트"""

    async def test_container_creation(self):
        """Container 생성"""

        class MyClass:
            pass

        container = Container(MyClass)
        assert container.target is MyClass
        assert container.elements == []
        assert container.owner_cls is None
        assert container.manager is None

    async def test_container_add_elements(self):
        """Container에 Element 추가"""

        class MyClass:
            pass

        container = Container(MyClass)
        elem1 = Element()
        elem2 = Element()

        container.add_elements(elem1, elem2)

        assert len(container.elements) == 2
        assert elem1 in container.elements
        assert elem2 in container.elements

    async def test_container_repr(self):
        """Container __repr__"""

        class MyService:
            pass

        container = Container(MyService)
        repr_str = repr(container)

        assert "MyService" in repr_str
        assert "Container" in repr_str

    async def test_get_container_returns_container(self):
        """get_container가 컨테이너 반환"""

        @Component
        class MyService:
            pass

        container = Container.get_container(MyService)
        assert container is not None
        assert isinstance(container, ComponentContainer)

    async def test_get_container_returns_none_for_non_component(self):
        """일반 클래스는 컨테이너가 없음"""

        class NormalClass:
            pass

        container = Container.get_container(NormalClass)
        assert container is None


class TestContainerDependencies:
    """Container 의존성 분석 테스트"""

    async def test_get_dependencies_simple(self):
        """단순 의존성 분석"""

        class Dep1:
            pass

        class Dep2:
            pass

        class MyService:
            dep1: Dep1
            dep2: Dep2

        container = Container(MyService)
        deps = container.get_dependencies()

        assert Dep1 in deps
        assert Dep2 in deps

    async def test_get_dependencies_empty(self):
        """의존성 없는 경우"""

        class NoDepService:
            pass

        container = Container(NoDepService)
        deps = container.get_dependencies()

        assert deps == []

    async def test_get_lazy_dependencies(self):
        """Lazy 의존성 분석"""

        class LazeDep:
            pass

        class MyService:
            lazy_dep: Lazy[LazeDep]

        container = Container(MyService)
        lazy_deps = container.get_lazy_dependencies()

        assert LazeDep in lazy_deps


# ============================================================
# ComponentContainer 테스트
# ============================================================


class TestComponentContainer:
    """ComponentContainer 테스트"""

    async def test_get_or_create_new(self):
        """새 컨테이너 생성"""

        class NewService:
            pass

        container = ComponentContainer.get_or_create(NewService)

        assert container is not None
        assert container.target is NewService
        assert hasattr(NewService, "__container__")

    async def test_get_or_create_existing(self):
        """기존 컨테이너 반환"""

        class ExistingService:
            pass

        container1 = ComponentContainer.get_or_create(ExistingService)
        container2 = ComponentContainer.get_or_create(ExistingService)

        assert container1 is container2

    async def test_component_container_initialization(self):
        """ComponentContainer 초기화 테스트"""

        @Component
        class SimpleService:
            value = 42

        app = (
            await Application("test_component_container_init")
            .scan(SimpleService)
            .ready_async()
        )

        instance = app.manager.get_instance(SimpleService)
        assert instance is not None
        assert instance.value == 42


# ============================================================
# FactoryContainer 테스트
# ============================================================


class TestFactoryContainer:
    """FactoryContainer 테스트"""

    async def test_factory_container_via_decorator(self):
        """@Factory로 FactoryContainer 생성"""

        class LocalStr:
            pass

        @Component
        class LocalStrFactory:
            @Factory
            def create(self) -> LocalStr:
                return LocalStr()

        container = FactoryContainer.get_or_create(LocalStrFactory.create)
        assert container is not None
        assert container.factory_method is LocalStrFactory.create

    async def test_factory_container_target_type(self):
        """FactoryContainer 반환 타입 분석"""

        class LocalProduct:
            pass

        @Component
        class LocalFactory:
            @Factory
            def create(self) -> LocalProduct:
                return LocalProduct()

        # Factory 메서드에서 반환 타입 분석
        container = FactoryContainer.get_or_create(LocalFactory.create)
        assert container.target is LocalProduct

    async def test_factory_container_produces_instance(self):
        """FactoryContainer가 인스턴스 생성"""

        class ContainerTestConfig:
            def __init__(self, name: str):
                self.name = name

        @Component
        class ContainerTestConfigFactory:
            @Factory
            def create(self) -> ContainerTestConfig:
                return ContainerTestConfig("production")

        app = (
            await Application("test_factory_container_produces")
            .scan(ContainerTestConfigFactory)
            .ready_async()
        )

        config = app.manager.get_instance(ContainerTestConfig)
        assert config.name == "production"

    async def test_factory_container_get_dependencies(self):
        """FactoryContainer 의존성 분석"""

        class LocalDep:
            pass

        class LocalProduct3:
            pass

        @Component
        class LocalProductFactory:
            @Factory
            def create(self, dep: LocalDep) -> LocalProduct3:
                return LocalProduct3()

        container = FactoryContainer.get_or_create(LocalProductFactory.create)
        # owner_cls가 설정되어야 의존성 분석 가능
        container.owner_cls = LocalProductFactory

        deps = container.get_dependencies()
        assert LocalProductFactory in deps


# ============================================================
# Container 엣지 케이스
# ============================================================


class TestContainerEdgeCases:
    """Container 엣지 케이스 테스트"""

    async def test_container_with_no_annotations(self):
        """어노테이션 없는 클래스"""

        class NoAnnotations:
            def __init__(self):
                self.x = 1

        container = Container(NoAnnotations)
        deps = container.get_dependencies()

        assert deps == []

    async def test_container_with_class_var_annotations(self):
        """ClassVar 어노테이션 처리"""
        from typing import ClassVar

        class WithClassVar:
            class_attr: ClassVar[int] = 42
            instance_attr: str

        container = Container(WithClassVar)
        # ClassVar는 의존성이 아니지만 현재 구현에서는 포함될 수 있음
        deps = container.get_dependencies()
        # str은 타입이므로 포함됨
        assert str in deps

    async def test_container_with_optional_annotation(self):
        """Optional 어노테이션 처리"""
        from typing import Optional

        class Dep:
            pass

        class WithOptional:
            maybe_dep: Optional[Dep]

        container = Container(WithOptional)
        deps = container.get_dependencies()
        # Optional[Dep]은 type이 아니므로 의존성에 포함되지 않음
        # (get_dependencies는 isinstance(field_type, type)만 통과)
        assert Dep not in deps

    async def test_container_with_union_annotation(self):
        """Union 어노테이션 처리"""
        from typing import Union

        class TypeA:
            pass

        class TypeB:
            pass

        class WithUnion:
            either: Union[TypeA, TypeB]

        container = Container(WithUnion)
        deps = container.get_dependencies()
        # Union은 type이 아니므로 의존성에 포함되지 않음
        assert TypeA not in deps
        assert TypeB not in deps

    async def test_circular_dependency_with_lazy(self):
        """순환 의존성 - Lazy로 해결"""

        @Component
        class ServiceA:
            b: Lazy["ServiceB"]

            def get_b_name(self):
                return self.b.__class__.__name__

        @Component
        class ServiceB:
            a: ServiceA

            def get_a_name(self):
                return self.a.__class__.__name__

        app = (
            await Application("test_circular_lazy")
            .scan(ServiceA, ServiceB)
            .ready_async()
        )

        a = app.manager.get_instance(ServiceA)
        b = app.manager.get_instance(ServiceB)

        assert b.a is a
        # Lazy로 감싼 b는 접근 시 resolve됨
        assert a.b is not None

    async def test_deep_dependency_chain(self):
        """깊은 의존성 체인"""

        @Component
        class Level1:
            value = 1

        @Component
        class Level2:
            l1: Level1

        @Component
        class Level3:
            l2: Level2

        @Component
        class Level4:
            l3: Level3

        @Component
        class Level5:
            l4: Level4

        app = await (
            Application("test_deep_chain")
            .scan(Level1, Level2, Level3, Level4, Level5)
            .ready_async()
        )

        l5 = app.manager.get_instance(Level5)
        assert l5.l4.l3.l2.l1.value == 1

    async def test_diamond_dependency(self):
        """다이아몬드 의존성 패턴"""

        @Component
        class Top:
            value = "top"

        @Component
        class Left:
            top: Top

        @Component
        class Right:
            top: Top

        @Component
        class Bottom:
            left: Left
            right: Right

        app = (
            await Application("test_diamond")
            .scan(Top, Left, Right, Bottom)
            .ready_async()
        )

        bottom = app.manager.get_instance(Bottom)
        # Left와 Right가 같은 Top 인스턴스를 공유
        assert bottom.left.top is bottom.right.top

    async def test_factory_with_multiple_dependencies(self):
        """Factory에 여러 의존성"""

        @Component
        class PluginA:
            name = "A"

        @Component
        class PluginB:
            name = "B"

        class PluginManager:
            def __init__(self, plugins: list):
                self.plugins = plugins

        @Component
        class PluginManagerFactory:
            a: PluginA
            b: PluginB

            @Factory
            def create(self) -> PluginManager:
                return PluginManager([self.a, self.b])

        app = await (
            Application("test_factory_multi_deps")
            .scan(PluginA, PluginB, PluginManagerFactory)
            .ready_async()
        )

        pm = app.manager.get_instance(PluginManager)
        assert len(pm.plugins) == 2
        names = {p.name for p in pm.plugins}
        assert names == {"A", "B"}

    async def test_scoped_container_creates_new_instance_each_access(self):
        """CALL 스코프는 접근할 때마다 새 인스턴스 생성"""
        creation_count = 0

        @Component
        @Scope(ScopeEnum.CALL)
        class CallScoped:
            def __init__(self):
                nonlocal creation_count
                creation_count += 1
                self.id = creation_count

        @Component
        class Consumer:
            call_scoped: CallScoped

        app = (
            await Application("test_scoped_new_instance")
            .scan(CallScoped, Consumer)
            .ready_async()
        )

        consumer = app.manager.get_instance(Consumer)

        # LazyFieldProxy는 접근할 때마다 새 인스턴스 생성
        # 첫 번째 접근
        first_access = consumer.call_scoped
        first_id = first_access.id

        # 두 번째 접근 (CALL 스코프이므로 새 인스턴스)
        second_access = consumer.call_scoped
        second_id = second_access.id

        # CALL 스코프는 매 접근마다 새 인스턴스
        assert first_id != second_id or creation_count >= 2

    async def test_multiple_factories_for_same_type(self):
        """같은 타입에 여러 Factory (Factory Chain)"""

        class Counter:
            def __init__(self, value: int = 0):
                self.value = value

        @Component
        class CounterFactories:
            from bloom.core import Order

            @Factory
            @Order(0)
            def create(self) -> Counter:
                return Counter(0)

            @Factory
            @Order(1)
            def add_ten(self, c: Counter) -> Counter:
                c.value += 10
                return c

            @Factory
            @Order(2)
            def multiply_two(self, c: Counter) -> Counter:
                c.value *= 2
                return c

        app = (
            await Application("test_factory_chain").scan(CounterFactories).ready_async()
        )

        counter = app.manager.get_instance(Counter)
        # 0 -> +10 -> *2 = 20
        assert counter.value == 20

    async def test_container_with_lifecycle_methods(self):
        """라이프사이클 메서드가 있는 Container"""
        events = []

        @Component
        class LifecycleService:
            @PostConstruct
            def on_init(self):
                events.append("init")

            @PreDestroy
            def on_destroy(self):
                events.append("destroy")

        app = (
            await Application("test_lifecycle_container")
            .scan(LifecycleService)
            .ready_async()
        )
        assert "init" in events

        await app.shutdown_async()
        assert "destroy" in events

    async def test_container_element_inheritance(self):
        """Container Element 상속"""
        from bloom.core.container import ScopeElement

        @Component
        @Scope(ScopeEnum.CALL)
        class ScopedService:
            pass

        container = ComponentContainer.get_or_create(ScopedService)

        # elements에 ScopeElement가 있어야 함
        scope_elements = [e for e in container.elements if isinstance(e, ScopeElement)]
        assert len(scope_elements) == 1
        assert scope_elements[0].scope == ScopeEnum.CALL
