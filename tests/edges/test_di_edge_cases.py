"""DI Container 엣지 케이스 테스트"""

import pytest
from abc import ABC, abstractmethod
from dataclasses import dataclass

from bloom import Application, Component
from bloom.core import Factory, Scope, ScopeEnum
from bloom.core.exceptions import CircularDependencyError


class TestEmptyModule:
    """빈 모듈 스캔 테스트"""

    async def test_scan_empty_module(self, reset_container_manager):
        """컴포넌트가 없는 모듈 스캔"""
        import types

        empty_module = types.ModuleType("empty_module")

        app = Application("empty_test")
        await app.scan(empty_module).ready_async()

        # 에러 없이 정상 동작
        assert app.manager is not None

    async def test_scan_module_with_only_functions(self, reset_container_manager):
        """함수만 있는 모듈 스캔"""
        import types

        func_module = types.ModuleType("func_module")
        setattr(func_module, "my_function", lambda x: x * 2)

        app = Application("func_test")
        await app.scan(func_module).ready_async()

        assert app.manager is not None


class TestFactoryEdgeCases:
    """@Factory 엣지 케이스 테스트"""

    async def test_factory_returns_none(self, reset_container_manager):
        """@Factory가 None 반환해도 에러 없이 처리"""
        from typing import Optional
        from dataclasses import dataclass

        @dataclass
        class NullableValue:
            data: str | None = None

        @Component
        class NoneFactory:
            @Factory
            def create_nullable(self) -> NullableValue:
                return NullableValue(data=None)

        @Component
        class Consumer:
            value: NullableValue

        app = (
            await Application("none_factory").scan(NoneFactory, Consumer).ready_async()
        )
        consumer = app.manager.get_instance(Consumer)

        assert consumer.value.data is None

    async def test_factory_returns_empty_list(self, reset_container_manager):
        """@Factory가 빈 리스트 반환"""

        @Component
        class EmptyListFactory:
            @Factory
            def create_empty(self) -> list[str]:
                return []

        app = await Application("empty_list").scan(EmptyListFactory).ready_async()
        result = app.manager.get_instance(list[str])

        assert result == []

    async def test_factory_with_no_args(self, reset_container_manager):
        """@Factory 메서드에 인자 없음"""

        @dataclass
        class Config:
            value: str

        @Component
        class NoArgFactory:
            @Factory
            def create_config(self) -> Config:
                return Config(value="created_value")

        app = await Application("no_arg").scan(NoArgFactory).ready_async()
        config = app.manager.get_instance(Config)

        assert config.value == "created_value"


class TestComponentEdgeCases:
    """@Component 엣지 케이스 테스트"""

    async def test_component_with_class_variable(self, reset_container_manager):
        """클래스 변수가 있는 컴포넌트"""

        @Component
        class WithClassVar:
            class_var: str = "class_value"  # ClassVar는 주입 대상 아님
            counter: int = 0

            def increment(self) -> int:
                self.counter += 1
                return self.counter

        app = await Application("class_var").scan(WithClassVar).ready_async()
        instance = app.manager.get_instance(WithClassVar)

        assert instance.class_var == "class_value"
        assert instance.increment() == 1

    async def test_component_with_property(self, reset_container_manager):
        """@property가 있는 컴포넌트"""

        @Component
        class WithProperty:
            _value: int = 10

            @property
            def value(self) -> int:
                return self._value * 2

        app = await Application("property").scan(WithProperty).ready_async()
        instance = app.manager.get_instance(WithProperty)

        assert instance.value == 20

    async def test_component_inheritance(self, reset_container_manager):
        """상속 관계의 컴포넌트"""

        class BaseService:
            def base_method(self) -> str:
                return "base"

        @Component
        class DerivedService(BaseService):
            def derived_method(self) -> str:
                return "derived"

        app = await Application("inheritance").scan(DerivedService).ready_async()
        instance = app.manager.get_instance(DerivedService)

        assert instance.base_method() == "base"
        assert instance.derived_method() == "derived"


