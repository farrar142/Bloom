"""Scope 기능 테스트"""

import pytest
from bloom import Application, Component
from bloom.core import Scope, ScopeEnum


class TestScopeSingleton:
    """SINGLETON Scope 테스트 (기본값)"""

    async def test_singleton_returns_same_instance(self):
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

        app = await Application("test_singleton").ready_async()

        consumer1 = app.manager.get_instance(Consumer)
        consumer2 = app.manager.get_instance(Consumer)

        # 같은 서비스 인스턴스 공유
        consumer1.service.increment()
        assert consumer2.service.counter == 1

    async def test_singleton_is_default(self):
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

        app = await Application("test_default").ready_async()

        c1 = app.manager.get_instance(Consumer1)
        c2 = app.manager.get_instance(Consumer2)

        # SINGLETON이므로 한 번만 생성, 같은 ID
        assert c1.service.id == c2.service.id == 1
        assert instance_count == 1


class TestScopePrototype:
    """PROTOTYPE Scope 테스트"""

    async def test_prototype_creates_new_instance_each_access(self):
        """PROTOTYPE은 접근할 때마다 새 인스턴스 생성"""
        instance_count = 0

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeService:
            def __init__(self):
                nonlocal instance_count
                instance_count += 1
                self.instance_id = instance_count

        @Component
        class Consumer:
            service: PrototypeService

        app = await Application("test_prototype").ready_async()

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

    async def test_prototype_with_multiple_consumers(self):
        """여러 Consumer에서 PROTOTYPE 사용"""
        instance_count = 0

        @Component
        @Scope(ScopeEnum.CALL)
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

        app = await Application("test_prototype_multi").ready_async()

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

    async def test_singleton_with_prototype_dependency(self):
        """SINGLETON이 PROTOTYPE을 의존"""
        proto_count = 0

        @Component
        @Scope(ScopeEnum.CALL)
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

        app = await Application("test_mixed").ready_async()

        service = app.manager.get_instance(SingletonService)

        # PROTOTYPE이므로 매번 새 인스턴스
        id1 = service.get_logger_id()
        id2 = service.get_logger_id()
        id3 = service.get_logger_id()

        assert id1 != id2 != id3
        assert proto_count == 3

    async def test_prototype_with_singleton_dependency(self):
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
        @Scope(ScopeEnum.CALL)
        class PrototypeWorker:
            counter: SingletonCounter

            def work(self) -> int:
                return self.counter.increment()

        @Component
        class Consumer:
            worker: PrototypeWorker

        app = await Application("test_proto_singleton").ready_async()

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

    async def test_prototype_pre_destroy_auto_called_on_method_exit(self):
        """메서드 종료 시 PROTOTYPE의 @PreDestroy 자동 호출"""
        from bloom.core.decorators import PostConstruct, PreDestroy, Factory
        from bloom.core.advice import MethodAdviceRegistry, MethodAdvice
        from bloom.core.advice.tracing import CallStackTraceAdvice

        destroyed = []
        created = []

        @Component
        @Scope(ScopeEnum.CALL)
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
        await app.ready_async()

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

    async def test_prototype_lifecycle_manager_manual_destroy(self):
        """LifecycleManager로 수동으로 @PreDestroy 호출"""
        from bloom.core.decorators import PostConstruct, PreDestroy

        destroyed = []

        @Component
        @Scope(ScopeEnum.CALL)
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
        await app.ready_async()

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


