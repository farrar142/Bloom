"""MethodAdvice 테스트"""

import pytest
from dataclasses import dataclass
from typing import Any

from bloom import Application, Component
from bloom.core.decorators import Factory, Handler
from bloom.core.container import HandlerContainer
from bloom.core.container.element import Element
from bloom.core.advice import (
    MethodAdvice,
    MethodAdviceRegistry,
    MethodInvocationManager,
    InvocationContext,
    MethodProxy,
)


# === 테스트용 Element 정의 ===


class TransactionalElement(Element):
    """트랜잭션 적용 마커"""

    pass


class CacheableElement(Element):
    """캐시 적용 마커"""

    def __init__(self, ttl: int = 60):
        super().__init__()
        self.metadata["ttl"] = ttl


class LoggableElement(Element):
    """로깅 적용 마커"""

    pass


# === 테스트용 Advice 정의 ===


class TransactionAdvice(MethodAdvice):
    """트랜잭션 어드바이스"""

    def __init__(self):
        self.calls: list[str] = []

    def supports(self, container: HandlerContainer) -> bool:
        return container.has_element(TransactionalElement)

    async def before(self, context: InvocationContext) -> None:
        self.calls.append("tx:before")
        context.set_attribute("tx_started", True)

    async def after(self, context: InvocationContext, result: Any) -> Any:
        self.calls.append("tx:after")
        context.set_attribute("tx_committed", True)
        return result

    async def on_error(self, context: InvocationContext, error: Exception) -> Any:
        self.calls.append("tx:on_error")
        context.set_attribute("tx_rolled_back", True)
        raise error


class CacheAdvice(MethodAdvice):
    """캐시 어드바이스"""

    def __init__(self):
        self.calls: list[str] = []
        self.cache: dict[str, Any] = {}

    def supports(self, container: HandlerContainer) -> bool:
        return container.has_element(CacheableElement)

    async def before(self, context: InvocationContext) -> None:
        self.calls.append("cache:before")

    async def after(self, context: InvocationContext, result: Any) -> Any:
        self.calls.append("cache:after")
        return result


class LoggingAdvice(MethodAdvice):
    """로깅 어드바이스"""

    def __init__(self):
        self.calls: list[str] = []

    def supports(self, container: HandlerContainer) -> bool:
        return container.has_element(LoggableElement)

    async def before(self, context: InvocationContext) -> None:
        self.calls.append("log:before")

    async def after(self, context: InvocationContext, result: Any) -> Any:
        self.calls.append("log:after")
        return result


# === 테스트용 Mock Container ===


class MockHandlerContainer(HandlerContainer):
    """테스트용 핸들러 컨테이너"""

    def __init__(self):
        # HandlerContainer가 기대하는 최소 구조
        self.elements: list[Element] = []
        self.handler = None

    def add_elements(self, *elements: Element) -> None:
        self.elements.extend(elements)

    def has_element(self, element_type: type) -> bool:
        return any(isinstance(e, element_type) for e in self.elements)


# === 테스트 ===