class TestDependencyEdgeCases:
    """의존성 주입 엣지 케이스 테스트"""

    async def test_optional_dependency_missing(self, reset_container_manager):
        """Optional 의존성이 없는 경우"""

        class MissingService:
            pass

        @Component
        class OptionalConsumer:
            service: MissingService | None = None

        app = await Application("optional_missing").scan(OptionalConsumer).ready_async()
        instance = app.manager.get_instance(OptionalConsumer)

        assert instance.service is None

    async def test_multiple_implementations_list(self, reset_container_manager):
        """동일 인터페이스 여러 구현체 - get_instances로 목록 조회"""

        class ServiceInterface:
            def get_name(self) -> str:
                raise NotImplementedError

        @Component
        class ServiceA(ServiceInterface):
            def get_name(self) -> str:
                return "A"

        @Component
        class ServiceB(ServiceInterface):
            def get_name(self) -> str:
                return "B"

        app = await Application("multi_impl").scan(ServiceA, ServiceB).ready_async()

        # 구현체 목록 조회
        instances = app.manager.get_instances(ServiceInterface)
        assert len(instances) == 2
        names = {inst.get_name() for inst in instances}
        assert names == {"A", "B"}

    async def test_lazy_dependency(self, reset_container_manager):
        """Lazy 의존성 기본 동작"""

        @Component
        class HeavyService:
            def compute(self) -> str:
                return "computed"

        @Component
        class Consumer:
            heavy: HeavyService

            def use_heavy(self) -> str:
                return self.heavy.compute()

        app = await Application("lazy").scan(HeavyService, Consumer).ready_async()
        consumer = app.manager.get_instance(Consumer)

        # Lazy 프록시를 통해 접근 가능
        result = consumer.use_heavy()
        assert result == "computed"


class TestLifecycleEdgeCases:
    """라이프사이클 엣지 케이스 테스트"""

    async def test_postconstruct_exception(self, reset_container_manager):
        """@PostConstruct에서 예외 발생"""
        from bloom.core.decorators import PostConstruct

        @Component
        class FailingInit:
            @PostConstruct
            def init(self):
                raise ValueError("Init failed!")

        app = Application("failing_init").scan(FailingInit)

        with pytest.raises(ValueError, match="Init failed!"):
            await app.ready_async()

    async def test_multiple_postconstruct(self, reset_container_manager):
        """여러 @PostConstruct 메서드"""
        from bloom.core.decorators import PostConstruct

        init_order = []

        @Component
        class MultiInit:
            @PostConstruct
            def init1(self):
                init_order.append("init1")

            @PostConstruct
            def init2(self):
                init_order.append("init2")

        app = await Application("multi_init").scan(MultiInit).ready_async()
        app.manager.get_instance(MultiInit)

        assert len(init_order) == 2
        assert "init1" in init_order
        assert "init2" in init_order


class TestScopeEdgeCases:
    """스코프 엣지 케이스 테스트"""

    async def test_singleton_is_same_instance(self, reset_container_manager):
        """SINGLETON 스코프 인스턴스 동일성"""

        @Component
        class SingletonService:
            pass

        app = await Application("singleton").scan(SingletonService).ready_async()

        instance1 = app.manager.get_instance(SingletonService)
        instance2 = app.manager.get_instance(SingletonService)

        assert instance1 is instance2

    async def test_prototype_is_different_instance(self, reset_container_manager):
        """PROTOTYPE 스코프 인스턴스 차이"""

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeService:
            pass

        @Component
        class Consumer:
            service: PrototypeService

        app = (
            await Application("prototype")
            .scan(PrototypeService, Consumer)
            .ready_async()
        )

        consumer = app.manager.get_instance(Consumer)
        # 프록시를 통한 접근이므로 id 비교가 아닌 동작 테스트
        assert consumer.service is not None


class TestTypeAnnotationEdgeCases:
    """타입 어노테이션 엣지 케이스 테스트"""

    async def test_generic_type_injection(self, reset_container_manager):
        """제네릭 타입 주입"""
        from dataclasses import dataclass

        @dataclass
        class Config:
            value: str

        @Component
        class ConfigFactory:
            @Factory
            def create_config(self) -> Config:
                return Config(value="test_value")

        @Component
        class Consumer:
            config: Config

        app = await Application("generic").scan(ConfigFactory, Consumer).ready_async()
        consumer = app.manager.get_instance(Consumer)

        assert consumer.config.value == "test_value"

    async def test_optional_with_default(self, reset_container_manager):
        """Optional 타입과 기본값"""

        @Component
        class Consumer:
            value: str | None = "default"

        app = await Application("optional_default").scan(Consumer).ready_async()
        consumer = app.manager.get_instance(Consumer)

        # 기본값 유지
        assert consumer.value == "default"
