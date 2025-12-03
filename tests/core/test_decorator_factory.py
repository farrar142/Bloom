"""
DecoratorFactory 테스트

일반 파이썬 데코레이터를 AOP 어노테이션으로 변환하는 기능 테스트.
"""

import pytest
import time
from functools import wraps
from typing import Any, Callable

from bloom.core.aop import (
    DecoratorFactory,
    SimpleDecoratorFactory,
    InjectableDecoratorFactory,
    FlatDecorator,
    create_annotation,
    create_injectable_annotation,
    create_component_proxy,
    get_method_descriptor,
    reset_interceptor_registry,
    MethodInvocation,
)


@pytest.fixture(autouse=True)
def reset_registry():
    """각 테스트 전후에 레지스트리 초기화"""
    reset_interceptor_registry()
    yield
    reset_interceptor_registry()


class TestDecoratorFactory:
    """DecoratorFactory 테스트"""

    @pytest.mark.asyncio
    async def test_basic_decorator_factory(self):
        """기본 DecoratorFactory 동작"""
        call_log = []

        # 1. 일반 파이썬 데코레이터 정의
        def rate_limited(limit: int, window: int = 60):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    call_log.append(f"rate_limit_check: limit={limit}, window={window}")
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        # 2. AOP 어노테이션으로 변환
        RateLimited = DecoratorFactory(rate_limited, order=-50)

        # 3. 사용
        class MyService:
            @RateLimited(limit=100, window=30)
            async def api_call(self) -> str:
                call_log.append("api_call executed")
                return "success"

        # 4. 프록시 없이 직접 호출 (파이썬 데코레이터로 동작)
        service = MyService()
        result = await service.api_call()

        assert result == "success"
        assert "rate_limit_check: limit=100, window=30" in call_log
        assert "api_call executed" in call_log

    @pytest.mark.asyncio
    async def test_decorator_without_parentheses(self):
        """@RateLimited (괄호 없이) 사용"""
        call_log = []

        # 기본값이 있는 데코레이터
        def logged(level: str = "INFO", include_result: bool = False):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    call_log.append(f"[{level}] calling")
                    result = await func(*args, **kwargs)
                    if include_result:
                        call_log.append(f"[{level}] result: {result}")
                    return result

                return wrapper

            return decorator

        Logged = DecoratorFactory(logged)

        class MyService:
            # 괄호 없이 사용 - 기본값 적용
            @Logged
            async def method1(self) -> str:
                return "result1"

            # 빈 괄호 - 기본값 적용
            @Logged()
            async def method2(self) -> str:
                return "result2"

            # 인자와 함께
            @Logged(level="DEBUG", include_result=True)
            async def method3(self) -> str:
                return "result3"

        service = MyService()

        await service.method1()
        assert "[INFO] calling" in call_log

        call_log.clear()
        await service.method2()
        assert "[INFO] calling" in call_log

        call_log.clear()
        await service.method3()
        assert "[DEBUG] calling" in call_log
        assert "[DEBUG] result: result3" in call_log

    @pytest.mark.asyncio
    async def test_decorator_with_method_arguments(self):
        """인자를 받는 메서드에서 데코레이터 동작 테스트"""
        call_log = []

        def logged(level: str = "INFO"):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    # args[0]은 self이므로 args[1:]부터가 실제 인자
                    call_log.append(f"[{level}] args={args[1:]}, kwargs={kwargs}")
                    result = await func(*args, **kwargs)
                    call_log.append(f"[{level}] result={result}")
                    return result

                return wrapper

            return decorator

        Logged = DecoratorFactory(logged)

        class Calculator:
            @Logged
            async def add(self, a: int, b: int) -> int:
                return a + b

            @Logged()
            async def multiply(self, x: int, y: int, z: int = 1) -> int:
                return x * y * z

            @Logged(level="DEBUG")
            async def divide(self, numerator: float, denominator: float) -> float:
                if denominator == 0:
                    raise ValueError("Cannot divide by zero")
                return numerator / denominator

            @Logged(level="TRACE")
            async def greet(self, name: str, *, greeting: str = "Hello") -> str:
                return f"{greeting}, {name}!"

        calc = Calculator()

        # 1. 위치 인자 테스트
        result = await calc.add(3, 5)
        assert result == 8
        assert "[INFO] args=(3, 5), kwargs={}" in call_log
        assert "[INFO] result=8" in call_log

        call_log.clear()

        # 2. 위치 인자 + 기본값 인자 테스트
        result = await calc.multiply(2, 3)
        assert result == 6
        assert "[INFO] args=(2, 3), kwargs={}" in call_log

        call_log.clear()

        # 3. 위치 인자 + 키워드 인자 테스트
        result = await calc.multiply(2, 3, z=4)
        assert result == 24
        assert "[INFO] args=(2, 3), kwargs={'z': 4}" in call_log

        call_log.clear()

        # 4. 데코레이터 인자 + 메서드 인자 테스트
        result = await calc.divide(10.0, 2.0)
        assert result == 5.0
        assert "[DEBUG] args=(10.0, 2.0), kwargs={}" in call_log
        assert "[DEBUG] result=5.0" in call_log

        call_log.clear()

        # 5. 키워드 전용 인자 테스트
        result = await calc.greet("World", greeting="Hi")
        assert result == "Hi, World!"
        assert "[TRACE] args=('World',), kwargs={'greeting': 'Hi'}" in call_log
        assert "[TRACE] result=Hi, World!" in call_log

        call_log.clear()

        # 6. 기본값 사용 테스트
        result = await calc.greet("Alice")
        assert result == "Hello, Alice!"
        assert "[TRACE] args=('Alice',), kwargs={}" in call_log

    @pytest.mark.asyncio
    async def test_decorator_factory_with_proxy(self):
        """DecoratorFactory + ComponentProxy 동작"""
        call_log = []

        def logging_decorator(level: str = "INFO"):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    call_log.append(f"[{level}] before")
                    result = await func(*args, **kwargs)
                    call_log.append(f"[{level}] after: {result}")
                    return result

                return wrapper

            return decorator

        Logged = DecoratorFactory(logging_decorator, order=100)

        class MyService:
            @Logged(level="DEBUG")
            async def do_something(self) -> str:
                call_log.append("method executed")
                return "done"

        service = MyService()
        proxied = create_component_proxy(service)

        result = await proxied.do_something()

        assert result == "done"
        assert "[DEBUG] before" in call_log
        assert "method executed" in call_log
        assert "[DEBUG] after: done" in call_log

    @pytest.mark.asyncio
    async def test_decorator_preserves_metadata(self):
        """DecoratorFactory가 메타데이터를 보존"""

        def simple_decorator(name: str):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        MyDecorator = DecoratorFactory(simple_decorator)

        class MyService:
            @MyDecorator(name="test")
            async def my_method(self) -> str:
                """This is my method"""
                return "result"

        # 메타데이터 확인
        descriptor = get_method_descriptor(MyService.my_method)
        assert descriptor is not None
        assert len(descriptor.interceptors) == 1
        # 키워드 인자로 전달되었으므로 kwargs에 저장됨
        assert descriptor.interceptors[0].metadata["kwargs"] == {"name": "test"}

    @pytest.mark.asyncio
    async def test_multiple_decorator_factories(self):
        """여러 DecoratorFactory 조합"""
        execution_order = []

        def first_decorator(name: str):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    execution_order.append(f"{name}:before")
                    result = await func(*args, **kwargs)
                    execution_order.append(f"{name}:after")
                    return result

                return wrapper

            return decorator

        def second_decorator(name: str):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    execution_order.append(f"{name}:before")
                    result = await func(*args, **kwargs)
                    execution_order.append(f"{name}:after")
                    return result

                return wrapper

            return decorator

        First = DecoratorFactory(first_decorator, order=10)
        Second = DecoratorFactory(second_decorator, order=20)

        class MyService:
            @First(name="first")
            @Second(name="second")
            async def chained_method(self) -> str:
                execution_order.append("method")
                return "done"

        service = MyService()

        # 직접 호출 시 파이썬 데코레이터 순서 (위에서 아래로 감쌈)
        # First가 Second를 감쌈: First -> Second -> method
        result = await service.chained_method()

        assert result == "done"
        assert execution_order == [
            "first:before",
            "second:before",
            "method",
            "second:after",
            "first:after",
        ]


