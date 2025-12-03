"""
AOP 모듈 테스트
"""

import pytest
import asyncio
from typing import Any

from bloom.core.aop import (
    MethodInterceptor,
    InterceptorChain,
    MethodInvocation,
    BeforeInterceptor,
    AfterInterceptor,
    AroundInterceptor,
    AfterReturningInterceptor,
    AfterThrowingInterceptor,
    MethodDescriptor,
    InterceptorInfo,
    get_method_descriptor,
    ensure_method_descriptor,
    Before,
    After,
    Around,
    AfterReturning,
    AfterThrowing,
    Order,
    Transactional,
    EventListener,
    Cacheable,
    Retry,
    Timed,
    Logged,
    create_component_proxy,
    get_interceptor_registry,
    reset_interceptor_registry,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """각 테스트 전후에 레지스트리 초기화"""
    reset_interceptor_registry()
    yield
    reset_interceptor_registry()


class TestInterceptorChain:
    """InterceptorChain 테스트"""

    @pytest.mark.asyncio
    async def test_empty_chain_invokes_target(self):
        """빈 체인은 타겟 메서드를 직접 호출"""
        result = []

        class Target:
            async def method(self, value: str) -> str:
                result.append(f"method:{value}")
                return f"result:{value}"

        target = Target()
        chain = InterceptorChain()

        invocation = MethodInvocation(
            target=target,
            method_name="method",
            args=("test",),
            kwargs={},
            method=target.method,
        )

        ret = await chain.invoke(invocation)

        assert result == ["method:test"]
        assert ret == "result:test"

    @pytest.mark.asyncio
    async def test_before_interceptor(self):
        """Before 인터셉터는 메서드 전에 실행"""
        order = []

        async def before_callback(inv: MethodInvocation) -> None:
            order.append("before")

        class Target:
            async def method(self) -> str:
                order.append("method")
                return "done"

        target = Target()
        chain = InterceptorChain()
        chain.add(BeforeInterceptor(before_callback))

        invocation = MethodInvocation(
            target=target,
            method_name="method",
            args=(),
            kwargs={},
            method=target.method,
        )

        await chain.invoke(invocation)

        assert order == ["before", "method"]

    @pytest.mark.asyncio
    async def test_after_interceptor(self):
        """After 인터셉터는 메서드 후에 실행 (예외 시에도)"""
        order = []

        async def after_callback(
            inv: MethodInvocation, result: Any, exc: Exception | None
        ) -> None:
            order.append(
                f"after:result={result},exc={type(exc).__name__ if exc else None}"
            )

        class Target:
            async def method(self) -> str:
                order.append("method")
                return "done"

        target = Target()
        chain = InterceptorChain()
        chain.add(AfterInterceptor(after_callback))

        invocation = MethodInvocation(
            target=target,
            method_name="method",
            args=(),
            kwargs={},
            method=target.method,
        )

        await chain.invoke(invocation)

        assert order == ["method", "after:result=done,exc=None"]

    @pytest.mark.asyncio
    async def test_after_interceptor_on_exception(self):
        """After 인터셉터는 예외 발생 시에도 실행"""
        order = []

        async def after_callback(
            inv: MethodInvocation, result: Any, exc: Exception | None
        ) -> None:
            order.append(f"after:exc={type(exc).__name__ if exc else None}")

        class Target:
            async def method(self) -> str:
                order.append("method")
                raise ValueError("test error")

        target = Target()
        chain = InterceptorChain()
        chain.add(AfterInterceptor(after_callback))

        invocation = MethodInvocation(
            target=target,
            method_name="method",
            args=(),
            kwargs={},
            method=target.method,
        )

        with pytest.raises(ValueError):
            await chain.invoke(invocation)

        assert order == ["method", "after:exc=ValueError"]

    @pytest.mark.asyncio
    async def test_around_interceptor(self):
        """Around 인터셉터는 전후를 모두 제어"""
        order = []

        async def around_callback(join_point) -> Any:
            order.append("around:before")
            result = await join_point.proceed()
            order.append(f"around:after:{result}")
            return f"wrapped:{result}"

        class Target:
            async def method(self) -> str:
                order.append("method")
                return "done"

        target = Target()
        chain = InterceptorChain()
        chain.add(AroundInterceptor(around_callback))

        invocation = MethodInvocation(
            target=target,
            method_name="method",
            args=(),
            kwargs={},
            method=target.method,
        )

        result = await chain.invoke(invocation)

        assert order == ["around:before", "method", "around:after:done"]
        assert result == "wrapped:done"

    @pytest.mark.asyncio
    async def test_interceptor_order(self):
        """인터셉터는 order 순으로 실행 (낮은 값이 먼저)"""
        order = []

        class OrderedInterceptor(MethodInterceptor):
            def __init__(self, name: str, ord: int):
                self.name = name
                self.order = ord

            async def intercept(self, inv, proceed):
                order.append(f"{self.name}:before")
                result = await proceed()
                order.append(f"{self.name}:after")
                return result

        class Target:
            async def method(self) -> str:
                order.append("method")
                return "done"

        target = Target()
        chain = InterceptorChain()
        # 역순으로 추가해도 order에 따라 정렬됨
        chain.add(OrderedInterceptor("C", 30))
        chain.add(OrderedInterceptor("A", 10))
        chain.add(OrderedInterceptor("B", 20))

        invocation = MethodInvocation(
            target=target,
            method_name="method",
            args=(),
            kwargs={},
            method=target.method,
        )

        await chain.invoke(invocation)

        # 낮은 order가 먼저 (외부에서 감쌈)
        # A -> B -> C -> method -> C -> B -> A
        assert order == [
            "A:before",
            "B:before",
            "C:before",
            "method",
            "C:after",
            "B:after",
            "A:after",
        ]


class TestDecorators:
    """AOP 데코레이터 테스트"""

    def test_order_decorator(self):
        """@Order 데코레이터는 메서드 순서 설정"""

        @Order(10)
        async def method():
            pass

        descriptor = get_method_descriptor(method)
        assert descriptor is not None
        assert descriptor.order == 10

    def test_before_decorator(self):
        """@Before 데코레이터는 before 인터셉터 정보 추가"""
        callback = lambda inv: None

        @Before(callback, order=5)
        async def method():
            pass

        descriptor = get_method_descriptor(method)
        assert descriptor is not None
        assert len(descriptor.interceptors) == 1
        assert descriptor.interceptors[0].interceptor_type == "before"
        assert descriptor.interceptors[0].callback is callback
        assert descriptor.interceptors[0].order == 5

    def test_transactional_decorator(self):
        """@Transactional 데코레이터는 트랜잭션 메타데이터 추가"""

        @Transactional(read_only=True, isolation="READ_COMMITTED")
        async def method():
            pass

        descriptor = get_method_descriptor(method)
        assert descriptor is not None

        tx_interceptors = descriptor.get_interceptors_by_type("transactional")
        assert len(tx_interceptors) == 1
        assert tx_interceptors[0].metadata["read_only"] is True
        assert tx_interceptors[0].metadata["isolation"] == "READ_COMMITTED"

    def test_event_listener_decorator(self):
        """@EventListener 데코레이터는 이벤트 리스너 메타데이터 추가"""

        @EventListener("user.created")
        async def on_user_created(event):
            pass

        descriptor = get_method_descriptor(on_user_created)
        assert descriptor is not None
        assert descriptor.get_metadata("event_listener")["event_type"] == "user.created"

    def test_multiple_decorators(self):
        """여러 데코레이터 조합"""

        @Order(1)
        @Transactional()
        @Cacheable("users", ttl=300)
        @Logged(level="DEBUG")
        async def get_user(id: int):
            pass

        descriptor = get_method_descriptor(get_user)
        assert descriptor is not None
        assert descriptor.order == 1
        assert descriptor.has_interceptor_type("transactional")
        assert descriptor.has_interceptor_type("cacheable")
        assert descriptor.has_interceptor_type("logged")


class TestComponentProxy:
    """ComponentProxy 테스트"""

    @pytest.mark.asyncio
    async def test_proxy_with_before_decorator(self):
        """@Before 데코레이터가 있는 메서드는 프록시됨"""
        call_log = []

        def log_call(inv: MethodInvocation) -> None:
            call_log.append(f"before:{inv.method_name}")

        class Service:
            @Before(log_call)
            async def do_something(self, value: str) -> str:
                call_log.append(f"method:{value}")
                return f"result:{value}"

        service = Service()
        proxied = create_component_proxy(service)

        result = await proxied.do_something("test")

        assert call_log == ["before:do_something", "method:test"]
        assert result == "result:test"

    @pytest.mark.asyncio
    async def test_proxy_with_around_decorator(self):
        """@Around 데코레이터로 메서드 감싸기"""
        call_log = []

        async def timing_advice(jp) -> Any:
            call_log.append("start")
            result = await jp.proceed()
            call_log.append("end")
            return f"timed:{result}"

        class Service:
            @Around(timing_advice)
            async def process(self) -> str:
                call_log.append("process")
                return "done"

        service = Service()
        proxied = create_component_proxy(service)

        result = await proxied.process()

        assert call_log == ["start", "process", "end"]
        assert result == "timed:done"

    @pytest.mark.asyncio
    async def test_proxy_with_multiple_decorators(self):
        """여러 데코레이터가 order 순으로 적용"""
        call_log = []

        async def outer_advice(jp) -> Any:
            call_log.append("outer:start")
            result = await jp.proceed()
            call_log.append("outer:end")
            return result

        async def inner_advice(jp) -> Any:
            call_log.append("inner:start")
            result = await jp.proceed()
            call_log.append("inner:end")
            return result

        class Service:
            @Around(outer_advice, order=10)
            @Around(inner_advice, order=20)
            async def multi_wrapped(self) -> str:
                call_log.append("method")
                return "done"

        service = Service()
        proxied = create_component_proxy(service)

        await proxied.multi_wrapped()

        # order가 낮은 outer가 먼저 (외부에서 감쌈)
        assert call_log == [
            "outer:start",
            "inner:start",
            "method",
            "inner:end",
            "outer:end",
        ]

    @pytest.mark.asyncio
    async def test_non_decorated_methods_not_proxied(self):
        """데코레이터 없는 메서드는 프록시 안됨"""

        class Service:
            async def normal_method(self) -> str:
                return "normal"

            @Before(lambda inv: None)
            async def decorated_method(self) -> str:
                return "decorated"

        service = Service()
        proxied = create_component_proxy(service)

        # decorated_method는 ProxiedMethod
        from bloom.core.aop import ProxiedMethod

        assert isinstance(proxied.decorated_method, ProxiedMethod)

        # normal_method는 원래 메서드 그대로
        assert not isinstance(proxied.normal_method, ProxiedMethod)


class TestInterceptorRegistry:
    """InterceptorRegistry 테스트"""

    @pytest.mark.asyncio
    async def test_global_interceptor(self):
        """글로벌 인터셉터는 모든 메서드에 적용"""
        call_log = []

        class LoggingInterceptor(MethodInterceptor):
            order = 0

            async def intercept(self, inv, proceed):
                call_log.append(f"global:{inv.method_name}")
                return await proceed()

        registry = get_interceptor_registry()
        registry.add_global_interceptor(LoggingInterceptor())

        class Service:
            async def method_a(self) -> str:
                return "a"

            async def method_b(self) -> str:
                return "b"

        service = Service()
        proxied = create_component_proxy(service)

        await proxied.method_a()
        await proxied.method_b()

        assert call_log == ["global:method_a", "global:method_b"]

    def test_custom_interceptor_factory(self):
        """커스텀 인터셉터 팩토리 등록"""
        registry = get_interceptor_registry()

        class MyInterceptor(MethodInterceptor):
            def __init__(self, config: dict):
                self.config = config
                self.order = 0

            async def intercept(self, inv, proceed):
                return await proceed()

        @registry.register_factory("my_type")
        def my_factory(info: InterceptorInfo) -> MethodInterceptor:
            return MyInterceptor(info.metadata)

        descriptor = MethodDescriptor()
        descriptor.add_interceptor(
            InterceptorInfo(
                interceptor_type="my_type",
                metadata={"key": "value"},
            )
        )

        interceptors = registry.create_interceptors_from_descriptor(descriptor)

        assert len(interceptors) == 1
        assert isinstance(interceptors[0], MyInterceptor)
        assert interceptors[0].config == {"key": "value"}


class TestRealWorldScenarios:
    """실제 사용 시나리오 테스트"""

    @pytest.mark.asyncio
    async def test_transactional_like_behavior(self):
        """트랜잭션과 유사한 동작 테스트"""
        tx_log = []

        async def tx_advice(jp) -> Any:
            tx_log.append("tx:begin")
            try:
                result = await jp.proceed()
                tx_log.append("tx:commit")
                return result
            except Exception:
                tx_log.append("tx:rollback")
                raise

        class UserService:
            @Around(tx_advice, order=-100)
            async def create_user(self, name: str) -> dict:
                tx_log.append(f"create:{name}")
                return {"name": name}

            @Around(tx_advice, order=-100)
            async def failing_method(self) -> None:
                tx_log.append("failing")
                raise ValueError("intentional")

        service = UserService()
        proxied = create_component_proxy(service)

        # 정상 케이스
        result = await proxied.create_user("Alice")
        assert result == {"name": "Alice"}
        assert tx_log == ["tx:begin", "create:Alice", "tx:commit"]

        # 예외 케이스
        tx_log.clear()
        with pytest.raises(ValueError):
            await proxied.failing_method()

        assert tx_log == ["tx:begin", "failing", "tx:rollback"]

    @pytest.mark.asyncio
    async def test_combined_decorators_scenario(self):
        """@Transactional + @Cacheable + @Logged 조합 시나리오"""
        execution_log = []

        # 각 인터셉터 시뮬레이션
        async def tx_advice(jp) -> Any:
            execution_log.append("TX:start")
            result = await jp.proceed()
            execution_log.append("TX:commit")
            return result

        async def cache_advice(jp) -> Any:
            execution_log.append("CACHE:check")
            result = await jp.proceed()
            execution_log.append("CACHE:store")
            return result

        async def log_advice(jp) -> Any:
            execution_log.append("LOG:before")
            result = await jp.proceed()
            execution_log.append("LOG:after")
            return result

        class ProductService:
            @Around(tx_advice, order=-100)  # 가장 먼저 (외부)
            @Around(cache_advice, order=-50)  # 그 다음
            @Around(log_advice, order=100)  # 가장 나중 (내부)
            async def get_product(self, id: int) -> dict:
                execution_log.append(f"DB:fetch:{id}")
                return {"id": id, "name": "Product"}

        service = ProductService()
        proxied = create_component_proxy(service)

        result = await proxied.get_product(1)

        # 예상 순서: TX -> CACHE -> LOG -> Method -> LOG -> CACHE -> TX
        assert execution_log == [
            "TX:start",
            "CACHE:check",
            "LOG:before",
            "DB:fetch:1",
            "LOG:after",
            "CACHE:store",
            "TX:commit",
        ]
        assert result == {"id": 1, "name": "Product"}
