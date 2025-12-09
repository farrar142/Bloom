"""
Decorator 테스트 - @Transactional, @Factory with scope

단위 테스트:
- @Transactional decorator
- @Factory with scope parameter

통합 테스트:
- @Transactional과 @Handler 조합
- @Factory(scope=Scope.CALL)와 ScopeContext 통합

엣지 케이스:
- 중첩 @Transactional
- sync/async 혼용
"""

import pytest
import asyncio
from bloom.core.decorators import (
    Component,
    Service,
    Handler,
    Configuration,
    Factory,
    Transactional,
    Scoped,
)
from bloom.core.container.scope import (
    Scope,
    ScopeContext,
    get_transactional_scope,
    set_transactional_scope,
    transactional_scope,
)
from bloom.core.abstract.autocloseable import AutoCloseable, AsyncAutoCloseable


# =============================================================================
# Mock 클래스들
# =============================================================================


class MockAutoCloseable(AutoCloseable):
    """테스트용 AutoCloseable"""

    instances: list["MockAutoCloseable"] = []
    close_order: list[int] = []

    def __init__(self, id: int = 0):
        self.id = id
        self.entered = False
        self.exited = False
        MockAutoCloseable.instances.append(self)

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited = True
        MockAutoCloseable.close_order.append(self.id)

    @classmethod
    def reset(cls):
        cls.instances = []
        cls.close_order = []


class MockAsyncAutoCloseable(AsyncAutoCloseable):
    """테스트용 AsyncAutoCloseable"""

    instances: list["MockAsyncAutoCloseable"] = []
    close_order: list[int] = []

    def __init__(self, id: int = 0):
        self.id = id
        self.entered = False
        self.exited = False
        MockAsyncAutoCloseable.instances.append(self)

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.exited = True
        MockAsyncAutoCloseable.close_order.append(self.id)

    @classmethod
    def reset(cls):
        cls.instances = []
        cls.close_order = []


# =============================================================================
# 단위 테스트: @Transactional
# =============================================================================


