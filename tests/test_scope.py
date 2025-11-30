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