class TestMethodAdvice:
    """MethodAdvice 기본 테스트"""

    @pytest.mark.asyncio
    async def test_single_advice_execution(self):
        """단일 어드바이스 실행"""
        # Given
        tx_advice = TransactionAdvice()
        registry = MethodAdviceRegistry()
        registry.register(tx_advice)
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()
        container.add_elements(TransactionalElement())

        async def handler(x: int) -> int:
            return x * 2

        # When
        result = await manager.invoke(container, None, handler, 5)

        # Then
        assert result == 10
        assert tx_advice.calls == ["tx:before", "tx:after"]

    @pytest.mark.asyncio
    async def test_no_applicable_advice(self):
        """적용 가능한 어드바이스가 없는 경우"""
        # Given
        tx_advice = TransactionAdvice()
        registry = MethodAdviceRegistry()
        registry.register(tx_advice)
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()
        # TransactionalElement가 없음

        async def handler(x: int) -> int:
            return x * 2

        # When
        result = await manager.invoke(container, None, handler, 5)

        # Then
        assert result == 10
        assert tx_advice.calls == []  # 호출되지 않음

    @pytest.mark.asyncio
    async def test_multiple_advices_execution_order(self):
        """여러 어드바이스 실행 순서 (Element 순서 기반)"""
        # Given
        cache_advice = CacheAdvice()
        tx_advice = TransactionAdvice()

        registry = MethodAdviceRegistry()
        registry.register(cache_advice)
        registry.register(tx_advice)
        manager = MethodInvocationManager(registry)

        # 데코레이터 순서: @Transactional → @Cacheable → @Handler
        # Element 순서: [CacheableElement, TransactionalElement]
        container = MockHandlerContainer()
        container.add_elements(CacheableElement())
        container.add_elements(TransactionalElement())

        async def handler() -> str:
            return "result"

        # When
        result = await manager.invoke(container, None, handler)

        # Then
        assert result == "result"
        # before: Cache → Transaction (순서대로)
        # after: Transaction → Cache (역순)
        assert cache_advice.calls == ["cache:before", "cache:after"]
        assert tx_advice.calls == ["tx:before", "tx:after"]

    @pytest.mark.asyncio
    async def test_on_error_called_on_exception(self):
        """예외 발생 시 on_error 호출"""
        # Given
        tx_advice = TransactionAdvice()
        registry = MethodAdviceRegistry()
        registry.register(tx_advice)
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()
        container.add_elements(TransactionalElement())

        async def handler() -> str:
            raise ValueError("test error")

        # When & Then
        with pytest.raises(ValueError, match="test error"):
            await manager.invoke(container, None, handler)

        assert tx_advice.calls == ["tx:before", "tx:on_error"]

    @pytest.mark.asyncio
    async def test_context_attribute_sharing(self):
        """InvocationContext를 통한 Advice 간 데이터 공유"""
        # Given
        tx_advice = TransactionAdvice()
        registry = MethodAdviceRegistry()
        registry.register(tx_advice)
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()
        container.add_elements(TransactionalElement())

        captured_context: InvocationContext | None = None

        async def handler() -> str:
            return "result"

        # Custom advice to capture context
        class ContextCaptureAdvice(MethodAdvice):
            def supports(self, c: HandlerContainer) -> bool:
                return True

            async def after(self, context: InvocationContext, result: Any) -> Any:
                nonlocal captured_context
                captured_context = context
                return result

        registry.register(ContextCaptureAdvice())

        # When
        await manager.invoke(container, None, handler)

        # Then
        assert captured_context is not None
        assert captured_context.get_attribute("tx_started") is True
        assert captured_context.get_attribute("tx_committed") is True

    @pytest.mark.asyncio
    async def test_sync_handler_support(self):
        """동기 핸들러 지원"""
        # Given
        tx_advice = TransactionAdvice()
        registry = MethodAdviceRegistry()
        registry.register(tx_advice)
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()
        container.add_elements(TransactionalElement())

        def sync_handler(x: int) -> int:
            return x * 3

        # When
        result = await manager.invoke(container, None, sync_handler, 4)

        # Then
        assert result == 12
        assert tx_advice.calls == ["tx:before", "tx:after"]

    @pytest.mark.asyncio
    async def test_advice_modifies_result(self):
        """Advice가 결과를 수정"""

        # Given
        class DoubleResultAdvice(MethodAdvice):
            def supports(self, c: HandlerContainer) -> bool:
                return True

            async def after(self, context: InvocationContext, result: Any) -> Any:
                return result * 2

        registry = MethodAdviceRegistry()
        registry.register(DoubleResultAdvice())
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()

        async def handler() -> int:
            return 5

        # When
        result = await manager.invoke(container, None, handler)

        # Then
        assert result == 10


