"""MethodAdvice 테스트"""

import pytest
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

    def supports(self, container: HandlerContainer) -> bool:
        return container.has_element(CacheableElement)

    async def before(self, context: InvocationContext) -> None:
        self.calls.append("cache:before")

    async def after(self, context: InvocationContext, result: Any) -> Any:
        self.calls.append("cache:after")
        return result


class LogAdvice(MethodAdvice):
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
        self.elements: list[Element] = []
        self.handler = None

    def add_elements(self, *elements: Element) -> None:
        self.elements.extend(elements)

    def has_element(self, element_type: type) -> bool:
        return any(isinstance(e, element_type) for e in self.elements)


# === 단위 테스트: MethodAdvice ===


class TestMethodAdvice:
    """MethodAdvice 단위 테스트 (Registry 직접 주입)"""

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
        # TransactionalElement 없음

        async def handler() -> str:
            return "no-advice"

        # When
        result = await manager.invoke(container, None, handler)

        # Then
        assert result == "no-advice"
        assert tx_advice.calls == []  # 호출 안 됨

    @pytest.mark.asyncio
    async def test_multiple_advices_execution_order(self):
        """여러 어드바이스 실행 순서: before 순서대로, after 역순"""
        # Given
        tx_advice = TransactionAdvice()
        cache_advice = CacheAdvice()
        registry = MethodAdviceRegistry()
        registry.register(tx_advice)
        registry.register(cache_advice)
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()
        container.add_elements(TransactionalElement())
        container.add_elements(CacheableElement())

        async def handler() -> str:
            return "result"

        # When
        await manager.invoke(container, None, handler)

        # Then - before: tx → cache, after: cache → tx
        assert tx_advice.calls == ["tx:before", "tx:after"]
        assert cache_advice.calls == ["cache:before", "cache:after"]

    @pytest.mark.asyncio
    async def test_on_error_called_on_exception(self):
        """핸들러 예외 시 on_error 호출"""
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
        """Context를 통한 어드바이스 간 데이터 공유"""
        # Given
        shared_data = {}

        class DataSharingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            async def before(self, context: InvocationContext) -> None:
                context.set_attribute("request_id", "123")

            async def after(self, context: InvocationContext, result: Any) -> Any:
                shared_data["request_id"] = context.get_attribute("request_id")
                return result

        registry = MethodAdviceRegistry()
        registry.register(DataSharingAdvice())
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()

        async def handler() -> str:
            return "done"

        # When
        await manager.invoke(container, None, handler)

        # Then
        assert shared_data["request_id"] == "123"

    def test_sync_handler_support(self):
        """동기 핸들러 지원"""
        # Given
        call_log = []

        class SyncAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            def before_sync(self, context: InvocationContext) -> None:
                call_log.append("before")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                call_log.append("after")
                return result

        registry = MethodAdviceRegistry()
        registry.register(SyncAdvice())
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()

        def handler(x: int) -> int:
            call_log.append("handler")
            return x * 2

        # When
        result = manager.invoke_sync(container, None, handler, 5)

        # Then
        assert result == 10
        assert call_log == ["before", "handler", "after"]

    @pytest.mark.asyncio
    async def test_advice_modifies_result(self):
        """어드바이스가 결과를 수정"""

        # Given
        class DoublingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            async def after(self, context: InvocationContext, result: Any) -> Any:
                return result * 2

        registry = MethodAdviceRegistry()
        registry.register(DoublingAdvice())
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()

        async def handler() -> int:
            return 5

        # When
        result = await manager.invoke(container, None, handler)

        # Then
        assert result == 10


# === 단위 테스트: MethodAdviceRegistry ===


class TestMethodAdviceRegistry:
    """MethodAdviceRegistry 단위 테스트"""

    def test_find_applicable_filters_by_supports(self):
        """supports()로 적용 가능한 어드바이스 필터링"""
        # Given
        tx_advice = TransactionAdvice()
        cache_advice = CacheAdvice()
        registry = MethodAdviceRegistry()
        registry.register(tx_advice)
        registry.register(cache_advice)

        container = MockHandlerContainer()
        container.add_elements(TransactionalElement())  # tx만 적용

        # When
        applicable = registry.find_applicable(container)

        # Then
        assert len(applicable) == 1
        assert applicable[0] is tx_advice

    def test_find_applicable_returns_empty_when_no_match(self):
        """매칭되는 어드바이스가 없으면 빈 리스트"""
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