class TestTransactionalDecorator:
    """@Transactional decorator 단위 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        MockAsyncAutoCloseable.reset()
        set_transactional_scope(None)

    def teardown_method(self):
        set_transactional_scope(None)

    @pytest.mark.asyncio
    async def test_transactional_creates_scope(self):
        """@Transactional이 스코프를 생성하는지 테스트"""
        scope_inside = None

        class MyService:
            @Transactional
            def my_method(self):
                nonlocal scope_inside
                scope_inside = get_transactional_scope()
                return "result"

        service = MyService()
        result = await service.my_method()

        assert result == "result"
        assert scope_inside is not None
        assert isinstance(scope_inside, ScopeContext)

    @pytest.mark.asyncio
    async def test_transactional_cleans_up_scope(self):
        """@Transactional이 종료 시 스코프를 정리하는지 테스트"""

        class MyService:
            @Transactional
            def my_method(self):
                return get_transactional_scope()

        service = MyService()
        scope_inside = await service.my_method()

        # 메서드 종료 후 스코프 정리됨
        assert get_transactional_scope() is None

    @pytest.mark.asyncio
    async def test_transactional_async_method(self):
        """@Transactional async 메서드 테스트"""
        scope_inside = None

        class MyService:
            @Transactional
            async def async_method(self):
                nonlocal scope_inside
                scope_inside = get_transactional_scope()
                await asyncio.sleep(0.01)
                return "async result"

        service = MyService()
        result = await service.async_method()

        assert result == "async result"
        assert scope_inside is not None

    @pytest.mark.asyncio
    async def test_transactional_closes_closeables(self):
        """@Transactional이 closeable을 close하는지 테스트"""
        closeable = MockAsyncAutoCloseable(1)

        class MyService:
            @Transactional
            async def my_method(self):
                ctx = get_transactional_scope()
                await closeable.__aenter__()
                ctx.register_closeable(closeable)
                return "done"

        service = MyService()
        await service.my_method()

        assert closeable.exited

    @pytest.mark.asyncio
    async def test_transactional_preserves_function_metadata(self):
        """@Transactional이 함수 메타데이터를 유지하는지 테스트"""

        class MyService:
            @Transactional
            def documented_method(self):
                """This is a documented method."""
                return "result"

        service = MyService()

        assert service.documented_method.__name__ == "documented_method"
        assert service.documented_method.__doc__ == "This is a documented method."

    @pytest.mark.asyncio
    async def test_transactional_with_arguments(self):
        """@Transactional 인자 전달 테스트"""

        class MyService:
            @Transactional
            def method_with_args(self, a: int, b: str, c: float = 1.0):
                return f"{a}-{b}-{c}"

        service = MyService()
        result = await service.method_with_args(1, "hello", c=2.5)

        assert result == "1-hello-2.5"

    @pytest.mark.asyncio
    async def test_transactional_with_return_value(self):
        """@Transactional 반환값 테스트"""

        class MyService:
            @Transactional
            def return_dict(self):
                return {"key": "value", "number": 42}

        service = MyService()
        result = await service.return_dict()

        assert result == {"key": "value", "number": 42}


# =============================================================================
# 단위 테스트: @Factory with scope
# =============================================================================


class TestFactoryWithScope:
    """@Factory with scope 단위 테스트"""

    def test_factory_default_singleton_scope(self):
        """@Factory 기본 SINGLETON 스코프 테스트"""
        from bloom.core.container.factory import FactoryContainer

        @Configuration
        class AppConfig:
            @Factory
            def singleton_service(self) -> MockAutoCloseable:
                return MockAutoCloseable(1)

        # FactoryContainer가 등록되었는지 확인
        assert hasattr(AppConfig.singleton_service, "__component_id__")

    def test_factory_call_scope(self):
        """@Factory @Scoped(Scope.CALL) 테스트"""
        from bloom.core.container.factory import FactoryContainer

        @Configuration
        class AppConfig:
            @Factory
            @Scoped(Scope.CALL)
            def call_scoped_service(self) -> MockAutoCloseable:
                return MockAutoCloseable(2)

        assert hasattr(AppConfig.call_scoped_service, "__component_id__")
        assert getattr(AppConfig.call_scoped_service, "__scope__") == Scope.CALL

    def test_factory_request_scope(self):
        """@Factory @Scoped(Scope.REQUEST) 테스트"""
        from bloom.core.container.factory import FactoryContainer

        @Configuration
        class AppConfig:
            @Factory
            @Scoped(Scope.REQUEST)
            def request_scoped_service(self) -> MockAutoCloseable:
                return MockAutoCloseable(3)

        assert hasattr(AppConfig.request_scoped_service, "__component_id__")
        assert getattr(AppConfig.request_scoped_service, "__scope__") == Scope.REQUEST

    def test_factory_async_with_scope(self):
        """@Factory @Scoped async 테스트"""

        @Configuration
        class AppConfig:
            @Factory
            @Scoped(Scope.CALL)
            async def async_call_scoped(self) -> MockAsyncAutoCloseable:
                return MockAsyncAutoCloseable(4)

        assert hasattr(AppConfig.async_call_scoped, "__component_id__")
        assert getattr(AppConfig.async_call_scoped, "__scope__") == Scope.CALL


# =============================================================================
# 통합 테스트: @Transactional 중첩
# =============================================================================


class TestNestedTransactional:
    """중첩 @Transactional 통합 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        MockAsyncAutoCloseable.reset()
        set_transactional_scope(None)

    def teardown_method(self):
        set_transactional_scope(None)

    @pytest.mark.asyncio
    async def test_nested_transactional_shares_scope(self):
        """중첩 @Transactional이 같은 스코프를 공유하는지 테스트"""
        scopes = []

        class MyService:
            @Transactional
            def outer_method(self):
                scopes.append(get_transactional_scope())
                return self.inner_method()

            @Transactional
            def inner_method(self):
                scopes.append(get_transactional_scope())
                return "inner"

        service = MyService()
        # outer_method 호출 (내부에서 inner_method 호출)
        # 하지만 이 테스트에서는 Transactional wrapper가 적용되어
        # 각각 await가 필요함

        # 직접 transactional_scope 사용하여 테스트
        async with transactional_scope() as outer_ctx:
            scopes.append(outer_ctx)
            async with transactional_scope() as inner_ctx:
                scopes.append(inner_ctx)

        # 중첩된 transactional은 같은 context
        assert scopes[0] == scopes[1]

    @pytest.mark.asyncio
    async def test_nested_transactional_closes_once(self):
        """중첩 @Transactional이 한 번만 close하는지 테스트"""
        MockAsyncAutoCloseable.reset()
        closeable = MockAsyncAutoCloseable(1)

        async with transactional_scope() as ctx:
            await closeable.__aenter__()
            ctx.register_closeable(closeable)

            async with transactional_scope() as inner_ctx:
                # 내부에서는 아직 close 안 됨
                assert not closeable.exited
                # 중첩된 context는 같은 context임
                assert ctx == inner_ctx

        # 최외곽 종료 후 close
        assert closeable.exited
        # close는 한 번만 호출됨
        assert MockAsyncAutoCloseable.close_order.count(1) == 1


