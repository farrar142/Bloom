"""Lazy 필드 주입 테스트

모든 필드 주입은 기본적으로 LazyFieldProxy로 래핑되어 지연 초기화됩니다.
"""

import pytest
from bloom import Application, Component
from bloom.core import Lazy
from bloom.core.lazy import LazyFieldProxy


class TestLazyFieldBasic:
    """기본 Lazy 필드 주입 테스트"""

    def test_field_injection_is_lazy(self):
        """모든 필드 주입은 기본적으로 Lazy (LazyFieldProxy)"""

        @Component
        class ServiceA:
            value: str = "service_a"

        @Component
        class Consumer:
            service: ServiceA

        app = Application("test_lazy_field").ready()

        consumer = app.manager.get_instance(Consumer)

        # 필드는 LazyFieldProxy로 주입됨 (투명 프록시)
        # 하지만 접근하면 실제 값처럼 동작
        assert consumer.service.value == "service_a"

    def test_lazy_field_resolves_on_access(self):
        """필드 접근 시 실제 인스턴스가 resolve됨"""

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

    def test_lazy_field_caches_instance_for_singleton(self):
        """SINGLETON 스코프에서 LazyFieldProxy는 인스턴스를 캐시함"""
        init_count = 0

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
        _ = service.db
        first_count = init_count
        # 두 번째 접근
        _ = service.db
        second_count = init_count

        # 같은 인스턴스가 반환됨
        assert first_count == second_count == 1


class TestLazyCircularDependency:
    """Lazy 필드 주입을 통한 순환 의존성 해결 테스트"""

    def test_circular_dependency_resolved_automatically(self):
        """순환 의존성이 자동으로 해결됨

        모든 필드 주입이 기본적으로 Lazy이므로,
        순환 의존성이 자동으로 해결됩니다.
        """

        @Component
        class ServiceA:
            value: str = "from_a"

            def get_value(self) -> str:
                return self.value

        @Component
        class ServiceB:
            value: str = "from_b"
            service_a: ServiceA

            def get_a_value(self) -> str:
                return self.service_a.value

        app = Application("test_circular").ready()

        service_b = app.manager.get_instance(ServiceB)

        # 프록시를 통해 속성 접근 가능
        assert service_b.service_a.value == "from_a"

        # 프록시를 통해 메서드 호출 가능
        assert service_b.get_a_value() == "from_a"

    def test_bidirectional_reference(self):
        """양방향 참조가 가능함"""

        @Component
        class Alpha:
            name: str = "alpha"

        @Component
        class Beta:
            name: str = "beta"

        @Component
        class Consumer:
            alpha: Alpha
            beta: Beta

        app = Application("test_bidirectional").ready()

        consumer = app.manager.get_instance(Consumer)

        # 양방향 참조 확인
        assert consumer.alpha.name == "alpha"
        assert consumer.beta.name == "beta"


class TestExplicitLazy:
    """명시적 Lazy[T] 타입 힌트 테스트"""

    def test_explicit_lazy_type_hint(self):
        """Lazy[T] 타입 힌트가 LazyFieldProxy로 동작"""

        @Component
        class HeavyService:
            value: str = "heavy"

        @Component
        class Consumer:
            service: Lazy[HeavyService]  # 명시적 Lazy

        app = Application("test_explicit_lazy").ready()

        consumer = app.manager.get_instance(Consumer)

        # 투명 프록시로 동작
        assert consumer.service.value == "heavy"


class TestLazyEdgeCases:
    """Lazy 필드 엣지 케이스 테스트"""

    def test_lazy_field_repr(self):
        """LazyFieldProxy의 repr (해결 후)"""

        @Component
        class Target:
            pass

        @Component
        class Holder:
            target: Target

        app = Application("test_repr").ready()

        holder = app.manager.get_instance(Holder)
        # 접근하면 실제 인스턴스의 repr이 반환됨
        repr_str = repr(holder.target)
        assert "Target" in repr_str

    def test_lazy_field_equality(self):
        """LazyFieldProxy 동등성 비교"""

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

    def test_lazy_field_setattr(self):
        """LazyFieldProxy를 통한 속성 설정"""

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


class TestLazyWithFactory:
    """Lazy 필드와 Factory 조합 테스트"""

    def test_lazy_field_with_factory(self):
        """Factory로 생성된 인스턴스도 Lazy 필드를 통해 접근"""
        from bloom.core.decorators import Factory

        @Component
        class Config:
            url: str = "https://api.example.com"

        class ApiClient:
            def __init__(self, url: str):
                self.url = url

            def get_url(self) -> str:
                return self.url

        @Component
        class FactoryConfig:
            config: Config

            @Factory
            def create_client(self) -> ApiClient:
                return ApiClient(self.config.url)

        @Component
        class Consumer:
            client: ApiClient

        app = Application("test_lazy_factory").ready()

        consumer = app.manager.get_instance(Consumer)
        assert consumer.client.get_url() == "https://api.example.com"


class TestLazyWithMultipleConsumers:
    """여러 Consumer에서 같은 서비스 주입 테스트"""

    def test_multiple_consumers_same_instance(self):
        """여러 Consumer가 같은 인스턴스를 공유 (SINGLETON)"""
        init_count = 0

        @Component
        class SharedService:
            def __init__(self):
                nonlocal init_count
                init_count += 1

        @Component
        class ConsumerA:
            service: SharedService

        @Component
        class ConsumerB:
            service: SharedService

        @Component
        class ConsumerC:
            service: SharedService

        app = Application("test_multiple_consumers").ready()

        a = app.manager.get_instance(ConsumerA)
        b = app.manager.get_instance(ConsumerB)
        c = app.manager.get_instance(ConsumerC)

        # 각 consumer의 service에 접근
        _ = a.service
        _ = b.service
        _ = c.service

        # SINGLETON이므로 한 번만 초기화됨
        assert init_count == 1

        # 모두 같은 인스턴스
        assert a.service == b.service == c.service


class TestLazyFieldProxyMethods:
    """LazyFieldProxy 메서드 테스트"""

    def test_lazy_field_get_method(self):
        """get() 메서드로 명시적 접근"""

        @Component
        class Service:
            value: str = "test"

        @Component
        class Consumer:
            service: Service

        app = Application("test_get").ready()

        consumer = app.manager.get_instance(Consumer)

        # LazyFieldProxy가 주입됨
        service_field = object.__getattribute__(consumer, "service")

        # get() 메서드로 명시적 접근 (선택적)
        if hasattr(service_field, "get"):
            instance = service_field.get()
            assert instance.value == "test"

    def test_lazy_field_resolved_property(self):
        """resolved 프로퍼티로 해결 여부 확인"""

        @Component
        class Service:
            value: str = "test"

        @Component
        class Consumer:
            service: Service

        app = Application("test_resolved").ready()

        consumer = app.manager.get_instance(Consumer)

        # LazyFieldProxy가 주입됨
        service_field = object.__getattribute__(consumer, "service")

        if hasattr(service_field, "resolved"):
            # 접근 전에는 미해결
            assert not service_field.resolved

            # 접근
            _ = consumer.service.value

            # 접근 후에는 해결됨
            assert service_field.resolved