class TestSimpleDecoratorFactory:
    """SimpleDecoratorFactory 테스트"""

    @pytest.mark.asyncio
    async def test_simple_factory_preserves_original_decorator(self):
        """SimpleDecoratorFactory는 원본 데코레이터를 그대로 적용"""
        call_count = {"value": 0}

        def counter_decorator(name: str):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    call_count["value"] += 1
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        Counter = SimpleDecoratorFactory(counter_decorator)

        class MyService:
            @Counter(name="test")
            async def counted_method(self) -> int:
                return call_count["value"]

        service = MyService()

        # 직접 호출
        result1 = await service.counted_method()
        result2 = await service.counted_method()

        assert result1 == 1
        assert result2 == 2


class TestCreateAnnotation:
    """create_annotation 헬퍼 테스트"""

    @pytest.mark.asyncio
    async def test_create_annotation_helper(self):
        """create_annotation 헬퍼 함수 동작"""
        executed = {"value": False}

        def my_decorator(message: str):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    executed["value"] = True
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        MyAnnotation = create_annotation(my_decorator, order=-10)

        class MyService:
            @MyAnnotation(message="hello")
            async def annotated_method(self) -> str:
                return "world"

        service = MyService()
        result = await service.annotated_method()

        assert result == "world"
        assert executed["value"] is True