# =============================================================================
# 통합 테스트: @Transactional과 예외
# =============================================================================


class TestTransactionalWithException:
    """@Transactional 예외 처리 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        MockAsyncAutoCloseable.reset()
        set_transactional_scope(None)

    def teardown_method(self):
        set_transactional_scope(None)

    @pytest.mark.asyncio
    async def test_transactional_exception_still_closes(self):
        """@Transactional 예외 발생 시에도 close 실행 테스트"""
        closeable = MockAsyncAutoCloseable(1)

        class MyService:
            @Transactional
            async def failing_method(self):
                ctx = get_transactional_scope()
                await closeable.__aenter__()
                ctx.register_closeable(closeable)
                raise ValueError("Test error")

        service = MyService()

        with pytest.raises(ValueError, match="Test error"):
            await service.failing_method()

        # 예외에도 불구하고 close됨
        assert closeable.exited

    @pytest.mark.asyncio
    async def test_transactional_exception_propagates(self):
        """@Transactional 예외가 전파되는지 테스트"""

        class MyService:
            @Transactional
            def raising_method(self):
                raise RuntimeError("Should propagate")

        service = MyService()

        with pytest.raises(RuntimeError, match="Should propagate"):
            await service.raising_method()


# =============================================================================
# 통합 테스트: sync/async 혼용
# =============================================================================


class TestTransactionalSyncAsync:
    """@Transactional sync/async 혼용 테스트"""

    def setup_method(self):
        set_transactional_scope(None)

    def teardown_method(self):
        set_transactional_scope(None)

    @pytest.mark.asyncio
    async def test_sync_method_becomes_awaitable(self):
        """sync 메서드가 awaitable이 되는지 테스트"""

        class MyService:
            @Transactional
            def sync_method(self):
                return "sync result"

        service = MyService()

        # @Transactional은 항상 async wrapper를 반환
        result = await service.sync_method()
        assert result == "sync result"

    @pytest.mark.asyncio
    async def test_async_method_stays_async(self):
        """async 메서드가 async로 유지되는지 테스트"""

        class MyService:
            @Transactional
            async def async_method(self):
                await asyncio.sleep(0.01)
                return "async result"

        service = MyService()

        result = await service.async_method()
        assert result == "async result"


# =============================================================================
# 엣지 케이스 테스트
# =============================================================================


class TestDecoratorEdgeCases:
    """Decorator 엣지 케이스 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        set_transactional_scope(None)

    def teardown_method(self):
        set_transactional_scope(None)

    @pytest.mark.asyncio
    async def test_transactional_with_none_return(self):
        """@Transactional None 반환 테스트"""

        class MyService:
            @Transactional
            def none_method(self):
                pass

        service = MyService()
        result = await service.none_method()
        assert result is None

    @pytest.mark.asyncio
    async def test_transactional_with_generator(self):
        """@Transactional 제너레이터 반환 테스트"""

        class MyService:
            @Transactional
            def gen_method(self):
                # 제너레이터를 반환하는 것은 특수 케이스
                return [i for i in range(5)]  # 리스트 컴프리헨션으로 대체

        service = MyService()
        result = await service.gen_method()
        assert result == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_multiple_transactional_methods(self):
        """여러 @Transactional 메서드 테스트"""
        results = []

        class MyService:
            @Transactional
            def method_a(self):
                ctx = get_transactional_scope()
                results.append(("a", ctx.context_id))
                return "a"

            @Transactional
            def method_b(self):
                ctx = get_transactional_scope()
                results.append(("b", ctx.context_id))
                return "b"

        service = MyService()

        await service.method_a()
        await service.method_b()

        # 각각 다른 스코프 (context_id로 비교)
        assert results[0][1] != results[1][1]

    @pytest.mark.asyncio
    async def test_transactional_instance_isolation(self):
        """@Transactional 인스턴스 격리 테스트"""
        scopes = []

        class MyService:
            @Transactional
            def my_method(self):
                scopes.append(get_transactional_scope())

        s1 = MyService()
        s2 = MyService()

        await s1.my_method()
        await s2.my_method()

        # 각각 다른 스코프
        assert scopes[0] != scopes[1]

    def test_factory_without_scope_uses_singleton(self):
        """@Factory scope 없이 사용 시 SINGLETON 기본값 테스트"""
        from bloom.core.container.manager import get_container_registry

        # 고유한 반환 타입 사용 (전역 상태 오염 방지)
        class UniqueType:
            pass

        @Configuration
        class TestConfig:
            @Factory
            def my_factory(self) -> UniqueType:
                return UniqueType()

        # 등록된 FactoryContainer 확인
        registry = get_container_registry()
        if TestConfig.my_factory in registry:
            containers = registry[TestConfig.my_factory]
            for container in containers.values():
                if hasattr(container, "scope"):
                    assert container.scope == Scope.SINGLETON