# === 단위 테스트: InvocationContext ===


class TestInvocationContext:
    """InvocationContext 단위 테스트"""

    def test_attribute_set_and_get(self):
        """속성 설정 및 조회"""
        # Given
        container = MockHandlerContainer()
        context = InvocationContext(
            container=container, instance=None, args=(), kwargs={}
        )

        # When
        context.set_attribute("key", "value")

        # Then
        assert context.get_attribute("key") == "value"
        assert context.get_attribute("missing", "default") == "default"


# === 단위 테스트: MethodProxy ===


class TestMethodProxy:
    """MethodProxy 단위 테스트"""

    @pytest.mark.asyncio
    async def test_async_method_proxy(self):
        """비동기 메서드 프록시"""
        # Given
        call_log = []

        class LogAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            async def before(self, context: InvocationContext) -> None:
                call_log.append("before")

            async def after(self, context: InvocationContext, result: Any) -> Any:
                call_log.append("after")
                return result

        registry = MethodAdviceRegistry()
        registry.register(LogAdvice())
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()

        class Service:
            async def method(self, x: int) -> int:
                call_log.append("method")
                return x * 2

        service = Service()
        proxy = MethodProxy(
            container=container,
            instance=service,
            original=Service.method,
            manager=manager,
        )

        # When
        result = await proxy(5)

        # Then
        assert result == 10
        assert call_log == ["before", "method", "after"]

    def test_sync_method_proxy(self):
        """동기 메서드 프록시"""
        # Given
        call_log = []

        class LogAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            def before_sync(self, context: InvocationContext) -> None:
                call_log.append("before")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                call_log.append("after")
                return result

        registry = MethodAdviceRegistry()
        registry.register(LogAdvice())
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()

        class Service:
            def method(self, x: int) -> int:
                call_log.append("method")
                return x * 2

        service = Service()
        proxy = MethodProxy(
            container=container,
            instance=service,
            original=Service.method,
            manager=manager,
        )

        # When
        result = proxy(5)

        # Then
        assert result == 10
        assert call_log == ["before", "method", "after"]


# === 통합 테스트: DI와 함께 사용 ===


class TestAdviceWithDI:
    """DI 컨테이너와 Advice 통합 테스트"""

    def test_advice_applied_to_handler_method(self):
        """@Handler 메서드에 Advice 적용"""
        # Given
        call_log: list[str] = []

        class LoggingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            def before_sync(self, context: InvocationContext) -> None:
                call_log.append("advice:before")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                call_log.append("advice:after")
                return result

        @Component
        class AdviceConfig:
            @Factory
            def advice_registry(self) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(LoggingAdvice())
                return registry

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
            def advice_registry(self) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(AsyncLoggingAdvice())
                return registry

        @Component
        class MyService:
            @Handler
            async def do_something_async(self) -> str:
                call_log.append("handler:execute")
                return "async_result"

        # When
        app = Application("test").scan(AdviceConfig, MyService).ready()
        service = app.manager.get_instance(MyService)
        result = await service.do_something_async()

        # Then
        assert result == "async_result"
        assert call_log == ["advice:before", "handler:execute", "advice:after"]

    def test_no_advice_when_registry_not_registered(self):
        """Registry가 없으면 Advice 미적용"""
        # Given
        call_log: list[str] = []

        @Component
        class MyService:
            @Handler
            def do_something(self) -> str:
                call_log.append("handler:execute")
                return "result"

        # When - Registry 없이 Application 시작
        app = Application("test").scan(MyService).ready()
        service = app.manager.get_instance(MyService)
        result = service.do_something()

        # Then - 프록시 없이 직접 호출
        assert result == "result"
        assert call_log == ["handler:execute"]

    def test_advice_auto_injection(self):
        """@Component Advice를 Factory에서 자동 주입"""
        # Given
        call_log: list[str] = []

        @Component
        class LoggingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            def before_sync(self, context: InvocationContext) -> None:
                call_log.append("advice:before")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                call_log.append("advice:after")
                return result

        @Component
        class AdviceConfig:
            @Factory
            def advice_registry(self, *advices: MethodAdvice) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                for advice in advices:
                    registry.register(advice)
                return registry

        @Component
        class MyService:
            @Handler
            def do_something(self) -> str:
                call_log.append("handler:execute")
                return "result"

        # When
        app = Application("test").scan(LoggingAdvice, AdviceConfig, MyService).ready()
        service = app.manager.get_instance(MyService)
        result = service.do_something()

        # Then
        assert result == "result"
        assert call_log == ["advice:before", "handler:execute", "advice:after"]