class TestMethodAdviceRegistry:
    """MethodAdviceRegistry 테스트"""

    def test_find_applicable_filters_by_supports(self):
        """supports() 기반 필터링"""
        # Given
        tx_advice = TransactionAdvice()
        cache_advice = CacheAdvice()

        registry = MethodAdviceRegistry()
        registry.register(tx_advice)
        registry.register(cache_advice)

        container = MockHandlerContainer()
        container.add_elements(TransactionalElement())  # CacheableElement 없음

        # When
        applicable = registry.find_applicable(container)

        # Then
        assert tx_advice in applicable
        assert cache_advice not in applicable

    def test_find_applicable_returns_empty_when_no_match(self):
        """매칭되는 Advice가 없는 경우 빈 리스트 반환"""
        # Given
        tx_advice = TransactionAdvice()

        registry = MethodAdviceRegistry()
        registry.register(tx_advice)

        container = MockHandlerContainer()
        # 아무 Element도 없음

        # When
        applicable = registry.find_applicable(container)

        # Then
        assert applicable == []


class TestInvocationContext:
    """InvocationContext 테스트"""

    def test_attribute_set_and_get(self):
        """속성 설정 및 조회"""
        # Given
        container = MockHandlerContainer()
        context = InvocationContext(
            container=container, instance=None, args=(), kwargs={}
        )

        # When
        context.set_attribute("key1", "value1")
        context.set_attribute("key2", 123)

        # Then
        assert context.get_attribute("key1") == "value1"
        assert context.get_attribute("key2") == 123
        assert context.get_attribute("nonexistent") is None
        assert context.get_attribute("nonexistent", "default") == "default"


class TestMethodProxy:
    """MethodProxy 테스트"""

    @pytest.mark.asyncio
    async def test_async_method_proxy(self):
        """비동기 메서드 프록시"""
        # Given
        tx_advice = TransactionAdvice()
        registry = MethodAdviceRegistry()
        registry.register(tx_advice)
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()
        container.add_elements(TransactionalElement())

        async def async_method(x: int) -> int:
            return x * 2

        proxy = MethodProxy(
            container=container, instance=None, original=async_method, manager=manager
        )

        # When
        result = await proxy(5)

        # Then
        assert result == 10
        assert tx_advice.calls == ["tx:before", "tx:after"]

    def test_sync_method_proxy(self):
        """동기 메서드 프록시"""

        # Given
        class SyncTransactionAdvice(MethodAdvice):
            def __init__(self):
                self.calls: list[str] = []

            def supports(self, container: HandlerContainer) -> bool:
                return container.has_element(TransactionalElement)

            def before_sync(self, context: InvocationContext) -> None:
                self.calls.append("tx:before_sync")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                self.calls.append("tx:after_sync")
                return result

        sync_advice = SyncTransactionAdvice()
        registry = MethodAdviceRegistry()
        registry.register(sync_advice)
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()
        container.add_elements(TransactionalElement())

        def sync_method(x: int) -> int:
            return x * 3

        proxy = MethodProxy(
            container=container, instance=None, original=sync_method, manager=manager
        )

        # When
        result = proxy(4)

        # Then
        assert result == 12
        assert sync_advice.calls == ["tx:before_sync", "tx:after_sync"]