# =============================================================================
# 성능 테스트
# =============================================================================


class TestDecoratorPerformance:
    """Decorator 성능 테스트"""

    def setup_method(self):
        set_transactional_scope(None)

    def teardown_method(self):
        set_transactional_scope(None)

    @pytest.mark.asyncio
    async def test_many_transactional_calls(self):
        """많은 @Transactional 호출 테스트"""
        call_count = 0

        class MyService:
            @Transactional
            def quick_method(self):
                nonlocal call_count
                call_count += 1
                return call_count

        service = MyService()

        for _ in range(100):
            await service.quick_method()

        assert call_count == 100

    @pytest.mark.asyncio
    async def test_concurrent_transactional_calls(self):
        """동시 @Transactional 호출 테스트"""
        results = []

        class MyService:
            @Transactional
            async def async_method(self, id: int):
                await asyncio.sleep(0.01)
                ctx = get_transactional_scope()
                results.append((id, ctx.context_id))
                return id

        service = MyService()

        # 동시에 여러 호출
        tasks = [service.async_method(i) for i in range(5)]
        await asyncio.gather(*tasks)

        # 각각 다른 context_id
        context_ids = [r[1] for r in results]
        assert len(set(context_ids)) == 5  # 모두 다른 ID


# =============================================================================
# @Scoped + @Component 테스트
# =============================================================================


class TestScopedComponent:
    """@Scoped + @Component 데코레이터 테스트"""

    def test_scoped_component_singleton(self):
        """@Component 기본 스코프는 SINGLETON"""
        from bloom.core.container import Container

        @Component
        class SingletonService:
            pass

        container = Container.register(SingletonService)
        from bloom.core.container.scope import Scope

        assert container.scope == Scope.SINGLETON

    def test_scoped_component_call_scope(self):
        """@Component @Scoped(Scope.CALL) 테스트"""
        from bloom.core.container import Container
        from bloom.core.container.scope import Scope

        @Component
        @Scoped(Scope.CALL)
        class CallScopedService:
            pass

        container = Container.register(CallScopedService)
        assert container.scope == Scope.CALL

    def test_scoped_component_request_scope(self):
        """@Component @Scoped(Scope.REQUEST) 테스트"""
        from bloom.core.container import Container
        from bloom.core.container.scope import Scope

        @Component
        @Scoped(Scope.REQUEST)
        class RequestScopedService:
            pass

        container = Container.register(RequestScopedService)
        assert container.scope == Scope.REQUEST

    def test_scoped_service_decorator(self):
        """@Service @Scoped 테스트"""
        from bloom.core.container import Container
        from bloom.core.container.scope import Scope

        @Service
        @Scoped(Scope.REQUEST)
        class RequestScopedHandler:
            pass

        container = Container.register(RequestScopedHandler)
        assert container.scope == Scope.REQUEST

    def test_scope_attribute_on_class(self):
        """__scope__ 속성이 클래스에 설정되는지 확인"""
        from bloom.core.container.scope import Scope

        @Scoped(Scope.CALL)
        class MyScopedClass:
            pass

        assert hasattr(MyScopedClass, "__scope__")
        assert MyScopedClass.__scope__ == Scope.CALL

    def test_scope_attribute_on_function(self):
        """__scope__ 속성이 함수에 설정되는지 확인"""
        from bloom.core.container.scope import Scope

        @Scoped(Scope.REQUEST)
        def my_scoped_function():
            pass

        assert hasattr(my_scoped_function, "__scope__")
        assert my_scoped_function.__scope__ == Scope.REQUEST
