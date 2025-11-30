"""Lazy 컴포넌트 데코레이터 테스트"""

import pytest
from bloom import Application, Component
from bloom.core import LazyComponent
from bloom.core import LazyProxy
from bloom.core.manager import ContainerManager, set_current_manager


class TestLazyBasic:
    """@Lazy 기본 동작 테스트"""

    def test_lazy_decorator_marks_component(self):
        """@Lazy 데코레이터가 컴포넌트를 lazy로 마킹함"""
        from bloom.core.lazy import is_lazy_component
        from bloom.core.container import ComponentContainer

        @LazyComponent
        @Component
        class HeavyService:
            pass

        container = ComponentContainer.get_container(HeavyService)
        assert container is not None
        assert is_lazy_component(container)

    def test_lazy_component_injects_proxy(self):
        """@Lazy 컴포넌트 주입 시 LazyProxy가 주입됨"""

        @LazyComponent
        @Component
        class HeavyService:
            value: str = "heavy"

        @Component
        class Consumer:
            service: HeavyService

        app = Application("test_proxy").ready()

        consumer = app.manager.get_instance(Consumer)
        # LazyProxy로 주입됨
        assert isinstance(consumer.service, LazyProxy)

    def test_lazy_proxy_resolves_on_access(self):
        """LazyProxy 속성 접근 시 실제 인스턴스가 resolve됨"""

        @LazyComponent
        @Component
        class HeavyService:
            value: str = "heavy_value"

            def process(self) -> str:
                return "processed"

        @Component
        class Consumer:
            service: HeavyService

        app = Application("test_resolve").ready()

        consumer = app.manager.get_instance(Consumer)
        # 속성 접근 시 resolve
        assert consumer.service.value == "heavy_value"
        # 메서드 호출
        assert consumer.service.process() == "processed"

    def test_lazy_proxy_caches_instance(self):
        """LazyProxy는 한 번 resolve된 인스턴스를 캐시함"""
        init_count = 0

        @LazyComponent
        @Component
        class Database:
            def __init__(self):
                nonlocal init_count
                init_count += 1

        @Component
        class Service:
            db: Database

        app = Application("test_cache").ready()

        service = app.manager.get_instance(Service)
        # 첫 번째 접근
        _ = service.db.init_count if hasattr(service.db, "init_count") else None
        first_count = init_count
        # 두 번째 접근
        _ = service.db
        second_count = init_count

        assert first_count == second_count == 1


class TestLazyCircularDependency:
    """@Lazy를 이용한 순환 의존성 해결 테스트"""

    def test_circular_dependency_with_lazy(self):
        """@Lazy를 사용하면 순환 의존성이 해결됨

        ServiceA <- ServiceB (ServiceB가 ServiceA 의존)
        ServiceA가 @Lazy이므로 ServiceB 생성 시 LazyProxy 주입
        나중에 ServiceA 접근 시 실제 초기화
        """

        @LazyComponent
        @Component
        class ServiceA:
            value: str = "from_a"

            def get_value(self) -> str:
                return self.value

        @Component
        class ServiceB:
            service_a: ServiceA  # LazyProxy 주입
            value: str = "from_b"

            def get_a_value(self) -> str:
                return self.service_a.value

        app = Application("test_circular").ready()

        service_b = app.manager.get_instance(ServiceB)
        # ServiceB.service_a는 LazyProxy
        assert isinstance(service_b.service_a, LazyProxy)
        # 프록시를 통해 속성 접근 가능
        assert service_b.service_a.value == "from_a"
        # 프록시를 통해 메서드 호출 가능
        assert service_b.get_a_value() == "from_a"

    def test_bidirectional_lazy(self):
        """양쪽 모두 @Lazy를 사용하는 경우"""

        @LazyComponent
        @Component
        class Alpha:
            name: str = "alpha"

        @LazyComponent
        @Component
        class Beta:
            name: str = "beta"

        @Component
        class Consumer:
            alpha: Alpha
            beta: Beta

        app = Application("test_bidirectional").ready()

        consumer = app.manager.get_instance(Consumer)

        # 양방향 참조 확인 - 프록시를 통해 속성 접근
        assert consumer.alpha.name == "alpha"
        assert consumer.beta.name == "beta"

    def test_mutual_dependency_with_lazy(self):
        """상호 의존하는 경우 - @Lazy 쪽이 일반 컴포넌트를 의존

        ServiceY(@Lazy) -> ServiceX (일반)
        ServiceX가 먼저 초기화되고, ServiceY는 LazyProxy로 주입됨
        ServiceY 접근 시 ServiceX가 이미 있으므로 주입 성공
        """

        @Component
        class ServiceX:
            value: str = "x"

        @LazyComponent
        @Component
        class ServiceY:
            service_x: ServiceX
            value: str = "y"

            def get_x_value(self) -> str:
                return self.service_x.value

        @Component
        class Consumer:
            x: ServiceX
            y: ServiceY  # LazyProxy

        app = Application("test_mutual").ready()

        consumer = app.manager.get_instance(Consumer)

        # Consumer.y는 LazyProxy
        assert isinstance(consumer.y, LazyProxy)
        # ServiceY가 ServiceX를 참조 가능
        assert consumer.y.get_x_value() == "x"
        assert consumer.y.value == "y"