class TestRealWorldScenario:
    """실제 사용 시나리오 테스트"""

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_factory(self):
        """Rate Limit 데코레이터 팩토리 시나리오"""
        calls: dict[str, list[float]] = {}

        def rate_limited(limit: int, window: int = 60):
            """일반 파이썬 rate limit 데코레이터"""

            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    key = func.__name__
                    now = time.time()

                    if key not in calls:
                        calls[key] = []

                    # 오래된 호출 제거
                    calls[key] = [t for t in calls[key] if now - t < window]

                    if len(calls[key]) >= limit:
                        raise RuntimeError(
                            f"Rate limit exceeded: {limit} per {window}s"
                        )

                    calls[key].append(now)
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        # AOP 어노테이션으로 변환
        RateLimited = DecoratorFactory(rate_limited, order=-80)

        class ApiService:
            @RateLimited(limit=3, window=60)
            async def call_api(self) -> str:
                return "api response"

        service = ApiService()

        # 3번까지는 성공
        assert await service.call_api() == "api response"
        assert await service.call_api() == "api response"
        assert await service.call_api() == "api response"

        # 4번째는 실패
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await service.call_api()

    @pytest.mark.asyncio
    async def test_retry_decorator_factory(self):
        """Retry 데코레이터 팩토리 시나리오"""
        attempt_count = {"value": 0}

        def retry(max_attempts: int = 3, delay: float = 0.01):
            """일반 파이썬 retry 데코레이터"""

            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    last_error = None
                    for attempt in range(max_attempts):
                        try:
                            return await func(*args, **kwargs)
                        except Exception as e:
                            last_error = e
                            if attempt < max_attempts - 1:
                                await __import__("asyncio").sleep(delay)
                    raise last_error

                return wrapper

            return decorator

        Retry = DecoratorFactory(retry, order=-90)

        class UnstableService:
            @Retry(max_attempts=3)
            async def unstable_method(self) -> str:
                attempt_count["value"] += 1
                if attempt_count["value"] < 3:
                    raise ValueError("Not ready yet")
                return "success"

        service = UnstableService()
        result = await service.unstable_method()

        assert result == "success"
        assert attempt_count["value"] == 3  # 3번째에 성공

    @pytest.mark.asyncio
    async def test_combined_decorator_factories_scenario(self):
        """여러 데코레이터 팩토리 조합 시나리오"""
        log = []

        # 1. 로깅 데코레이터
        def logged(level: str = "INFO"):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    log.append(f"[{level}] Calling {func.__name__}")
                    result = await func(*args, **kwargs)
                    log.append(f"[{level}] {func.__name__} returned: {result}")
                    return result

                return wrapper

            return decorator

        # 2. 타이밍 데코레이터
        def timed(name: str | None = None):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    metric_name = name or func.__name__
                    start = time.time()
                    result = await func(*args, **kwargs)
                    elapsed = time.time() - start
                    log.append(f"[TIMING] {metric_name}: {elapsed:.4f}s")
                    return result

                return wrapper

            return decorator

        Logged = DecoratorFactory(logged, order=100)
        Timed = DecoratorFactory(timed, order=50)

        class ComplexService:
            @Logged(level="DEBUG")
            @Timed(name="complex_operation")
            async def complex_method(self) -> str:
                return "completed"

        service = ComplexService()
        result = await service.complex_method()

        assert result == "completed"
        # Logged(100) 외부, Timed(50) 내부이지만 파이썬 데코레이터 순서는 위→아래
        # @Logged가 @Timed를 감쌈
        assert log[0].startswith("[DEBUG] Calling")
        assert "[TIMING]" in log[1]
        assert "returned: completed" in log[2]