# === 통합 테스트: 중첩 호출 ===


class TestNestedAdvice:
    """중첩 핸들러 호출 시 Advice 동작"""

    def test_nested_handler_call(self):
        """중첩 핸들러 호출에도 Advice 적용"""
        # Given
        call_log: list[str] = []

        class LoggingAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            def before_sync(self, context: InvocationContext) -> None:
                call_log.append("before")

            def after_sync(self, context: InvocationContext, result: Any) -> Any:
                call_log.append("after")
                return result

        @Component
        class AdviceConfig:
            @Factory
            def advice_registry(self) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(LoggingAdvice())
                return registry

        @Component
        class InnerService:
            @Handler
            def inner_method(self) -> str:
                call_log.append("inner:execute")
                return "inner"

        @Component
        class OuterService:
            inner: InnerService

            @Handler
            def outer_method(self) -> str:
                call_log.append("outer:execute")
                result = self.inner.inner_method()
                return f"outer-{result}"

        # When
        app = Application("test").scan(AdviceConfig, InnerService, OuterService).ready()
        outer = app.manager.get_instance(OuterService)
        result = outer.outer_method()

        # Then
        assert result == "outer-inner"
        # outer.before -> outer.execute -> inner.before -> inner.execute -> inner.after -> outer.after
        assert "outer:execute" in call_log
        assert "inner:execute" in call_log


# === 에러 전파 테스트 ===


class TestErrorPropagation:
    """에러 전파 및 on_error 테스트"""

    @pytest.mark.asyncio
    async def test_error_recovery_in_on_error(self):
        """on_error에서 에러 복구"""

        # Given
        class RecoveryAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            async def on_error(
                self, context: InvocationContext, error: Exception
            ) -> Any:
                # 에러를 복구하고 대체 값 반환
                return "recovered"

        registry = MethodAdviceRegistry()
        registry.register(RecoveryAdvice())
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()

        async def handler() -> str:
            raise ValueError("test error")

        # When
        result = await manager.invoke(container, None, handler)

        # Then
        assert result == "recovered"

    @pytest.mark.asyncio
    async def test_error_chain_propagation(self):
        """여러 어드바이스 중 에러 전파"""
        # Given
        call_log = []

        class FirstAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            async def before(self, context: InvocationContext) -> None:
                call_log.append("first:before")

            async def on_error(
                self, context: InvocationContext, error: Exception
            ) -> Any:
                call_log.append("first:on_error")
                raise error

        class SecondAdvice(MethodAdvice):
            def supports(self, container: HandlerContainer) -> bool:
                return True

            async def before(self, context: InvocationContext) -> None:
                call_log.append("second:before")

            async def on_error(
                self, context: InvocationContext, error: Exception
            ) -> Any:
                call_log.append("second:on_error")
                raise error

        registry = MethodAdviceRegistry()
        registry.register(FirstAdvice())
        registry.register(SecondAdvice())
        manager = MethodInvocationManager(registry)

        container = MockHandlerContainer()

        async def handler() -> str:
            raise ValueError("test")

        # When
        with pytest.raises(ValueError):
            await manager.invoke(container, None, handler)

        # Then - on_error는 역순으로 호출
        assert call_log == [
            "first:before",
            "second:before",
            "second:on_error",
            "first:on_error",
        ]
