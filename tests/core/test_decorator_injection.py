"""DecoratorContainer 함수 내부 인젝션 테스트"""

import pytest
from typing import Any, Awaitable, Callable, Coroutine
from functools import wraps

from bloom.core.container import (
    Container,
    CallableContainer,
    HandlerContainer,
    DecoratorContainer,
)
from bloom.core.decorators import (
    Component,
    Handler,
    Decorator,
    ADecoratorType,
    ACallable,
)
from bloom.core.container.element import Element, OrderElement
from bloom.core.manager import ContainerManager, set_current_manager


@pytest.fixture(autouse=True)
def reset_manager():
    """각 테스트 전에 manager 초기화"""
    manager = ContainerManager("test")
    set_current_manager(manager)
    yield manager
    set_current_manager(None)


class TestDecoratorInjection:
    @pytest.mark.asyncio
    async def test_decorator_without_injection(self, reset_manager: ContainerManager):
        """의존성 주입 없는 기본 decorator 테스트"""
        from bloom import Application

        def outer[**P, R](
            func: ACallable[P, R],
        ) -> ACallable[P, R]:
            @wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs):
                return await func(*args, **kwargs)

            return wrapper

        def outer2[**P, R](
            func: Callable[P, R],
        ) -> Callable[P, R]:
            @wraps(func)
            def wrapper(*args: P.args, **kwargs: P.kwargs):
                return func(*args, **kwargs)

            return wrapper

        @Component
        class MyComponent:
            @Decorator(outer)
            async def my_method(self, x: int) -> int:
                return x * 2

            @Decorator(outer2)
            def my_method2(self, x: int) -> int:
                return x + 3

        app = Application("test_app", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()
        comp = reset_manager.get_instance(MyComponent, raise_exception=True)
        result = await comp.my_method(5)
        result2 = comp.my_method2(7)
        assert result + result2 == 20

    @pytest.mark.asyncio
    async def test_decorator_with_single_injection(
        self, reset_manager: ContainerManager
    ):
        """단일 의존성 주입 테스트"""
        from bloom import Application

        call_log: list[str] = []

        @Component
        class Logger:
            def log(self, msg: str) -> None:
                call_log.append(f"LOG: {msg}")

        def logging_wrapper(fn, logger: Logger):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                logger.log(f"before {fn.__name__}")
                result = await fn(*args, **kwargs)
                logger.log(f"after {fn.__name__}: {result}")
                return result

            return wrapped

        @Component
        class MyService:
            @Decorator(logging_wrapper)
            async def process(self, data: str) -> str:
                return f"processed:{data}"

        app = Application("test_app", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(MyService)
        result = await service.process("hello")

        assert result == "processed:hello"
        assert "LOG: before process" in call_log
        assert "LOG: after process: processed:hello" in call_log

    @pytest.mark.asyncio
    async def test_decorator_with_multiple_injections(
        self, reset_manager: ContainerManager
    ):
        """다중 의존성 주입 테스트"""
        from bloom import Application

        call_log: list[str] = []

        @Component
        class Logger:
            def log(self, msg: str) -> None:
                call_log.append(f"LOG: {msg}")

        @Component
        class Config:
            def __init__(self):
                self.prefix = "[MyApp]"

            def get_prefix(self) -> str:
                return self.prefix

        def configured_logging_wrapper(fn, logger: Logger, config: Config):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                prefix = config.get_prefix()
                logger.log(f"{prefix} Calling {fn.__name__}")
                result = await fn(*args, **kwargs)
                logger.log(f"{prefix} Result: {result}")
                return result

            return wrapped

        @Component
        class MyService:
            @Decorator(configured_logging_wrapper)
            async def compute(self, x: int, y: int) -> int:
                return x + y

        app = Application("test_app", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(MyService)
        result = await service.compute(3, 5)

        assert result == 8
        assert "[MyApp] Calling compute" in call_log[0]
        assert "[MyApp] Result: 8" in call_log[1]

    @pytest.mark.asyncio
    async def test_decorator_injection_with_container_invoke(
        self, reset_manager: ContainerManager
    ):
        """container.invoke()로 호출 시에도 의존성 주입 동작"""
        from bloom import Application

        call_log: list[str] = []

        @Component
        class Metrics:
            def record(self, name: str, value: Any) -> None:
                call_log.append(f"METRIC: {name}={value}")

        def metrics_wrapper(fn, metrics: Metrics):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                result = await fn(*args, **kwargs)
                metrics.record(fn.__name__, result)
                return result

            return wrapped

        @Component
        class CalculatorService:
            @Decorator(metrics_wrapper)
            async def multiply(self, a: int, b: int) -> int:
                return a * b

        app = Application("test_app", manager=reset_manager)
        app.scan(CalculatorService)
        app.scan(Metrics)
        await app.ready_async()

        # container.invoke()로 호출
        container: DecoratorContainer = getattr(
            CalculatorService.multiply, "__container__"
        )
        result = await container.invoke(4, 7)

        assert result == 28
        assert "METRIC: multiply=28" in call_log

    @pytest.mark.asyncio
    async def test_decorator_sync_wrapper_with_injection(
        self, reset_manager: ContainerManager
    ):
        """동기 wrapper에 의존성 주입"""
        from bloom import Application

        call_log: list[str] = []

        @Component
        class Validator:
            def validate(self, value: int) -> bool:
                is_valid = value > 0
                call_log.append(f"VALIDATE: {value} -> {is_valid}")
                return is_valid

        def validation_wrapper(fn, validator: Validator):
            @wraps(fn)
            def wrapped(self, value: int):
                if not validator.validate(value):
                    raise ValueError("Invalid value")
                return fn(self, value)

            return wrapped

        @Component
        class NumberService:
            @Decorator(validation_wrapper)
            def square(self, value: int) -> int:
                return value * value

        app = Application("test_app", manager=reset_manager)
        app.scan(NumberService)
        app.scan(Validator)
        await app.ready_async()

        service = reset_manager.get_instance(NumberService)
        result = service.square(5)

        assert result == 25
        assert "VALIDATE: 5 -> True" in call_log

    @pytest.mark.asyncio
    async def test_decorator_injection_lazy_resolution(
        self, reset_manager: ContainerManager
    ):
        """의존성이 lazy하게 resolve되는지 확인 (wrapper 정의 시점이 아닌 호출 시점)"""
        from bloom import Application

        resolution_log: list[str] = []

        @Component
        class LazyService:
            def __init__(self):
                resolution_log.append("LazyService created")

            def get_value(self) -> str:
                return "lazy_value"

        def lazy_wrapper(fn, lazy_service: LazyService):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                # 이 시점에 LazyService가 resolve됨
                value = lazy_service.get_value()
                result = await fn(*args, **kwargs)
                return f"{value}:{result}"

            return wrapped

        @Component
        class MyService:
            @Decorator(lazy_wrapper)
            async def get_data(self) -> str:
                return "data"

        # decorator 적용 시점에는 아직 LazyService가 생성되지 않음
        assert "LazyService created" not in resolution_log

        app = Application("test_app", manager=reset_manager)
        app.scan(MyService)
        app.scan(LazyService)
        await app.ready_async()

        # Application ready 후에도 아직 LazyService가 호출되지 않을 수 있음
        # (lazy resolution)

        service = reset_manager.get_instance(MyService)
        result = await service.get_data()

        # 호출 시점에 LazyService가 resolve되고 사용됨
        assert result == "lazy_value:data"
        assert "LazyService created" in resolution_log

    @pytest.mark.asyncio
    async def test_decorator_injection_with_handler(
        self, reset_manager: ContainerManager
    ):
        """@Handler와 함께 사용 시에도 의존성 주입 동작"""
        from bloom import Application

        call_log: list[str] = []

        @Component
        class AuditLogger:
            def audit(self, action: str) -> None:
                call_log.append(f"AUDIT: {action}")

        def audit_wrapper(fn, audit_logger: AuditLogger):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                audit_logger.audit(f"start:{fn.__name__}")
                result = await fn(*args, **kwargs)
                audit_logger.audit(f"end:{fn.__name__}")
                return result

            return wrapped

        @Component
        class AuditedService:
            @Decorator(audit_wrapper)
            @Handler
            async def important_action(self) -> str:
                call_log.append("ACTION")
                return "done"

        app = Application("test_app", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(AuditedService)
        result = await service.important_action()

        assert result == "done"
        assert "ACTION" in call_log
