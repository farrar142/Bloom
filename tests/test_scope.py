"""Scope 기능 테스트"""

import pytest
from bloom import Application, Component
from bloom.core import Scope, ScopeEnum


class TestScopeSingleton:
    """SINGLETON Scope 테스트 (기본값)"""

    def test_singleton_returns_same_instance(self):
        """SINGLETON은 항상 같은 인스턴스를 반환"""

        @Component
        class SingletonService:
            counter: int = 0

            def increment(self) -> int:
                self.counter += 1
                return self.counter

        @Component
        class Consumer:
            service: SingletonService

        app = Application("test_singleton").ready()

        consumer1 = app.manager.get_instance(Consumer)
        consumer2 = app.manager.get_instance(Consumer)

        # 같은 서비스 인스턴스 공유
        consumer1.service.increment()
        assert consumer2.service.counter == 1

    def test_singleton_is_default(self):
        """Scope를 지정하지 않으면 SINGLETON"""
        instance_count = 0

        @Component
        class DefaultService:
            def __init__(self):
                nonlocal instance_count
                instance_count += 1
                self.id = instance_count

        @Component
        class Consumer1:
            service: DefaultService

        @Component
        class Consumer2:
            service: DefaultService

        app = Application("test_default").ready()

        c1 = app.manager.get_instance(Consumer1)
        c2 = app.manager.get_instance(Consumer2)

        # SINGLETON이므로 한 번만 생성, 같은 ID
        assert c1.service.id == c2.service.id == 1
        assert instance_count == 1


class TestScopePrototype:
    """PROTOTYPE Scope 테스트"""

    def test_prototype_creates_new_instance_each_access(self):
        """PROTOTYPE은 접근할 때마다 새 인스턴스 생성"""
        instance_count = 0

        @Component
        @Scope(ScopeEnum.PROTOTYPE)
        class PrototypeService:
            def __init__(self):
                nonlocal instance_count
                instance_count += 1
                self.instance_id = instance_count

        @Component
        class Consumer:
            service: PrototypeService

        app = Application("test_prototype").ready()

        consumer = app.manager.get_instance(Consumer)

        # 첫 번째 접근
        first_id = consumer.service.instance_id
        # 두 번째 접근 - 새 인스턴스
        second_id = consumer.service.instance_id
        # 세 번째 접근 - 또 새 인스턴스
        third_id = consumer.service.instance_id

        # 모두 다른 인스턴스
        assert first_id != second_id
        assert second_id != third_id
        assert instance_count == 3

    def test_prototype_with_multiple_consumers(self):
        """여러 Consumer에서 PROTOTYPE 사용"""
        instance_count = 0

        @Component
        @Scope(ScopeEnum.PROTOTYPE)
        class RequestHandler:
            def __init__(self):
                nonlocal instance_count
                instance_count += 1
                self.id = instance_count

        @Component
        class ServiceA:
            handler: RequestHandler

        @Component
        class ServiceB:
            handler: RequestHandler

        app = Application("test_prototype_multi").ready()

        a = app.manager.get_instance(ServiceA)
        b = app.manager.get_instance(ServiceB)

        # 각각 접근할 때마다 새 인스턴스
        a_id1 = a.handler.id
        b_id1 = b.handler.id
        a_id2 = a.handler.id

        assert a_id1 != b_id1
        assert a_id1 != a_id2