class TestInjectableDecoratorFactory:
    """InjectableDecoratorFactory 테스트 - 데코레이터 내 DI 지원"""

    @pytest.mark.asyncio
    async def test_injectable_decorator_basic(self):
        """기본 InjectableDecoratorFactory 동작 - DI 없이"""
        call_log = []

        # DI 주입 가능한 데코레이터 (rate_service가 주입 대상)
        class RateLimitService:
            async def check(self, key: str, limit: int) -> bool:
                call_log.append(f"rate_check: {key}, limit={limit}")
                return True

        def rate_limited(
            limit: int = 100,
            *,
            rate_service: RateLimitService | None = None,
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    if rate_service:
                        key = func.__name__
                        allowed = await rate_service.check(key, limit)
                        if not allowed:
                            raise RuntimeError("Rate limit exceeded")
                    call_log.append(f"executing with limit={limit}")
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        RateLimited = InjectableDecoratorFactory(rate_limited)

        class MyService:
            @RateLimited(limit=50)
            async def api_call(self, data: str) -> str:
                call_log.append(f"api_call({data})")
                return f"result: {data}"

        service = MyService()

        # DI 없이 직접 호출 - rate_service가 None이므로 체크 스킵
        result = await service.api_call("test")

        assert result == "result: test"
        assert "executing with limit=50" in call_log
        assert "api_call(test)" in call_log

    @pytest.mark.asyncio
    async def test_injectable_decorator_with_manual_injection(self):
        """InjectableDecoratorFactory - 수동으로 의존성 전달"""
        call_log = []

        class CacheService:
            def __init__(self, prefix: str = "cache"):
                self.prefix = prefix
                self.store: dict[str, Any] = {}

            async def get(self, key: str) -> Any | None:
                full_key = f"{self.prefix}:{key}"
                call_log.append(f"cache_get: {full_key}")
                return self.store.get(full_key)

            async def set(self, key: str, value: Any) -> None:
                full_key = f"{self.prefix}:{key}"
                call_log.append(f"cache_set: {full_key}={value}")
                self.store[full_key] = value

        def cached(
            ttl: int = 300,
            key_prefix: str = "",
            *,
            cache: CacheService | None = None,
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    if cache:
                        cache_key = f"{key_prefix}:{func.__name__}"
                        cached_value = await cache.get(cache_key)
                        if cached_value is not None:
                            call_log.append(f"cache_hit: {cache_key}")
                            return cached_value

                    result = await func(*args, **kwargs)

                    if cache:
                        await cache.set(cache_key, result)

                    return result

                return wrapper

            return decorator

        Cached = InjectableDecoratorFactory(cached)

        # 수동으로 cache 서비스 전달
        my_cache = CacheService(prefix="my")

        class DataService:
            @Cached(ttl=60, key_prefix="data", cache=my_cache)
            async def get_data(self, id: int) -> dict:
                call_log.append(f"fetching data {id}")
                return {"id": id, "name": f"Item {id}"}

        service = DataService()

        # 첫 번째 호출 - 캐시 미스
        result1 = await service.get_data(1)
        assert result1 == {"id": 1, "name": "Item 1"}
        assert "cache_get: my:data:get_data" in call_log
        assert "fetching data 1" in call_log
        assert "cache_set: my:data:get_data=" in call_log[-1]

        call_log.clear()

        # 두 번째 호출 - 캐시 히트
        result2 = await service.get_data(1)
        assert result2 == {"id": 1, "name": "Item 1"}
        assert "cache_hit: data:get_data" in call_log
        assert "fetching data 1" not in call_log

    @pytest.mark.asyncio
    async def test_injectable_decorator_metadata_preserved(self):
        """InjectableDecoratorFactory 메타데이터 보존"""

        class LogService:
            pass

        def logged(
            level: str = "INFO",
            *,
            logger: LogService | None = None,
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        Logged = InjectableDecoratorFactory(logged)

        class MyService:
            @Logged(level="DEBUG")
            async def my_method(self) -> str:
                return "done"

        # 메타데이터 확인
        descriptor = get_method_descriptor(MyService.my_method)
        assert descriptor is not None
        assert len(descriptor.interceptors) == 1

        info = descriptor.interceptors[0]
        assert info.metadata["kwargs"] == {"level": "DEBUG"}
        assert "logger" in info.metadata["injectable_params"]

    @pytest.mark.asyncio
    async def test_injectable_without_parentheses(self):
        """@Injectable 괄호 없이 사용"""
        call_log = []

        class MetricService:
            pass

        def timed(
            name: str = "default",
            *,
            metrics: MetricService | None = None,
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    call_log.append(f"timing: {name}")
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        Timed = InjectableDecoratorFactory(timed)

        class MyService:
            @Timed  # 괄호 없이
            async def method1(self) -> str:
                return "result1"

            @Timed()  # 빈 괄호
            async def method2(self) -> str:
                return "result2"

            @Timed(name="custom")  # 인자와 함께
            async def method3(self) -> str:
                return "result3"

        service = MyService()

        await service.method1()
        assert "timing: default" in call_log

        call_log.clear()
        await service.method2()
        assert "timing: default" in call_log

        call_log.clear()
        await service.method3()
        assert "timing: custom" in call_log

    @pytest.mark.asyncio
    async def test_injectable_with_method_arguments(self):
        """InjectableDecoratorFactory - 메서드 인자와 함께 동작"""
        call_log = []

        class ValidationService:
            async def validate(self, data: dict) -> bool:
                call_log.append(f"validating: {data}")
                return True

        def validated(
            schema: str = "default",
            *,
            validator: ValidationService | None = None,
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    call_log.append(f"schema: {schema}")
                    if validator and "data" in kwargs:
                        await validator.validate(kwargs["data"])
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        Validated = InjectableDecoratorFactory(validated)

        # 수동으로 validator 전달
        my_validator = ValidationService()

        class UserService:
            @Validated(schema="user", validator=my_validator)
            async def create_user(self, name: str, data: dict) -> dict:
                call_log.append(f"creating user: {name}")
                return {"name": name, **data}

        service = UserService()

        result = await service.create_user("Alice", data={"age": 30})

        assert result == {"name": "Alice", "age": 30}
        assert "schema: user" in call_log
        assert "validating: {'age': 30}" in call_log
        assert "creating user: Alice" in call_log

    @pytest.mark.asyncio
    async def test_create_injectable_annotation_helper(self):
        """create_injectable_annotation 헬퍼 함수 테스트"""
        call_log = []

        class AuditService:
            async def log(self, action: str, data: Any) -> None:
                call_log.append(f"audit: {action} - {data}")

        def audited(
            action: str = "unknown",
            *,
            audit_service: AuditService | None = None,
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    result = await func(*args, **kwargs)
                    if audit_service:
                        await audit_service.log(action, result)
                    call_log.append(f"audited action: {action}")
                    return result

                return wrapper

            return decorator

        Audited = create_injectable_annotation(audited, order=-50)

        # 수동 주입
        my_audit = AuditService()

        class OrderService:
            @Audited(action="order.created", audit_service=my_audit)
            async def create_order(self, item: str, qty: int) -> dict:
                return {"item": item, "qty": qty}

        service = OrderService()
        result = await service.create_order("Widget", 5)

        assert result == {"item": "Widget", "qty": 5}
        assert "audit: order.created - {'item': 'Widget', 'qty': 5}" in call_log
        assert "audited action: order.created" in call_log


class TestFlatDecorator:
    """FlatDecorator 테스트 - 삼중 중첩 없는 평탄화된 데코레이터"""

    @pytest.mark.asyncio
    async def test_flat_decorator_basic(self):
        """기본 FlatDecorator 동작"""
        call_log = []

        # 평탄화된 데코레이터 함수 (삼중 중첩 없음!)
        async def logged(
            func: Callable,
            *args: Any,
            level: str = "INFO",
            **kwargs: Any,
        ) -> Any:
            call_log.append(f"[{level}] before")
            result = await func(*args, **kwargs)
            call_log.append(f"[{level}] after: {result}")
            return result

        Logged = FlatDecorator(logged)

        class MyService:
            @Logged(level="DEBUG")
            async def do_something(self) -> str:
                call_log.append("method executed")
                return "done"

        service = MyService()
        result = await service.do_something()

        assert result == "done"
        assert "[DEBUG] before" in call_log
        assert "method executed" in call_log
        assert "[DEBUG] after: done" in call_log

    @pytest.mark.asyncio
    async def test_flat_decorator_without_parentheses(self):
        """@Logged 괄호 없이 사용"""
        call_log = []

        async def timed(
            func: Callable,
            *args: Any,
            name: str = "default",
            **kwargs: Any,
        ) -> Any:
            start = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            call_log.append(f"[{name}] {elapsed:.4f}s")
            return result

        Timed = FlatDecorator(timed)

        class MyService:
            @Timed  # 괄호 없이
            async def method1(self) -> str:
                return "result1"

            @Timed()  # 빈 괄호
            async def method2(self) -> str:
                return "result2"

            @Timed(name="custom")  # 인자와 함께
            async def method3(self) -> str:
                return "result3"

        service = MyService()

        await service.method1()
        assert "[default]" in call_log[0]

        call_log.clear()
        await service.method2()
        assert "[default]" in call_log[0]

        call_log.clear()
        await service.method3()
        assert "[custom]" in call_log[0]

    @pytest.mark.asyncio
    async def test_flat_decorator_with_method_arguments(self):
        """메서드 인자와 함께 동작"""
        call_log = []

        async def validated(
            func: Callable,
            *args: Any,
            schema: str = "default",
            **kwargs: Any,
        ) -> Any:
            call_log.append(f"validating with schema: {schema}")
            call_log.append(f"args: {args[1:]}")  # args[0]은 self
            result = await func(*args, **kwargs)
            return result

        Validated = FlatDecorator(validated)

        class UserService:
            @Validated(schema="user")
            async def create_user(self, name: str, age: int) -> dict:
                return {"name": name, "age": age}

        service = UserService()
        result = await service.create_user("Alice", 30)

        assert result == {"name": "Alice", "age": 30}
        assert "validating with schema: user" in call_log
        assert "args: ('Alice', 30)" in call_log

    @pytest.mark.asyncio
    async def test_flat_decorator_rate_limit_example(self):
        """Rate Limit 예제 - 삼중 중첩 vs 평탄화 비교"""
        call_count = {"value": 0}

        # 평탄화된 rate_limited (단일 함수)
        async def rate_limited(
            func: Callable,
            *args: Any,
            limit: int = 100,
            window: int = 60,
            **kwargs: Any,
        ) -> Any:
            call_count["value"] += 1
            if call_count["value"] > limit:
                raise RuntimeError(f"Rate limit exceeded: {limit} per {window}s")
            return await func(*args, **kwargs)

        RateLimited = FlatDecorator(rate_limited)

        class ApiService:
            @RateLimited(limit=3)
            async def call_api(self) -> str:
                return "api response"

        service = ApiService()

        # 3번까지는 성공
        assert await service.call_api() == "api response"
        assert await service.call_api() == "api response"
        assert await service.call_api() == "api response"

        # 4번째는 실패
        with pytest.raises(RuntimeError, match="Rate limit exceeded"):
            await service.call_api()

    @pytest.mark.asyncio
    async def test_flat_decorator_retry_example(self):
        """Retry 예제"""
        attempt_count = {"value": 0}

        async def retry(
            func: Callable,
            *args: Any,
            max_attempts: int = 3,
            **kwargs: Any,
        ) -> Any:
            import asyncio

            last_error = None
            for attempt in range(max_attempts):
                try:
                    attempt_count["value"] += 1
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(0.01)
            raise last_error  # type: ignore

        Retry = FlatDecorator(retry)

        fail_until = {"count": 2}

        class UnstableService:
            @Retry(max_attempts=3)
            async def unstable_method(self) -> str:
                if fail_until["count"] > 0:
                    fail_until["count"] -= 1
                    raise ValueError("Not ready")
                return "success"

        service = UnstableService()
        result = await service.unstable_method()

        assert result == "success"
        assert attempt_count["value"] == 3

    @pytest.mark.asyncio
    async def test_flat_decorator_multiple(self):
        """여러 FlatDecorator 조합"""
        execution_order = []

        async def first(
            func: Callable,
            *args: Any,
            name: str = "first",
            **kwargs: Any,
        ) -> Any:
            execution_order.append(f"{name}:before")
            result = await func(*args, **kwargs)
            execution_order.append(f"{name}:after")
            return result

        async def second(
            func: Callable,
            *args: Any,
            name: str = "second",
            **kwargs: Any,
        ) -> Any:
            execution_order.append(f"{name}:before")
            result = await func(*args, **kwargs)
            execution_order.append(f"{name}:after")
            return result

        First = FlatDecorator(first, order=10)
        Second = FlatDecorator(second, order=20)

        class MyService:
            @First(name="A")
            @Second(name="B")
            async def chained_method(self) -> str:
                execution_order.append("method")
                return "done"

        service = MyService()
        result = await service.chained_method()

        assert result == "done"
        # 파이썬 데코레이터 순서: First가 Second를 감쌈
        assert execution_order == [
            "A:before",
            "B:before",
            "method",
            "B:after",
            "A:after",
        ]

    @pytest.mark.asyncio
    async def test_flat_decorator_preserves_metadata(self):
        """메타데이터 보존 확인"""

        async def my_handler(
            func: Callable,
            *args: Any,
            option: str = "default",
            **kwargs: Any,
        ) -> Any:
            return await func(*args, **kwargs)

        MyDecorator = FlatDecorator(my_handler)

        class MyService:
            @MyDecorator(option="custom")
            async def my_method(self) -> str:
                """This is my method"""
                return "result"

        descriptor = get_method_descriptor(MyService.my_method)
        assert descriptor is not None
        assert len(descriptor.interceptors) == 1
        assert descriptor.interceptors[0].metadata["kwargs"] == {"option": "custom"}

    def test_flat_decorator_sync_function(self):
        """동기 함수 지원 테스트"""
        call_log = []

        # 동기 핸들러
        def logged(
            func: Callable,
            *args: Any,
            level: str = "INFO",
            **kwargs: Any,
        ) -> Any:
            call_log.append(f"[{level}] before")
            result = func(*args, **kwargs)
            call_log.append(f"[{level}] after: {result}")
            return result

        Logged = FlatDecorator(logged)

        class MyService:
            @Logged(level="DEBUG")
            def sync_method(self, x: int, y: int) -> int:
                call_log.append("method executed")
                return x + y

        service = MyService()
        result = service.sync_method(3, 5)

        assert result == 8
        assert "[DEBUG] before" in call_log
        assert "method executed" in call_log
        assert "[DEBUG] after: 8" in call_log

    def test_flat_decorator_sync_without_parentheses(self):
        """동기 함수 - 괄호 없이 사용"""
        call_log = []

        def timed(
            func: Callable,
            *args: Any,
            name: str = "default",
            **kwargs: Any,
        ) -> Any:
            import time

            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            call_log.append(f"[{name}] {elapsed:.4f}s")
            return result

        Timed = FlatDecorator(timed)

        class Calculator:
            @Timed  # 괄호 없이
            def add(self, a: int, b: int) -> int:
                return a + b

            @Timed()  # 빈 괄호
            def subtract(self, a: int, b: int) -> int:
                return a - b

            @Timed(name="multiply_op")  # 인자와 함께
            def multiply(self, a: int, b: int) -> int:
                return a * b

        calc = Calculator()

        assert calc.add(1, 2) == 3
        assert "[default]" in call_log[0]

        call_log.clear()
        assert calc.subtract(5, 3) == 2
        assert "[default]" in call_log[0]

        call_log.clear()
        assert calc.multiply(4, 5) == 20
        assert "[multiply_op]" in call_log[0]


class TestDecoratorFactorySyncSupport:
    """DecoratorFactory 동기 함수 지원 테스트"""

    def test_decorator_factory_sync_function(self):
        """DecoratorFactory - 동기 함수 데코레이터"""
        call_log = []

        # 동기 데코레이터 팩토리 (삼중 중첩)
        def logged(level: str = "INFO"):
            def decorator(func):
                @wraps(func)
                def wrapper(*args, **kwargs):
                    call_log.append(f"[{level}] before")
                    result = func(*args, **kwargs)
                    call_log.append(f"[{level}] after: {result}")
                    return result

                return wrapper

            return decorator

        Logged = DecoratorFactory(logged)

        class Calculator:
            @Logged(level="DEBUG")
            def add(self, a: int, b: int) -> int:
                call_log.append("add executed")
                return a + b

        calc = Calculator()
        result = calc.add(10, 20)

        assert result == 30
        assert "[DEBUG] before" in call_log
        assert "add executed" in call_log
        assert "[DEBUG] after: 30" in call_log

    def test_decorator_factory_sync_without_parentheses(self):
        """DecoratorFactory - 동기 함수, 괄호 없이"""
        call_log = []

        def counter(name: str = "default"):
            def decorator(func):
                @wraps(func)
                def wrapper(*args, **kwargs):
                    call_log.append(f"[{name}] called")
                    return func(*args, **kwargs)

                return wrapper

            return decorator

        Counter = DecoratorFactory(counter)

        class Service:
            @Counter  # 괄호 없이
            def method1(self) -> str:
                return "result1"

            @Counter()  # 빈 괄호
            def method2(self) -> str:
                return "result2"

            @Counter(name="custom")  # 인자와 함께
            def method3(self) -> str:
                return "result3"

        service = Service()

        assert service.method1() == "result1"
        assert "[default] called" in call_log

        call_log.clear()
        assert service.method2() == "result2"
        assert "[default] called" in call_log

        call_log.clear()
        assert service.method3() == "result3"
        assert "[custom] called" in call_log


class TestInterceptorDIIntegration:
    """
    인터셉터에서 DI(의존성 주입) 통합 테스트.

    container_manager가 ProxiedMethod를 통해 인터셉터에 전달되어
    InjectableDecoratorFactory가 정상적으로 의존성을 주입하는지 테스트.
    """

    @pytest.mark.asyncio
    async def test_interceptor_with_container_manager_injection(self):
        """container_manager가 있을 때 의존성 주입 성공"""
        from bloom.core import Component, get_container_manager

        call_log = []

        # 주입받을 서비스 정의
        @Component
        class InjectionLogService:
            def log(self, message: str):
                call_log.append(f"LogService: {message}")

        # 주입을 사용하는 데코레이터 팩토리
        def logging_decorator(
            level: str = "INFO",
            *,
            log_service: InjectionLogService,  # DI로 주입됨
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    log_service.log(f"[{level}] Before {func.__name__}")
                    result = await func(*args, **kwargs)
                    log_service.log(f"[{level}] After {func.__name__}: {result}")
                    return result

                return wrapper

            return decorator

        # Injectable 어노테이션으로 변환
        LoggingAnnotation = InjectableDecoratorFactory(logging_decorator)

        # 데코레이터를 사용하는 클래스
        @Component
        class InjectionTestService:
            @LoggingAnnotation(level="DEBUG")
            async def do_work(self) -> str:
                call_log.append("do_work executed")
                return "work done"

        # get_container_manager로 글로벌 매니저 가져오기
        manager = get_container_manager()
        await manager.initialize()

        # 프록시 생성 (container_manager 전달!)
        service = await manager.get_instance_async(InjectionTestService)
        proxied_service = create_component_proxy(
            service,
            container_manager=manager,  # DI 컨테이너 전달
        )

        # 실행
        result = await proxied_service.do_work()

        # 검증
        assert result == "work done"
        # LogService가 제대로 주입되어 호출되었는지 확인
        assert "LogService: [DEBUG] Before do_work" in call_log
        assert "do_work executed" in call_log
        assert "LogService: [DEBUG] After do_work: work done" in call_log

    @pytest.mark.asyncio
    async def test_interceptor_without_container_manager(self):
        """container_manager 없이 프록시 - 주입 실패 시 에러 발생"""
        call_log = []

        # 주입받을 서비스 클래스 (컨테이너에 등록되지 않음)
        class AuditService:
            def audit(self, action: str):
                call_log.append(f"AuditService: {action}")

        # 필수 의존성을 사용하는 데코레이터 - 주입 안 되면 에러
        def audited(
            action: str = "unknown",
            *,
            audit_service: AuditService,  # 주입 필요
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    # audit_service가 주입되지 않으면 NameError 발생
                    audit_service.audit(f"Action: {action}")
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        Audited = InjectableDecoratorFactory(audited)

        class MyService:
            @Audited(action="test")
            async def do_something(self) -> str:
                return "done"

        service = MyService()
        # container_manager 없이 프록시 생성
        proxied_service = create_component_proxy(service)

        # 주입 실패로 audit_service 사용 시 에러 발생
        with pytest.raises((UnboundLocalError, NameError, TypeError)):
            await proxied_service.do_something()

    @pytest.mark.asyncio
    async def test_interceptor_with_optional_injection_and_fallback(self):
        """optional 주입 - 컨테이너에 없으면 기본값 사용"""
        from bloom.core import Component, get_container_manager

        call_log = []

        # 선택적 주입: 기본값으로 None 처리
        def optional_logging(
            prefix: str = "",
            *,
            logger: Any = None,  # 주입되지 않으면 None
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    if logger:
                        logger.log(f"{prefix} Before")
                    else:
                        call_log.append(f"{prefix} No logger - before")
                    result = await func(*args, **kwargs)
                    if logger:
                        logger.log(f"{prefix} After")
                    else:
                        call_log.append(f"{prefix} No logger - after")
                    return result

                return wrapper

            return decorator

        OptionalLogging = InjectableDecoratorFactory(optional_logging)

        @Component
        class OptionalTestService:
            @OptionalLogging(prefix="[OP]")
            async def operation(self) -> str:
                call_log.append("operation executed")
                return "result"

        # 글로벌 ContainerManager (Logger 미등록 상태)
        manager = get_container_manager()
        await manager.initialize()

        service = await manager.get_instance_async(OptionalTestService)
        proxied_service = create_component_proxy(service, container_manager=manager)

        result = await proxied_service.operation()

        # Logger가 없으므로 fallback 경로 실행
        assert result == "result"
        assert "[OP] No logger - before" in call_log
        assert "operation executed" in call_log
        assert "[OP] No logger - after" in call_log

    @pytest.mark.asyncio
    async def test_component_proxy_factory_with_container_manager(self):
        """ComponentProxyFactory가 container_manager를 전달하는지 테스트"""
        from bloom.core import Component, get_container_manager
        from bloom.core.aop import ComponentProxyFactory

        call_log = []

        @Component
        class ProxyMetricsService:
            def record(self, name: str, value: int):
                call_log.append(f"Metrics: {name}={value}")

        def metered_decorator(
            metric_name: str = "default",
            *,
            metrics: ProxyMetricsService,
        ):
            def decorator(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    metrics.record(metric_name, 1)
                    return await func(*args, **kwargs)

                return wrapper

            return decorator

        MeteredAnnotation = InjectableDecoratorFactory(metered_decorator)

        @Component
        class ProxyApiService:
            @MeteredAnnotation(metric_name="api_calls")
            async def call_api(self) -> str:
                call_log.append("API called")
                return "api result"

        # 글로벌 ContainerManager
        manager = get_container_manager()
        await manager.initialize()

        # ComponentProxyFactory 사용
        factory = ComponentProxyFactory(container_manager=manager)
        service = await manager.get_instance_async(ProxyApiService)
        proxied = factory.create_proxy(service)

        result = await proxied.call_api()

        assert result == "api result"
        assert "Metrics: api_calls=1" in call_log
        assert "API called" in call_log