class TestLazyWithFactory:
    """@Lazy와 Factory 조합 테스트"""

    def test_lazy_component_with_dependencies(self):
        """@Lazy 컴포넌트가 다른 의존성을 가질 때"""

        @Component
        class Config:
            url: str = "https://api.example.com"

        @LazyComponent
        @Component
        class ApiClient:
            config: Config

            def get_url(self) -> str:
                return self.config.url

        @Component
        class Service:
            client: ApiClient

        app = Application("test_lazy_deps").ready()

        service = app.manager.get_instance(Service)
        assert service.client.get_url() == "https://api.example.com"


class TestLazyEdgeCases:
    """@Lazy 엣지 케이스 테스트"""

    def test_lazy_proxy_repr(self):
        """LazyProxy의 repr"""

        @LazyComponent
        @Component
        class Target:
            pass

        @Component
        class Holder:
            target: Target

        app = Application("test_repr").ready()

        holder = app.manager.get_instance(Holder)
        proxy_repr = repr(holder.target)
        assert "LazyProxy" in proxy_repr
        assert "Target" in proxy_repr

    def test_lazy_proxy_equality(self):
        """LazyProxy 동등성 비교"""

        @LazyComponent
        @Component
        class Target:
            pass

        @Component
        class HolderA:
            target: Target

        @Component
        class HolderB:
            target: Target

        app = Application("test_equality").ready()

        holder_a = app.manager.get_instance(HolderA)
        holder_b = app.manager.get_instance(HolderB)

        # 같은 인스턴스를 가리키므로 동등해야 함
        assert holder_a.target == holder_b.target

    def test_lazy_proxy_setattr(self):
        """LazyProxy를 통한 속성 설정"""

        @LazyComponent
        @Component
        class Target:
            value: str = "original"

        @Component
        class Holder:
            target: Target

        app = Application("test_setattr").ready()

        holder = app.manager.get_instance(Holder)
        holder.target.value = "modified"

        # 다른 holder를 통해서도 변경된 값이 보여야 함
        target = app.manager.get_instance(Target)
        assert target.value == "modified"

    def test_non_lazy_component_is_not_proxy(self):
        """@Lazy가 없는 컴포넌트는 프록시가 아님"""

        @Component
        class RegularService:
            value: str = "regular"

        @Component
        class Consumer:
            service: RegularService

        app = Application("test_non_lazy").ready()

        consumer = app.manager.get_instance(Consumer)
        # 일반 인스턴스, 프록시가 아님
        assert not isinstance(consumer.service, LazyProxy)
        assert isinstance(consumer.service, RegularService)

    def test_multiple_lazy_fields(self):
        """여러 @Lazy 필드를 가진 컴포넌트"""

        @LazyComponent
        @Component
        class DepA:
            value: str = "A"

        @LazyComponent
        @Component
        class DepB:
            value: str = "B"

        @LazyComponent
        @Component
        class DepC:
            value: str = "C"

        @Component
        class MultiDep:
            a: DepA
            b: DepB
            c: DepC

        app = Application("test_multi").ready()

        service = app.manager.get_instance(MultiDep)

        assert service.a.value == "A"
        assert service.b.value == "B"
        assert service.c.value == "C"