class TestCallScopedPrototype:
    """CALL_SCOPED PROTOTYPE 테스트

    CALL_SCOPED가 동작하려면 CallStackTraceAdvice가 필요합니다.
    """

    async def test_call_scoped_returns_same_instance_in_handler(self):
        """CALL_SCOPED는 같은 핸들러 호출 내에서 같은 인스턴스 반환"""
        from bloom.core.container.element import PrototypeMode
        from bloom.core.decorators import Handler, Factory
        from bloom.core.advice import MethodAdvice, MethodAdviceRegistry
        from bloom.core.advice.tracing import CallStackTraceAdvice

        instance_count = 0

        @Component
        @Scope(ScopeEnum.CALL, mode=PrototypeMode.CALL_SCOPED)
        class ScopedResource:
            def __init__(self):
                nonlocal instance_count
                instance_count += 1
                self.instance_id = instance_count

        @Component
        class TracingAdvice(CallStackTraceAdvice):
            pass

        @Component
        class AdviceConfig:
            @Factory
            def registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
                reg = MethodAdviceRegistry()
                for a in advices:
                    reg.register(a)
                return reg

        @Component
        class Service:
            resource: ScopedResource

            @Handler
            def do_work(self) -> list[int]:
                """핸들러 내에서 여러 번 접근"""
                ids = []
                # 3번 접근해도 같은 인스턴스
                ids.append(self.resource.instance_id)
                ids.append(self.resource.instance_id)
                ids.append(self.resource.instance_id)
                return ids

        app = Application("test_call_scoped")
        app.scan(ScopedResource, TracingAdvice, AdviceConfig, Service)
        await app.ready_async()

        service = app.manager.get_instance(Service)

        # 첫 번째 핸들러 호출
        first_call_ids = service.do_work()
        # 모두 같은 ID
        assert first_call_ids[0] == first_call_ids[1] == first_call_ids[2]
        first_id = first_call_ids[0]

        # 두 번째 핸들러 호출 - 새로운 인스턴스
        second_call_ids = service.do_work()
        assert second_call_ids[0] == second_call_ids[1] == second_call_ids[2]
        second_id = second_call_ids[0]

        # 다른 호출이므로 다른 인스턴스
        assert first_id != second_id
        # 총 2개의 인스턴스 생성
        assert instance_count == 2

    async def test_call_scoped_different_consumers_same_instance(self):
        """같은 핸들러 내 여러 Consumer에서도 같은 CALL_SCOPED 인스턴스"""
        from bloom.core.container.element import PrototypeMode
        from bloom.core.decorators import Handler, Factory
        from bloom.core.advice import MethodAdvice, MethodAdviceRegistry
        from bloom.core.advice.tracing import CallStackTraceAdvice

        instance_count = 0

        @Component
        @Scope(ScopeEnum.CALL, mode=PrototypeMode.CALL_SCOPED)
        class SharedResource:
            def __init__(self):
                nonlocal instance_count
                instance_count += 1
                self.instance_id = instance_count

        @Component
        class TracingAdvice(CallStackTraceAdvice):
            pass

        @Component
        class AdviceConfig:
            @Factory
            def registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
                reg = MethodAdviceRegistry()
                for a in advices:
                    reg.register(a)
                return reg

        @Component
        class HelperService:
            resource: SharedResource

            def get_resource_id(self) -> int:
                return self.resource.instance_id

        @Component
        class MainService:
            resource: SharedResource
            helper: HelperService

            @Handler
            def do_work(self) -> tuple[int, int]:
                """메인과 헬퍼에서 같은 리소스 공유"""
                main_id = self.resource.instance_id
                helper_id = self.helper.get_resource_id()
                return main_id, helper_id

        app = Application("test_call_scoped_shared")
        app.scan(
            SharedResource, TracingAdvice, AdviceConfig, HelperService, MainService
        )
        await app.ready_async()

        main = app.manager.get_instance(MainService)

        main_id, helper_id = main.do_work()

        # 같은 핸들러 호출 내이므로 같은 인스턴스
        assert main_id == helper_id
        # 1개만 생성
        assert instance_count == 1

    async def test_call_scoped_vs_default_prototype(self):
        """CALL_SCOPED vs DEFAULT PROTOTYPE 비교"""
        from bloom.core.container.element import PrototypeMode
        from bloom.core.decorators import Handler, Factory
        from bloom.core.advice import MethodAdvice, MethodAdviceRegistry
        from bloom.core.advice.tracing import CallStackTraceAdvice

        scoped_count = 0
        default_count = 0

        @Component
        @Scope(ScopeEnum.CALL, mode=PrototypeMode.CALL_SCOPED)
        class ScopedService:
            def __init__(self):
                nonlocal scoped_count
                scoped_count += 1
                self.id = scoped_count

        @Component
        @Scope(ScopeEnum.CALL)  # DEFAULT
        class DefaultService:
            def __init__(self):
                nonlocal default_count
                default_count += 1
                self.id = default_count

        @Component
        class TracingAdvice(CallStackTraceAdvice):
            pass

        @Component
        class AdviceConfig:
            @Factory
            def registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
                reg = MethodAdviceRegistry()
                for a in advices:
                    reg.register(a)
                return reg

        @Component
        class Consumer:
            scoped: ScopedService
            default: DefaultService

            @Handler
            def get_ids(self) -> tuple[list[int], list[int]]:
                scoped_ids = [self.scoped.id, self.scoped.id, self.scoped.id]
                default_ids = [self.default.id, self.default.id, self.default.id]
                return scoped_ids, default_ids

        app = Application("test_comparison")
        app.scan(ScopedService, DefaultService, TracingAdvice, AdviceConfig, Consumer)
        await app.ready_async()

        consumer = app.manager.get_instance(Consumer)

        scoped_ids, default_ids = consumer.get_ids()

        # CALL_SCOPED: 같은 호출 내 모두 같은 ID
        assert scoped_ids[0] == scoped_ids[1] == scoped_ids[2]
        assert scoped_count == 1

        # DEFAULT: 매번 다른 ID
        assert default_ids[0] != default_ids[1] != default_ids[2]
        assert default_count == 3