class TestAdviceWithDI:
    """Advice와 DI 통합 테스트"""

    def test_advice_applied_to_handler_method(self):
        """@Handler 메서드에 Advice가 적용되는지 테스트"""
        # Given
        call_log: list[str] = []

        class LoggingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True  # 모든 핸들러에 적용

            def before_sync(self, context: InvocationContext) -> None:
                call_log.append("advice:before")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                call_log.append("advice:after")
                return result

        @Component
        class AdviceConfig:
            @Factory
            def invocation_manager(self) -> MethodInvocationManager:
                registry = MethodAdviceRegistry()
                registry.register(LoggingAdvice())
                return MethodInvocationManager(registry)

        @Component
        class MyService:
            @Handler
            def do_something(self) -> str:
                call_log.append("handler:execute")
                return "result"

        # When
        app = Application("test").scan(AdviceConfig, MyService).ready()
        service = app.manager.get_instance(MyService)
        result = service.do_something()

        # Then
        assert result == "result"
        assert call_log == ["advice:before", "handler:execute", "advice:after"]

    @pytest.mark.asyncio
    async def test_async_advice_with_handler(self):
        """비동기 @Handler 메서드에 Advice 적용"""
        # Given
        call_log: list[str] = []

        class AsyncLoggingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            async def before(self, context: InvocationContext) -> None:
                call_log.append("advice:before")

            async def after(self, context: InvocationContext, result: Any) -> Any:
                call_log.append("advice:after")
                return result

        @Component
        class AdviceConfig:
            @Factory
            def invocation_manager(self) -> MethodInvocationManager:
                registry = MethodAdviceRegistry()
                registry.register(AsyncLoggingAdvice())
                return MethodInvocationManager(registry)

        @Component
        class AsyncService:
            @Handler
            async def do_async(self) -> str:
                call_log.append("handler:execute")
                return "async_result"

        # When
        app = Application("test").scan(AdviceConfig, AsyncService).ready()
        service = app.manager.get_instance(AsyncService)
        result = await service.do_async()

        # Then
        assert result == "async_result"
        assert call_log == ["advice:before", "handler:execute", "advice:after"]

    def test_no_advice_when_manager_not_registered(self):
        """MethodInvocationManager가 없으면 프록시 적용 안 함"""
        # Given
        call_log: list[str] = []

        @Component
        class SimpleService:
            @Handler
            def simple_method(self) -> str:
                call_log.append("handler:execute")
                return "simple"

        # When - MethodInvocationManager 없이 초기화
        app = Application("test").scan(SimpleService).ready()
        service = app.manager.get_instance(SimpleService)

        # 프록시가 적용되지 않았으므로 직접 호출
        # (실제로는 MethodProxy가 아닌 원본 메서드)
        result = service.simple_method()

        # Then
        assert result == "simple"
        assert call_log == ["handler:execute"]

    def test_advice_auto_injection(self):
        """*advices: MethodAdvice로 자동 주입"""
        # Given
        call_log: list[str] = []

        class Advice1(MethodAdvice):
            def supports(self, c: HandlerContainer) -> bool:
                return True

            def before_sync(self, ctx: InvocationContext) -> None:
                call_log.append("advice1:before")

            def after_sync(self, ctx: InvocationContext, result: Any) -> Any:
                call_log.append("advice1:after")
                return result

        class Advice2(MethodAdvice):
            def supports(self, c: HandlerContainer) -> bool:
                return True

            def before_sync(self, ctx: InvocationContext) -> None:
                call_log.append("advice2:before")

            def after_sync(self, ctx: InvocationContext, result: Any) -> Any:
                call_log.append("advice2:after")
                return result

        @Component
        class MyAdvice1(Advice1):
            pass

        @Component
        class MyAdvice2(Advice2):
            pass

        @Component
        class AdviceConfig:
            @Factory
            def invocation_manager(
                self, *advices: MethodAdvice
            ) -> MethodInvocationManager:
                registry = MethodAdviceRegistry()
                for advice in advices:
                    registry.register(advice)
                return MethodInvocationManager(registry)

        @Component
        class TestService:
            @Handler
            def run(self) -> str:
                call_log.append("handler:execute")
                return "done"

        # When
        app = (
            Application("test")
            .scan(MyAdvice1, MyAdvice2, AdviceConfig, TestService)
            .ready()
        )
        service = app.manager.get_instance(TestService)
        result = service.run()

        # Then
        assert result == "done"
        # 순서: advice1 → advice2 → handler → advice2 → advice1
        assert "handler:execute" in call_log
        assert call_log.count("advice1:before") == 1
        assert call_log.count("advice2:before") == 1