class TestScopeMixed:
    """혼합 Scope 테스트"""

    def test_singleton_with_prototype_dependency(self):
        """SINGLETON이 PROTOTYPE을 의존"""
        proto_count = 0

        @Component
        @Scope(ScopeEnum.PROTOTYPE)
        class PrototypeLogger:
            def __init__(self):
                nonlocal proto_count
                proto_count += 1
                self.id = proto_count

        @Component
        class SingletonService:
            logger: PrototypeLogger

            def get_logger_id(self) -> int:
                return self.logger.id

        app = Application("test_mixed").ready()

        service = app.manager.get_instance(SingletonService)

        # PROTOTYPE이므로 매번 새 인스턴스
        id1 = service.get_logger_id()
        id2 = service.get_logger_id()
        id3 = service.get_logger_id()

        assert id1 != id2 != id3
        assert proto_count == 3

    def test_prototype_with_singleton_dependency(self):
        """PROTOTYPE이 SINGLETON을 의존"""
        singleton_count = 0

        @Component
        class SingletonCounter:
            def __init__(self):
                nonlocal singleton_count
                singleton_count += 1
                self.count = 0

            def increment(self) -> int:
                self.count += 1
                return self.count

        @Component
        @Scope(ScopeEnum.PROTOTYPE)
        class PrototypeWorker:
            counter: SingletonCounter

            def work(self) -> int:
                return self.counter.increment()

        @Component
        class Consumer:
            worker: PrototypeWorker

        app = Application("test_proto_singleton").ready()

        consumer = app.manager.get_instance(Consumer)

        # PROTOTYPE worker지만 SINGLETON counter는 공유
        result1 = consumer.worker.work()
        result2 = consumer.worker.work()
        result3 = consumer.worker.work()

        # counter는 SINGLETON이므로 값이 누적
        assert result1 == 1
        assert result2 == 2
        assert result3 == 3
        # SINGLETON은 한 번만 생성
        assert singleton_count == 1


class TestPrototypeLifecycleWithEvents:
    """PROTOTYPE 라이프사이클 자동 정리 테스트"""

    def test_prototype_pre_destroy_auto_called_on_method_exit(self):
        """메서드 종료 시 PROTOTYPE의 @PreDestroy 자동 호출"""
        from bloom.core.decorators import PostConstruct, PreDestroy, Factory
        from bloom.core.advice import MethodAdviceRegistry, MethodAdvice
        from bloom.core.advice.tracing import CallStackTraceAdvice

        destroyed = []
        created = []

        @Component
        @Scope(ScopeEnum.PROTOTYPE)
        class ManagedResource:
            resource_id: int = 0

            @PostConstruct
            def init(self):
                self.resource_id = id(self)
                created.append(self.resource_id)

            @PreDestroy
            def cleanup(self):
                destroyed.append(self.resource_id)

        @Component
        class TracingAdvice(CallStackTraceAdvice):
            """콜스택 추적 활성화 (PROTOTYPE 자동 정리 트리거)"""

            pass

        @Component
        class AdviceConfig:
            @Factory
            def advice_registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                for advice in advices:
                    registry.register(advice)
                return registry

        @Component
        class Consumer:
            resource: ManagedResource

            def use_resource(self) -> int:
                """이 메서드 종료 시 resource의 @PreDestroy 자동 호출"""
                return self.resource.resource_id

        app = Application("test_prototype_auto_destroy")
        app.scan(ManagedResource)
        app.scan(TracingAdvice)
        app.scan(AdviceConfig)
        app.scan(Consumer)
        app.ready()

        consumer = app.manager.get_instance(Consumer)

        # 메서드 호출 - 내부에서 PROTOTYPE 생성, 종료 시 자동 정리
        result1 = consumer.use_resource()
        result2 = consumer.use_resource()
        result3 = consumer.use_resource()

        # 3개 생성됨
        assert len(created) == 3
        # 메서드 종료 시마다 @PreDestroy 호출됨
        assert len(destroyed) == 3
        assert result1 in destroyed
        assert result2 in destroyed
        assert result3 in destroyed

    def test_prototype_lifecycle_manager_manual_destroy(self):
        """LifecycleManager로 수동으로 @PreDestroy 호출"""
        from bloom.core.decorators import PostConstruct, PreDestroy

        destroyed = []

        @Component
        @Scope(ScopeEnum.PROTOTYPE)
        class ManagedResource:
            resource_id: int = 0

            @PostConstruct
            def init(self):
                self.resource_id = id(self)

            @PreDestroy
            def cleanup(self):
                destroyed.append(self.resource_id)

        app = Application("test_prototype_manual_destroy")
        app.scan(ManagedResource)
        app.ready()

        # 직접 컨테이너에서 인스턴스 생성 (콜스택 외부)
        container = app.manager.get_container(ManagedResource)
        assert container is not None

        instance = container._create_instance()
        app.manager.lifecycle.invoke_prototype_post_construct(instance, container)

        assert len(destroyed) == 0

        # 수동으로 PreDestroy 호출
        app.manager.lifecycle.invoke_prototype_pre_destroy(instance, container)

        assert len(destroyed) == 1
        assert instance.resource_id in destroyed
