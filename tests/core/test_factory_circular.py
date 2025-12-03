"""@Factory Creator/Modifier 패턴을 통한 순환 의존성 해결 테스트"""

import pytest

from bloom.core import (
    Component,
    Configuration,
    Factory,
    get_container_manager,
    reset_container_manager,
)
from bloom.core.decorators import register_factories_from_configuration


class TestFactoryCircularDependency:
    """
    Factory Creator/Modifier 패턴 테스트.

    순환 의존성 문제:
        A -> B -> A (직접 의존 시 순환)

    Factory 패턴 해결:
        1. Creator: A를 기본 상태로 생성
        2. Modifier: 생성된 A에 B를 주입 (B 생성 시 A 참조 가능)
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        """각 테스트 전 manager 리셋"""
        reset_container_manager()
        yield
        reset_container_manager()

    @pytest.mark.asyncio
    async def test_simple_circular_with_factory_creator(self):
        """
        단순 순환 의존성을 Factory Creator로 해결.

        ServiceA <-> ServiceB 상호 참조
        """

        # 먼저 클래스 정의 (순환 참조)
        class ServiceA:
            b: "ServiceB | None" = None

            def get_name(self) -> str:
                return "A"

        class ServiceB:
            def __init__(self, a: ServiceA):
                self.a = a

            def get_name(self) -> str:
                return "B"

        @Configuration
        class CircularConfig:
            @Factory
            def service_a(self) -> ServiceA:
                """Creator: A를 먼저 생성 (B 없이)"""
                return ServiceA()

            @Factory
            def service_b(self, a: ServiceA) -> ServiceB:
                """B 생성 시 A를 주입받음"""
                b = ServiceB(a)
                # Modifier: A에 B를 주입
                a.b = b
                return b

        manager = get_container_manager()
        register_factories_from_configuration(CircularConfig)

        # initialize()로 모든 SINGLETON 인스턴스 생성
        await manager.initialize()

        # ServiceA 먼저 요청 - 캐시에서 가져옴
        a = manager.get_instance(ServiceA)
        assert a is not None
        assert a.get_name() == "A"

        # ServiceB 요청 - 캐시에서 가져옴
        b = manager.get_instance(ServiceB)
        assert b is not None
        assert b.get_name() == "B"
        assert b.a is a  # B가 A를 참조
        assert a.b is b  # A도 B를 참조 (Modifier에 의해)

    @pytest.mark.asyncio
    async def test_three_way_circular_with_factory(self):
        """
        3자 순환 의존성 해결.

        A -> B -> C -> A
        """

        class ServiceA:
            c: "ServiceC | None" = None

        class ServiceB:
            def __init__(self, a: ServiceA):
                self.a = a

        class ServiceC:
            def __init__(self, b: ServiceB):
                self.b = b

        @Configuration
        class ThreeWayConfig:
            @Factory
            def service_a(self) -> ServiceA:
                """A를 먼저 생성 (C 참조 없이)"""
                return ServiceA()

            @Factory
            def service_b(self, a: ServiceA) -> ServiceB:
                """B 생성, A 주입"""
                return ServiceB(a)

            @Factory
            def service_c(self, b: ServiceB, a: ServiceA) -> ServiceC:
                """C 생성, B 주입, 그리고 A에 C 연결 (순환 완성)"""
                c = ServiceC(b)
                a.c = c  # Modifier: 순환 완성
                return c

        manager = get_container_manager()
        register_factories_from_configuration(ThreeWayConfig)
        await manager.initialize()

        a = manager.get_instance(ServiceA)
        b = manager.get_instance(ServiceB)
        c = manager.get_instance(ServiceC)

        # 순환 체인 검증
        assert b.a is a
        assert c.b is b
        assert a.c is c  # 순환 완성

        # 전체 순환 탐색
        assert a.c.b.a is a

    @pytest.mark.asyncio
    async def test_factory_with_post_init_modifier(self):
        """
        Factory + 별도 Modifier 메서드 패턴.
        """

        class Database:
            repository: "Repository | None" = None

        class Repository:
            def __init__(self, db: Database):
                self.db = db

        @Configuration
        class DatabaseConfig:
            _db: Database | None = None
            _repo: Repository | None = None

            @Factory
            def database(self) -> Database:
                """Creator"""
                self._db = Database()
                return self._db

            @Factory
            def repository(self, db: Database) -> Repository:
                """Creator + Modifier"""
                self._repo = Repository(db)
                # Modifier
                db.repository = self._repo
                return self._repo

        manager = get_container_manager()
        register_factories_from_configuration(DatabaseConfig)
        await manager.initialize()

        db = manager.get_instance(Database)
        repo = manager.get_instance(Repository)

        assert repo.db is db
        assert db.repository is repo

    @pytest.mark.asyncio
    async def test_lazy_circular_resolution(self):
        """
        Lazy 주입을 통한 순환 해결 (Factory 없이 Component만으로).

        현재 구현에서는 forward reference가 클래스 정의 시점에서 해결되지 않으면
        필드 주입이 되지 않을 수 있음.
        이를 해결하려면 모듈 레벨에서 클래스를 정의하거나,
        Factory 패턴을 사용해야 함.

        이 테스트는 Factory를 사용한 순환 해결 방식을 검증.
        """

        class LazyServiceA:
            b: "LazyServiceB | None" = None

            def get_b_name(self) -> str:
                if self.b:
                    return self.b.name
                return "None"

        class LazyServiceB:
            a: "LazyServiceA | None" = None
            name: str = "B"

            def get_a(self) -> "LazyServiceA | None":
                return self.a

        @Configuration
        class LazyConfig:
            @Factory
            def lazy_service_a(self) -> LazyServiceA:
                return LazyServiceA()

            @Factory
            def lazy_service_b(self, a: LazyServiceA) -> LazyServiceB:
                b = LazyServiceB()
                b.a = a
                a.b = b  # Modifier 패턴
                return b

        manager = get_container_manager()
        register_factories_from_configuration(LazyConfig)
        await manager.initialize()

        a = manager.get_instance(LazyServiceA)
        b = manager.get_instance(LazyServiceB)

        # Factory를 통한 상호 참조 작동
        assert a.get_b_name() == "B"
        assert b.a is a
        assert a.b is b

    @pytest.mark.asyncio
    async def test_factory_singleton_guarantee(self):
        """
        Factory가 SINGLETON 스코프를 보장하는지.
        순환 참조 시 동일 인스턴스가 사용되어야 함.
        """
        create_count = {"a": 0, "b": 0}

        class CountedA:
            b: "CountedB | None" = None

            def __init__(self):
                create_count["a"] += 1

        class CountedB:
            def __init__(self, a: CountedA):
                create_count["b"] += 1
                self.a = a

        @Configuration
        class CountingConfig:
            @Factory
            def counted_a(self) -> CountedA:
                return CountedA()

            @Factory
            def counted_b(self, a: CountedA) -> CountedB:
                b = CountedB(a)
                a.b = b
                return b

        manager = get_container_manager()
        register_factories_from_configuration(CountingConfig)
        await manager.initialize()

        # 여러 번 요청해도 동일 인스턴스
        a1 = manager.get_instance(CountedA)
        a2 = manager.get_instance(CountedA)
        b1 = manager.get_instance(CountedB)
        b2 = manager.get_instance(CountedB)

        assert a1 is a2
        assert b1 is b2
        assert create_count["a"] == 1
        assert create_count["b"] == 1

    @pytest.mark.asyncio
    async def test_factory_dependency_order(self):
        """
        Factory 의존성 순서가 올바르게 해결되는지.
        """
        order: list[str] = []

        class First:
            def __init__(self):
                order.append("First")

        class Second:
            def __init__(self, first: First):
                order.append("Second")
                self.first = first

        class Third:
            def __init__(self, first: First, second: Second):
                order.append("Third")
                self.first = first
                self.second = second

        @Configuration
        class OrderConfig:
            @Factory
            def first(self) -> First:
                return First()

            @Factory
            def second(self, first: First) -> Second:
                return Second(first)

            @Factory
            def third(self, first: First, second: Second) -> Third:
                return Third(first, second)

        manager = get_container_manager()
        register_factories_from_configuration(OrderConfig)
        await manager.initialize()

        # Third 요청 시 의존성 순서대로 생성
        third = manager.get_instance(Third)

        assert order == ["First", "Second", "Third"]
        assert third.first is third.second.first  # 동일 First 인스턴스