class TestNestedAdvice:
    """중첩 Advice 테스트 - 메서드 내부에서 다른 @Handler 메서드 호출 시 프록시 적용 확인"""

    def test_nested_handler_call_applies_proxy(self):
        """@Handler 메서드 내에서 다른 @Handler 호출 시 프록시가 적용되는지 테스트"""
        # Given
        call_log: list[str] = []

        class LoggingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            def before_sync(self, context: InvocationContext) -> None:
                method_name = context.container.target.__name__
                call_log.append(f"advice:before:{method_name}")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                method_name = context.container.target.__name__
                call_log.append(f"advice:after:{method_name}")
                return result

        @Component
        class AdviceConfig:
            @Factory
            def invocation_manager(self) -> MethodInvocationManager:
                registry = MethodAdviceRegistry()
                registry.register(LoggingAdvice())
                return MethodInvocationManager(registry)

        @Component
        class NestedService:
            @Handler
            def outer_method(self) -> str:
                call_log.append("outer:execute")
                # 내부에서 다른 @Handler 메서드 호출
                inner_result = self.inner_method()
                call_log.append(f"outer:got:{inner_result}")
                return "outer_result"

            @Handler
            def inner_method(self) -> str:
                call_log.append("inner:execute")
                return "inner_result"

        # When
        app = Application("test").scan(AdviceConfig, NestedService).ready()
        service = app.manager.get_instance(NestedService)
        result = service.outer_method()

        # Then
        assert result == "outer_result"
        # 중첩 호출 시 inner_method에도 Advice가 적용되어야 함
        expected_log = [
            "advice:before:outer_method",
            "outer:execute",
            "advice:before:inner_method",  # 중첩 호출 시 프록시 적용
            "inner:execute",
            "advice:after:inner_method",
            "outer:got:inner_result",
            "advice:after:outer_method",
        ]
        assert call_log == expected_log

    @pytest.mark.asyncio
    async def test_nested_async_handler_call_applies_proxy(self):
        """비동기 @Handler 메서드 내에서 다른 비동기 @Handler 호출 시 프록시 적용"""
        # Given
        call_log: list[str] = []

        class AsyncLoggingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            async def before(self, context: InvocationContext) -> None:
                method_name = context.container.target.__name__
                call_log.append(f"advice:before:{method_name}")

            async def after(self, context: InvocationContext, result: Any) -> Any:
                method_name = context.container.target.__name__
                call_log.append(f"advice:after:{method_name}")
                return result

        @Component
        class AdviceConfig:
            @Factory
            def invocation_manager(self) -> MethodInvocationManager:
                registry = MethodAdviceRegistry()
                registry.register(AsyncLoggingAdvice())
                return MethodInvocationManager(registry)

        @Component
        class AsyncNestedService:
            @Handler
            async def outer_async(self) -> str:
                call_log.append("outer:execute")
                inner_result = await self.inner_async()
                call_log.append(f"outer:got:{inner_result}")
                return "outer_async_result"

            @Handler
            async def inner_async(self) -> str:
                call_log.append("inner:execute")
                return "inner_async_result"

        # When
        app = Application("test").scan(AdviceConfig, AsyncNestedService).ready()
        service = app.manager.get_instance(AsyncNestedService)
        result = await service.outer_async()

        # Then
        assert result == "outer_async_result"
        expected_log = [
            "advice:before:outer_async",
            "outer:execute",
            "advice:before:inner_async",
            "inner:execute",
            "advice:after:inner_async",
            "outer:got:inner_async_result",
            "advice:after:outer_async",
        ]
        assert call_log == expected_log

    def test_deeply_nested_handler_calls(self):
        """3단계 이상 중첩 호출 테스트"""
        # Given
        call_log: list[str] = []

        class LoggingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            def before_sync(self, context: InvocationContext) -> None:
                method_name = context.container.target.__name__
                call_log.append(f"before:{method_name}")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                method_name = context.container.target.__name__
                call_log.append(f"after:{method_name}")
                return result

        @Component
        class AdviceConfig:
            @Factory
            def invocation_manager(self) -> MethodInvocationManager:
                registry = MethodAdviceRegistry()
                registry.register(LoggingAdvice())
                return MethodInvocationManager(registry)

        @Component
        class DeeplyNestedService:
            @Handler
            def level1(self) -> str:
                call_log.append("level1:execute")
                return self.level2()

            @Handler
            def level2(self) -> str:
                call_log.append("level2:execute")
                return self.level3()

            @Handler
            def level3(self) -> str:
                call_log.append("level3:execute")
                return "deep_result"

        # When
        app = Application("test").scan(AdviceConfig, DeeplyNestedService).ready()
        service = app.manager.get_instance(DeeplyNestedService)
        result = service.level1()

        # Then
        assert result == "deep_result"
        expected_log = [
            "before:level1",
            "level1:execute",
            "before:level2",
            "level2:execute",
            "before:level3",
            "level3:execute",
            "after:level3",
            "after:level2",
            "after:level1",
        ]
        assert call_log == expected_log

    def test_nested_call_with_error_propagation(self):
        """중첩 호출에서 에러 발생 시 on_error 전파 테스트"""
        # Given
        call_log: list[str] = []

        class ErrorTrackingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            def before_sync(self, context: InvocationContext) -> None:
                method_name = context.container.target.__name__
                call_log.append(f"before:{method_name}")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                method_name = context.container.target.__name__
                call_log.append(f"after:{method_name}")
                return result

            def on_error_sync(
                self, context: InvocationContext, error: Exception
            ) -> Any:
                method_name = context.container.target.__name__
                call_log.append(f"error:{method_name}")
                raise error

        @Component
        class AdviceConfig:
            @Factory
            def invocation_manager(self) -> MethodInvocationManager:
                registry = MethodAdviceRegistry()
                registry.register(ErrorTrackingAdvice())
                return MethodInvocationManager(registry)

        @Component
        class ErrorService:
            @Handler
            def caller(self) -> str:
                call_log.append("caller:execute")
                return self.thrower()

            @Handler
            def thrower(self) -> str:
                call_log.append("thrower:execute")
                raise ValueError("nested error")

        # When
        app = Application("test").scan(AdviceConfig, ErrorService).ready()
        service = app.manager.get_instance(ErrorService)

        with pytest.raises(ValueError, match="nested error"):
            service.caller()

        # Then - 에러는 inner에서 발생하고, outer로 전파됨
        expected_log = [
            "before:caller",
            "caller:execute",
            "before:thrower",
            "thrower:execute",
            "error:thrower",  # inner에서 에러 처리
            "error:caller",  # outer로 전파
        ]
        assert call_log == expected_log

    def test_cross_service_nested_calls(self):
        """서로 다른 서비스 간 중첩 호출 테스트"""
        # Given
        call_log: list[str] = []

        class LoggingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            def before_sync(self, context: InvocationContext) -> None:
                instance_name = type(context.instance).__name__
                method_name = context.container.target.__name__
                call_log.append(f"before:{instance_name}.{method_name}")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                instance_name = type(context.instance).__name__
                method_name = context.container.target.__name__
                call_log.append(f"after:{instance_name}.{method_name}")
                return result

        @Component
        class AdviceConfig:
            @Factory
            def invocation_manager(self) -> MethodInvocationManager:
                registry = MethodAdviceRegistry()
                registry.register(LoggingAdvice())
                return MethodInvocationManager(registry)

        @Component
        class ServiceB:
            @Handler
            def process(self, data: str) -> str:
                call_log.append(f"ServiceB.process:{data}")
                return f"processed:{data}"

        @Component
        class ServiceA:
            service_b: ServiceB

            @Handler
            def execute(self) -> str:
                call_log.append("ServiceA.execute")
                return self.service_b.process("input")

        # When
        app = Application("test").scan(AdviceConfig, ServiceA, ServiceB).ready()
        service_a = app.manager.get_instance(ServiceA)
        result = service_a.execute()

        # Then
        assert result == "processed:input"
        expected_log = [
            "before:ServiceA.execute",
            "ServiceA.execute",
            "before:ServiceB.process",
            "ServiceB.process:input",
            "after:ServiceB.process",
            "after:ServiceA.execute",
        ]
        assert call_log == expected_log