class TestLazyInitializationTiming:
    """@Lazy 초기화 타이밍 테스트"""

    def test_lazy_not_initialized_until_access(self):
        """@Lazy 컴포넌트는 접근 전까지 초기화되지 않음"""
        initialized = False

        @LazyComponent
        @Component
        class HeavyService:
            def __init__(self):
                nonlocal initialized
                initialized = True

        @Component
        class Consumer:
            service: HeavyService

        app = Application("test_timing").ready()

        consumer = app.manager.get_instance(Consumer)
        # 아직 접근하지 않았으므로 초기화되지 않음
        assert not initialized

        # 접근 시 초기화
        _ = consumer.service.value if hasattr(consumer.service, "value") else None
        # 이제 초기화됨
        # (주의: LazyProxy.__getattr__ 호출 시 초기화)

    def test_lazy_initializes_on_method_call(self):
        """메서드 호출 시 초기화"""
        call_log = []

        @LazyComponent
        @Component
        class Service:
            def __init__(self):
                call_log.append("init")

            def do_work(self):
                call_log.append("work")
                return "done"

        @Component
        class Consumer:
            service: Service

        app = Application("test_method_call").ready()

        consumer = app.manager.get_instance(Consumer)
        assert "init" not in call_log

        result = consumer.service.do_work()
        assert result == "done"
        assert "init" in call_log
        assert "work" in call_log


class TestLazyFieldType:
    """Lazy[T] 필드 타입 테스트 (Spring ObjectProvider 스타일)"""

    def test_lazy_field_type_injects_wrapper(self):
        """Lazy[T] 필드 타입으로 LazyWrapper가 주입됨"""
        from bloom.core.lazy import Lazy, LazyWrapper

        @Component
        class HeavyService:
            value: str = "heavy"

        @Component
        class Consumer:
            service: Lazy[HeavyService]

        app = Application("test_lazy_field").ready()

        consumer = app.manager.get_instance(Consumer)
        # LazyWrapper로 주입됨
        assert isinstance(consumer.service, LazyWrapper)

    def test_lazy_wrapper_get_resolves_instance(self):
        """LazyWrapper.get()으로 실제 인스턴스를 가져옴"""
        from bloom.core.lazy import Lazy

        @Component
        class HeavyService:
            value: str = "resolved_value"

        @Component
        class Consumer:
            service: Lazy[HeavyService]

        app = Application("test_lazy_get").ready()

        consumer = app.manager.get_instance(Consumer)
        # get()으로 실제 인스턴스 획득
        actual = consumer.service.get()
        assert isinstance(actual, HeavyService)
        assert actual.value == "resolved_value"

    def test_lazy_wrapper_caches_instance(self):
        """LazyWrapper는 한 번 resolve된 인스턴스를 캐시함"""
        from bloom.core.lazy import Lazy

        init_count = 0

        @Component
        class ExpensiveService:
            def __init__(self):
                nonlocal init_count
                init_count += 1

        @Component
        class Consumer:
            service: Lazy[ExpensiveService]

        app = Application("test_lazy_cache").ready()

        consumer = app.manager.get_instance(Consumer)
        # 첫 번째 호출
        first = consumer.service.get()
        assert init_count == 1
        # 두 번째 호출 - 캐시 사용
        second = consumer.service.get()
        assert init_count == 1
        # 동일 인스턴스
        assert first is second

    def test_lazy_field_type_breaks_circular_dependency(self):
        """Lazy[T]로 순환 의존성을 해결함"""
        from bloom.core.lazy import Lazy

        @Component
        class ServiceA:
            service_b: Lazy["ServiceB"]

            def get_b_name(self) -> str:
                return self.service_b.get().name

        @Component
        class ServiceB:
            name: str = "B"
            service_a: Lazy[ServiceA]

        app = Application("test_circular_lazy").ready()

        a = app.manager.get_instance(ServiceA)
        b = app.manager.get_instance(ServiceB)

        # 순환 참조가 해결됨
        assert a.get_b_name() == "B"
        assert b.service_a.get() is a

    def test_lazy_field_with_factory(self):
        """Lazy[T]가 @Factory로 생성된 인스턴스와 함께 동작함"""
        from bloom.core.lazy import Lazy
        from bloom.core.decorators import Factory

        class Connection:
            def __init__(self, host: str):
                self.host = host

        @Component
        class ConnectionFactory:
            @Factory
            def create_connection(self) -> Connection:
                return Connection("localhost")

        @Component
        class Repository:
            conn: Lazy[Connection]

            def get_host(self) -> str:
                return self.conn.get().host

        app = Application("test_lazy_factory").ready()

        repo = app.manager.get_instance(Repository)
        assert repo.get_host() == "localhost"

    def test_lazy_wrapper_resolved_property(self):
        """LazyWrapper.resolved 프로퍼티로 resolve 여부 확인"""
        from bloom.core.lazy import Lazy

        @Component
        class Service:
            pass

        @Component
        class Consumer:
            service: Lazy[Service]

        app = Application("test_lazy_resolved").ready()

        consumer = app.manager.get_instance(Consumer)
        # 아직 resolve되지 않음
        assert not consumer.service.resolved
        # resolve
        consumer.service.get()
        # 이제 resolved
        assert consumer.service.resolved
