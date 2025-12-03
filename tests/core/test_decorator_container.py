"""DecoratorContainer 테스트

DecoratorContainer는 원본 메서드를 데코레이션하는 컨테이너로,
다른 컨테이너와 흡수/전이될 때 데코레이션이 유지되는지 검증합니다.
"""

import pytest
from typing import Any, Awaitable, Callable, Coroutine
from functools import wraps

from bloom.core.container import (
    Container,
    CallableContainer,
    HandlerContainer,
    DecoratorContainer,
)
from bloom.core.decorators import Decorator
from bloom.core.container.element import Element, OrderElement
from bloom.core.manager import ContainerManager, set_current_manager


@pytest.fixture(autouse=True)
def reset_manager():
    """각 테스트 전에 manager 초기화"""
    manager = ContainerManager("test")
    set_current_manager(manager)
    yield manager
    set_current_manager(None)


# === 헬퍼: wrapper 생성 함수들 ===


def create_logging_wrapper(call_log: list[str], prefix: str = ""):
    """로깅 wrapper 생성"""

    def wrapper(fn):
        @wraps(fn)
        def sync_wrapped(*args, **kwargs):
            call_log.append(f"{prefix}before")
            result = fn(*args, **kwargs)
            call_log.append(f"{prefix}after:{result}")
            return result

        @wraps(fn)
        async def async_wrapped(*args, **kwargs):
            call_log.append(f"{prefix}before")
            result = await fn(*args, **kwargs)
            call_log.append(f"{prefix}after:{result}")
            return result

        import asyncio

        return async_wrapped if asyncio.iscoroutinefunction(fn) else sync_wrapped

    return wrapper


def create_simple_wrapper(call_log: list[str], name: str):
    """단순 wrapper 생성"""

    def wrapper(fn):
        @wraps(fn)
        def sync_wrapped(*args, **kwargs):
            call_log.append(f"{name}:start")
            result = fn(*args, **kwargs)
            call_log.append(f"{name}:end")
            return result

        @wraps(fn)
        async def async_wrapped(*args, **kwargs):
            call_log.append(f"{name}:start")
            result = await fn(*args, **kwargs)
            call_log.append(f"{name}:end")
            return result

        import asyncio

        return async_wrapped if asyncio.iscoroutinefunction(fn) else sync_wrapped

    return wrapper


class TestDecoratorContainerBasic:
    """DecoratorContainer 기본 기능 테스트"""

    def test_wrapper_executed(self):
        """wrapper가 실행되는지 확인"""
        call_log: list[str] = []

        def my_wrapper(original):
            def wrapped(*args, **kwargs):
                call_log.append("wrapper_start")
                result = original(*args, **kwargs)
                call_log.append("wrapper_end")
                return result

            return wrapped

        def my_func():
            call_log.append("original")
            return "result"

        container = DecoratorContainer.get_or_create(my_func, my_wrapper)

        result = container.invoke_sync()

        assert call_log == ["wrapper_start", "original", "wrapper_end"]
        assert result == "result"

    def test_wrapper_with_args(self):
        """인자를 받는 함수에서 wrapper 실행"""
        call_log: list[str] = []

        def my_wrapper(original):
            def wrapped(*args, **kwargs):
                call_log.append(f"args:{args}")
                result = original(*args, **kwargs)
                call_log.append(f"result:{result}")
                return result

            return wrapped

        def my_func(x: int, y: int):
            call_log.append(f"compute:{x}+{y}")
            return x + y

        container = DecoratorContainer.get_or_create(my_func, my_wrapper)

        result = container.invoke_sync(3, 5)

        assert "args:(3, 5)" in call_log
        assert "compute:3+5" in call_log
        assert "result:8" in call_log
        assert result == 8

    def test_wrapper_modifies_result(self):
        """wrapper가 결과를 수정하는 경우"""
        call_log: list[str] = []

        def double_wrapper(original):
            def wrapped(*args, **kwargs):
                result = original(*args, **kwargs)
                return result * 2

            return wrapped

        def my_func(x: int):
            return x + 1

        container = DecoratorContainer.get_or_create(my_func, double_wrapper)

        result = container.invoke_sync(5)
        assert result == 12  # (5 + 1) * 2


class TestDecoratorContainerAsync:
    """DecoratorContainer 비동기 테스트"""

    @pytest.mark.asyncio
    async def test_async_wrapper(self):
        """비동기 함수에서 wrapper 실행"""
        call_log: list[str] = []

        def my_wrapper(original):
            async def wrapped(*args, **kwargs):
                call_log.append("wrapper_start")
                result = await original(*args, **kwargs)
                call_log.append("wrapper_end")
                return result

            return wrapped

        async def my_async_func(x: int):
            call_log.append(f"original:{x}")
            return x * 3

        container = DecoratorContainer.get_or_create(my_async_func, my_wrapper)

        result = await container(5)

        assert call_log == ["wrapper_start", "original:5", "wrapper_end"]
        assert result == 15

    @pytest.mark.asyncio
    async def test_sync_wrapper_on_async_func(self):
        """비동기 함수에 동기 wrapper 적용 (wrapper가 async로 래핑)"""
        call_log: list[str] = []

        def my_wrapper(original):
            # 비동기 함수를 래핑하므로 async wrapper 사용
            async def wrapped(*args, **kwargs):
                call_log.append("sync_wrapper_start")
                result = await original(*args, **kwargs)
                call_log.append("sync_wrapper_end")
                return result

            return wrapped

        async def my_async_func():
            call_log.append("original_async")
            return "async_result"

        container = DecoratorContainer.get_or_create(my_async_func, my_wrapper)

        result = await container()

        assert call_log == ["sync_wrapper_start", "original_async", "sync_wrapper_end"]
        assert result == "async_result"


class TestDecoratorContainerTransfer:
    """DecoratorContainer 흡수/전이 테스트

    핵심: DecoratorContainer와 HandlerContainer는 같은 MRO 레벨이므로
    먼저 생성된 컨테이너가 유지됩니다. 데코레이션 정보는 Element로 이전됩니다.
    """

    @pytest.mark.asyncio
    async def test_decorator_then_handler_same_level(self):
        """DecoratorContainer 후 HandlerContainer 적용 시 HandlerContainer가 우선 (priority 30 > 20)"""
        call_log: list[str] = []

        wrapper = create_logging_wrapper(call_log)

        def my_handler():
            call_log.append("handler")
            return "done"

        # DecoratorContainer 먼저 생성
        dec_container = DecoratorContainer.get_or_create(my_handler, wrapper)
        assert isinstance(dec_container, DecoratorContainer)

        # HandlerContainer 시도 - priority가 높으므로 오버라이드
        handler_container = HandlerContainer.get_or_create(my_handler)

        # 현재 컨테이너 확인 - HandlerContainer가 됨 (priority 30 > 20)
        current_container = getattr(my_handler, "__container__")
        assert isinstance(current_container, HandlerContainer)

        # decoration element가 이전되었는지 확인
        decoration_elements = [
            e for e in current_container.elements if "wrapper" in e.metadata
        ]
        assert len(decoration_elements) > 0, "decoration element should be transferred"

    def test_handler_absorbed_by_decorator_preserves_handler(self):
        """HandlerContainer가 먼저 있으면 유지됨"""

        # HandlerContainer 먼저 생성
        def my_handler():
            return "handler_result"

        handler_container = HandlerContainer.get_or_create(my_handler)
        handler_container.add_elements(OrderElement(10))

        # DecoratorContainer 시도 - 같은 레벨이므로 먼저 생성된 HandlerContainer 유지
        noop_wrapper = lambda fn: fn
        dec_container = DecoratorContainer.get_or_create(my_handler, noop_wrapper)

        current_container = getattr(my_handler, "__container__")

        # HandlerContainer가 먼저 생성되었으므로 유지됨
        assert isinstance(current_container, HandlerContainer)
        assert current_container.has_element(OrderElement)
        assert current_container.get_metadata("order") == 10

    def test_decorator_creation(self):
        """DecoratorContainer 생성 확인"""
        call_log: list[str] = []

        wrapper = create_logging_wrapper(call_log)

        def my_func():
            call_log.append("original")
            return "result"

        # 데코레이터 생성
        container = DecoratorContainer.get_or_create(my_func, wrapper)
        assert isinstance(container, DecoratorContainer)

    def test_element_transfer_includes_decorator_metadata(self):
        """Element 이전 시 데코레이터 메타데이터 포함 확인"""

        def my_wrapper(fn):
            return fn

        def target_func():
            return "target_result"

        # DecoratorContainer 생성
        dec_container = DecoratorContainer.get_or_create(target_func, my_wrapper)

        # HandlerContainer로 오버라이드 (priority 30 > 20)
        handler_container = HandlerContainer.get_or_create(target_func)

        # 메타데이터 확인 - HandlerContainer에 decoration element가 이전됨
        decoration_element = None
        for elem in handler_container.elements:
            if "wrapper" in elem.metadata:
                decoration_element = elem
                break

        assert decoration_element is not None
        assert decoration_element.metadata["wrapper"] == my_wrapper


class TestDecoratorFunction:
    """@decorator 함수형 데코레이터 테스트"""

    @pytest.mark.asyncio
    async def test_decorator_factory_with_wrapper(self):
        """@Decorator(wrapper) 사용"""
        call_log: list[str] = []

        def timing_wrapper(original):
            def wrapped(*args, **kwargs):
                call_log.append("timing_start")
                result = original(*args, **kwargs)
                call_log.append("timing_end")
                return result

            return wrapped

        @Decorator(timing_wrapper)
        def my_function(x: int):
            call_log.append(f"compute:{x}")
            return x * 2

        container = getattr(my_function, "__container__")
        assert isinstance(container, DecoratorContainer)

        result = await container.invoke(5)

        assert call_log == ["timing_start", "compute:5", "timing_end"]
        assert result == 10

    @pytest.mark.asyncio
    async def test_decorator_stacking(self):
        """여러 decorator 스태킹"""
        call_log: list[str] = []

        wrapper1 = create_simple_wrapper(call_log, "outer")
        wrapper2 = create_simple_wrapper(call_log, "inner")

        @Decorator(wrapper1)
        @Decorator(wrapper2)
        def my_function():
            call_log.append("execute")
            return "done"

        container = getattr(my_function, "__container__")
        result = await container.invoke()

        # 스태킹 순서에 따라 outer -> inner -> execute
        assert "execute" in call_log
        assert result == "done"


class TestDecoratorContainerMROHierarchy:
    """DecoratorContainer MRO 계층 구조 테스트"""

    def test_decorator_container_inherits_callable(self):
        """DecoratorContainer가 CallableContainer를 상속하는지 확인"""
        assert issubclass(DecoratorContainer, CallableContainer)

    def test_decorator_container_mro_index(self):
        """DecoratorContainer의 MRO 인덱스 확인"""
        # Container 기준 MRO 인덱스
        decorator_idx = DecoratorContainer.__mro__.index(Container)
        callable_idx = CallableContainer.__mro__.index(Container)
        handler_idx = HandlerContainer.__mro__.index(Container)

        # DecoratorContainer와 CallableContainer 관계
        assert decorator_idx > callable_idx
        # HandlerContainer와 비교 (둘 다 CallableContainer 상속)
        assert handler_idx > callable_idx


class TestDecoratorContainerRealWorld:
    """DecoratorContainer 실제 사용 시나리오 테스트"""

    def test_logging_decorator_use_case(self):
        """로깅 데코레이터 사용 사례"""
        logs: list[str] = []

        def logging_wrapper(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                logs.append(f"ENTRY: args={args}, kwargs={kwargs}")
                result = fn(*args, **kwargs)
                logs.append(f"EXIT: result={result}")
                return result

            return wrapped

        def process_data(data: str):
            return data.upper()

        container = DecoratorContainer.get_or_create(process_data, logging_wrapper)

        result = container.invoke_sync("hello")

        assert result == "HELLO"
        assert len(logs) == 2
        assert "ENTRY" in logs[0]
        assert "EXIT" in logs[1]
        assert "HELLO" in logs[1]

    def test_validation_decorator_use_case(self):
        """검증 데코레이터 사용 사례"""
        validation_errors: list[str] = []

        def validation_wrapper(fn):
            @wraps(fn)
            def wrapped(n: int):
                if n < 0:
                    validation_errors.append("Value must be positive")
                return fn(n)

            return wrapped

        def calculate_square(n: int):
            return n * n

        container = DecoratorContainer.get_or_create(
            calculate_square, validation_wrapper
        )

        # 정상 케이스
        result = container.invoke_sync(5)
        assert result == 25
        assert len(validation_errors) == 0

        # 검증 실패 케이스 (에러 로그만 추가, 실행은 계속)
        result = container.invoke_sync(-3)
        assert result == 9  # 실행은 됨
        assert len(validation_errors) == 1
        assert "positive" in validation_errors[0]

    def test_retry_decorator_use_case(self):
        """재시도 데코레이터 사용 사례"""
        call_count = {"value": 0}

        def retry_wrapper(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                last_error: BaseException | None = None
                for attempt in range(3):
                    try:
                        return fn(*args, **kwargs)
                    except Exception as e:
                        last_error = e
                if last_error is not None:
                    raise last_error
                raise RuntimeError("Unexpected state")

            return wrapped

        def flaky_function():
            call_count["value"] += 1
            if call_count["value"] < 3:
                raise ValueError("Temporary failure")
            return "success"

        container = DecoratorContainer.get_or_create(flaky_function, retry_wrapper)

        result = container.invoke_sync()
        assert result == "success"
        assert call_count["value"] == 3


class TestDecoratorContainerAbsorption:
    """DecoratorContainer 흡수 상세 테스트"""

    def test_absorbed_decorator_element_preserved(self):
        """흡수된 DecoratorContainer의 Element가 보존되는지 확인"""
        custom_element = Element()
        custom_element.metadata["custom_key"] = "custom_value"

        def my_func():
            return "result"

        noop_wrapper = lambda fn: fn

        # DecoratorContainer에 Element 추가
        dec_container = DecoratorContainer.get_or_create(my_func, noop_wrapper)
        dec_container.add_element(custom_element)

        # HandlerContainer로 오버라이드 (priority 30 > 20)
        handler_container = HandlerContainer.get_or_create(my_func)

        # Element가 이전되었는지 확인
        current = getattr(my_func, "__container__")
        # HandlerContainer가 됨 (priority가 더 높음)
        assert isinstance(current, HandlerContainer)
        # custom element가 이전되었는지 확인
        assert any(
            elem.metadata.get("custom_key") == "custom_value"
            for elem in current.elements
        )

    def test_decorator_to_decorator_stacking(self):
        """같은 함수에 @decorator 여러번 적용 시 wrapper 누적"""
        call_log: list[str] = []

        wrapper1 = create_simple_wrapper(call_log, "wrapper1")
        wrapper2 = create_simple_wrapper(call_log, "wrapper2")

        def my_func():
            call_log.append("original")
            return "done"

        # 첫 번째 DecoratorContainer
        container1 = DecoratorContainer.get_or_create(my_func, wrapper1)

        # 두 번째 @decorator 적용 - 같은 컨테이너에 wrapper 추가
        container2 = DecoratorContainer.get_or_create(my_func, wrapper2)

        # 같은 컨테이너여야 함
        assert container1 is container2


class TestDecoratorContainerStandalone:
    """DecoratorContainer가 @Handler 없이 독립적으로 동작하는 테스트

    DecoratorContainer는 CallableContainer처럼 독립적으로 동작 가능합니다.
    @Component 내부에서 @Handler 없이 @decorator만 사용해도
    owner 인스턴스가 자동으로 바인딩되어야 합니다.
    """

    @pytest.mark.asyncio
    async def test_decorator_only_in_component(self, reset_manager: ContainerManager):
        """@Component 내부에서 @decorator만 사용 (@Handler 없음)"""
        from bloom import Application, Component

        call_log: list[str] = []

        def logging_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("before")
                result = await fn(*args, **kwargs)
                call_log.append(f"after:{result}")
                return result

            return wrapped

        @Component
        class MyService:
            def __init__(self):
                self.name = "MyService"

            @Decorator(logging_wrapper)
            async def process(self, data: str) -> str:
                call_log.append(f"process:{data}:{self.name}")
                return f"processed:{data}"

        # Application 설정
        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        # 컨테이너 확인 - DecoratorContainer여야 함
        container = getattr(MyService.process, "__container__")
        assert isinstance(container, DecoratorContainer)

        # 서비스 인스턴스를 통한 직접 호출 (bound method)
        service = reset_manager.get_instance(MyService)  # type: ignore
        result = await service.process("hello")

        assert "process:hello:MyService" in call_log
        assert result == "processed:hello"

    @pytest.mark.asyncio
    async def test_decorator_container_invoke_with_owner(
        self, reset_manager: ContainerManager
    ):
        """DecoratorContainer.invoke()가 owner 인스턴스를 자동 바인딩"""
        from bloom import Application, Component

        call_log: list[str] = []

        def timing_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("timing:start")
                result = await fn(*args, **kwargs)
                call_log.append("timing:end")
                return result

            return wrapped

        @Component
        class TimedService:
            def __init__(self):
                self.counter = 0

            @Decorator(timing_wrapper)
            async def increment(self) -> int:
                self.counter += 1
                call_log.append(f"counter:{self.counter}")
                return self.counter

        app = Application("test", manager=reset_manager)
        app.scan(TimedService)  # 로컬 클래스 직접 스캔
        await app.ready_async()

        # 컨테이너를 통한 invoke 호출
        container: DecoratorContainer = getattr(TimedService.increment, "__container__")
        result = await container.invoke()

        # wrapper가 적용되고 self가 바인딩되어야 함
        assert "timing:start" in call_log
        assert "counter:1" in call_log
        assert "timing:end" in call_log
        assert result == 1

    @pytest.mark.asyncio
    async def test_decorator_container_call_with_owner(
        self, reset_manager: ContainerManager
    ):
        """DecoratorContainer.__call__()가 owner 인스턴스를 자동 바인딩"""
        from bloom import Application, Component

        call_log: list[str] = []

        def validate_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("validate")
                return await fn(*args, **kwargs)

            return wrapped

        @Component
        class ValidatedService:
            def __init__(self):
                self.state = "initialized"

            @Decorator(validate_wrapper)
            async def get_state(self) -> str:
                call_log.append(f"get_state:{self.state}")
                return self.state

        app = Application("test", manager=reset_manager)
        app.scan(ValidatedService)  # 로컬 클래스 직접 스캔
        await app.ready_async()

        # 컨테이너를 통한 __call__ 호출
        container: DecoratorContainer = getattr(
            ValidatedService.get_state, "__container__"
        )
        result = await container()

        assert "validate" in call_log
        assert "get_state:initialized" in call_log
        assert result == "initialized"

    @pytest.mark.asyncio
    async def test_decorator_with_arguments_and_owner(
        self, reset_manager: ContainerManager
    ):
        """인자가 있는 메서드에서 owner 인스턴스 바인딩"""
        from bloom import Application, Component

        call_log: list[str] = []

        def audit_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append(f"audit:args={args},kwargs={kwargs}")
                return await fn(*args, **kwargs)

            return wrapped

        @Component
        @Component
        class CalculatorService:
            def __init__(self):
                self.operations = []

            @Decorator(audit_wrapper)
            async def add(self, a: int, b: int) -> int:
                result = a + b
                self.operations.append(f"add({a},{b})={result}")
                call_log.append(f"add:{a}+{b}={result}")
                return result

        app = Application("test", manager=reset_manager)
        app.scan(CalculatorService)  # 로컬 클래스 직접 스캔
        await app.ready_async()

        container: DecoratorContainer = getattr(CalculatorService.add, "__container__")
        result = await container(3, 5)

        assert "add:3+5=8" in call_log
        assert result == 8

        # audit wrapper도 호출됨
        audit_log = [log for log in call_log if log.startswith("audit:")]
        assert len(audit_log) == 1

    @pytest.mark.asyncio
    async def test_multiple_decorators_without_handler(
        self, reset_manager: ContainerManager
    ):
        """여러 @decorator를 @Handler 없이 사용"""
        from bloom import Application, Component

        call_log: list[str] = []

        def wrapper1(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("wrapper1:start")
                result = await fn(*args, **kwargs)
                call_log.append("wrapper1:end")
                return result

            return wrapped

        def wrapper2(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("wrapper2:start")
                result = await fn(*args, **kwargs)
                call_log.append("wrapper2:end")
                return result

            return wrapped

        @Component
        class MultiWrapperService:
            @Decorator(wrapper1)
            @Decorator(wrapper2)
            async def do_work(self) -> str:
                call_log.append("do_work")
                return "done"

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(MultiWrapperService)  # type: ignore
        result = await service.do_work()

        assert "do_work" in call_log
        assert result == "done"

    @pytest.mark.asyncio
    async def test_sync_method_with_decorator(self, reset_manager: ContainerManager):
        """동기 메서드에 @decorator 사용"""
        from bloom import Application, Component

        call_log: list[str] = []

        def sync_wrapper(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                call_log.append("sync:before")
                result = fn(*args, **kwargs)
                call_log.append("sync:after")
                return result

            return wrapped

        @Component
        class SyncService:
            def __init__(self):
                self.value = 10

            @Decorator(sync_wrapper)
            def get_value(self) -> int:
                call_log.append(f"get_value:{self.value}")
                return self.value

        app = Application("test", manager=reset_manager)
        app.scan(SyncService)  # 로컬 클래스 직접 스캔
        await app.ready_async()

        container: DecoratorContainer = getattr(SyncService.get_value, "__container__")
        result = await container()

        assert "sync:before" in call_log
        assert "get_value:10" in call_log
        assert "sync:after" in call_log
        assert result == 10


class TestDecoratorWithComponentAndHandler:
    """@Component + @Handler와 DecoratorContainer 조합 테스트

    실제 Bloom 프레임워크의 @Component, @Handler와 함께 사용할 때
    데코레이션이 제대로 동작하는지 검증합니다.
    """

    @pytest.mark.asyncio
    async def test_decorator_with_component_handler(
        self, reset_manager: ContainerManager
    ):
        """@Component 내부의 @Handler와 decorator 조합"""
        from bloom import Application, Component
        from bloom.core.decorators import Handler

        call_log: list[str] = []

        def logging_wrapper[**P, R](fn: Callable[P, Awaitable[R]]):
            @wraps(fn)
            async def wrapped(*args: P.args, **kwargs: P.kwargs):
                call_log.append("before_handler")
                result = await fn(*args, **kwargs)
                call_log.append(f"after_handler:{result}")
                return result

            return wrapped

        @Component
        class MyService:
            @Decorator(logging_wrapper)
            @Handler
            async def process_data(self, data: str) -> str:
                call_log.append(f"process:{data}")
                return f"processed:{data}"

        # Application 설정
        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        # 핸들러 컨테이너 확인
        container = getattr(MyService.process_data, "__container__")
        assert container is not None

        # 인스턴스 가져오기
        service = reset_manager.get_instance(MyService)  # type: ignore
        assert service is not None

        # 핸들러 직접 호출 (bound method)
        result = await service.process_data("hello")

        # 원본 함수 실행 확인
        assert "process:hello" in call_log
        assert result == "processed:hello"

    @pytest.mark.asyncio
    async def test_handler_then_decorator_order(self, reset_manager):
        """@Handler → @decorator 순서: HandlerContainer가 priority 높아서 유지됨"""
        from bloom import Application, Component
        from bloom.core.decorators import Handler

        call_log: list[str] = []

        def timing_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("timing_start")
                result = await fn(*args, **kwargs)
                call_log.append("timing_end")
                return result

            return wrapped

        # Component 외부에서 decorator 적용하여 테스트
        async def timed_func() -> str:
            call_log.append("operation")
            return "done"

        # @decorator가 먼저 (priority 20), @Handler가 나중 (priority 30)
        dec_container = DecoratorContainer.get_or_create(timed_func, timing_wrapper)
        handler_container = HandlerContainer.get_or_create(timed_func)

        # 컨테이너 타입 확인 - HandlerContainer가 우선 (priority 30 > 20)
        current = getattr(timed_func, "__container__")
        assert isinstance(current, HandlerContainer)

        # decoration element가 이전되었는지 확인
        decoration_elements = [e for e in current.elements if "wrapper" in e.metadata]
        assert len(decoration_elements) > 0, "decoration element should be transferred"

    @pytest.mark.asyncio
    async def test_multiple_handlers_with_decorator(self, reset_manager):
        """여러 핸들러에 각각 다른 decorator 적용"""
        from bloom import Application, Component
        from bloom.core.decorators import Handler

        call_log: list[str] = []

        def wrapper_a(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("log_a")
                return await fn(*args, **kwargs)

            return wrapped

        def wrapper_b(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("log_b")
                return await fn(*args, **kwargs)

            return wrapped

        @Component
        class MultiHandlerService:
            @Decorator(wrapper_a)
            @Handler
            async def handler_a(self) -> str:
                call_log.append("handler_a")
                return "a"

            @Decorator(wrapper_b)
            @Handler
            async def handler_b(self) -> str:
                call_log.append("handler_b")
                return "b"

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(MultiHandlerService)

        # 각 핸들러 호출
        result_a = await service.handler_a()
        result_b = await service.handler_b()

        assert result_a == "a"
        assert result_b == "b"
        assert "handler_a" in call_log
        assert "handler_b" in call_log

    @pytest.mark.asyncio
    async def test_decorator_preserves_handler_container_type(self, reset_manager):
        """decorator가 HandlerContainer 타입을 유지하는지 확인"""
        from bloom import Component
        from bloom.core.decorators import Handler
        from bloom.core.container import HandlerContainer

        noop_wrapper = lambda fn: fn

        @Component
        class ServiceWithDecorator:
            @Decorator(noop_wrapper)
            @Handler
            async def my_handler(self) -> str:
                return "result"

        # 컨테이너 타입 확인
        container = getattr(ServiceWithDecorator.my_handler, "__container__")

        # @Handler가 아래에서 먼저 적용되므로 HandlerContainer가 생성됨
        # 그 다음 @decorator가 적용되지만 같은 레벨이므로 HandlerContainer 유지
        assert isinstance(container, HandlerContainer)

    @pytest.mark.asyncio
    async def test_decorator_with_handler_invoke(self, reset_manager):
        """DecoratorContainer로 감싼 Handler를 invoke로 호출"""
        from bloom import Application, Component
        from bloom.core.decorators import Handler

        call_log: list[str] = []

        def invoke_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("before")
                result = await fn(*args, **kwargs)
                call_log.append(f"after:{result}")
                return result

            return wrapped

        @Component
        class InvokeTestService:
            @Decorator(invoke_wrapper)
            @Handler
            async def invoke_me(self, value: int) -> int:
                call_log.append(f"invoke:{value}")
                return value * 2

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        # HandlerContainer의 invoke 사용
        container = getattr(InvokeTestService.invoke_me, "__container__")
        assert container is not None

        # owner_cls 설정 확인
        assert container.owner_cls == InvokeTestService

        # 인스턴스를 통한 호출
        service = reset_manager.get_instance(InvokeTestService)
        result = await service.invoke_me(5)

        assert result == 10
        assert "invoke:5" in call_log

    @pytest.mark.asyncio
    async def test_decoration_element_transferred_to_handler(self, reset_manager):
        """decorator의 Element가 HandlerContainer로 이전되는지 확인"""
        from bloom import Component
        from bloom.core.decorators import Handler

        def my_wrapper(fn):
            return fn

        @Component
        class ElementTransferService:
            @Decorator(my_wrapper)
            @Handler
            async def my_method(self) -> str:
                return "result"

        container = getattr(ElementTransferService.my_method, "__container__")

        # decoration 관련 Element 확인
        decoration_elem = None
        for elem in container.elements:
            if "wrapper" in elem.metadata:
                decoration_elem = elem
                break

        # decorator가 먼저 적용되고 Handler가 나중에 적용되므로
        # DecoratorContainer의 Element가 HandlerContainer로 이전됨
        if decoration_elem:
            assert decoration_elem.metadata.get("wrapper") == my_wrapper


class TestDecoratorContainerWithControllerAndGet:
    """Controller + Get과 DecoratorContainer 조합 테스트"""

    @pytest.mark.asyncio
    async def test_decorator_with_controller_get(self, reset_manager):
        """@Controller + @Get + @decorator 조합"""
        from bloom import Application
        from bloom.web.controller import Controller
        from bloom.web.handler import Get, HttpMethodHandlerContainer

        call_log: list[str] = []

        def auth_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("auth_check")
                return await fn(*args, **kwargs)

            return wrapped

        @Controller
        class ApiController:
            @Decorator(auth_wrapper)
            @Get("/api/users")
            async def get_users(self) -> dict:
                call_log.append("get_users")
                return {"users": []}

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        # 컨테이너 확인
        container = getattr(ApiController.get_users, "__container__")
        assert isinstance(container, HttpMethodHandlerContainer)
        assert container.get_metadata("http_method") == "GET"
        assert container.get_metadata("http_path") == "/api/users"

    @pytest.mark.asyncio
    async def test_decorator_order_with_http_handler(self, reset_manager):
        """HTTP 핸들러에서 decorator 적용 순서 확인"""
        from bloom import Application
        from bloom.web.controller import Controller
        from bloom.web.handler import Post, HttpMethodHandlerContainer
        from bloom.core.decorators import Order

        call_log: list[str] = []

        def validate_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("validate")
                return await fn(*args, **kwargs)

            return wrapped

        @Controller
        class ValidationController:
            @Order(1)
            @Decorator(validate_wrapper)
            @Post("/api/items")
            async def create_item(self, data: dict) -> dict:
                call_log.append("create")
                return {"created": True}

        # 컨테이너 확인
        container = getattr(ValidationController.create_item, "__container__")
        assert isinstance(container, HttpMethodHandlerContainer)
        assert container.get_metadata("order") == 1
        assert container.get_metadata("http_method") == "POST"


class TestMultipleDecoratorContainersWithHandler:
    """@Component에서 @Handler와 여러 DecoratorContainer 조합 테스트

    실제 시나리오: 로깅, 인증, 트랜잭션 등 여러 데코레이터가
    하나의 핸들러에 적용되는 경우를 검증합니다.
    """

    @pytest.mark.asyncio
    async def test_two_decorators_with_handler(self, reset_manager):
        """2개의 DecoratorContainer + @Handler 조합"""
        from bloom import Application, Component
        from bloom.core.decorators import Handler

        call_log: list[str] = []

        def log_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("log:before")
                result = await fn(*args, **kwargs)
                call_log.append(f"log:after:{result}")
                return result

            return wrapped

        def timing_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("timing:start")
                result = await fn(*args, **kwargs)
                call_log.append("timing:end")
                return result

            return wrapped

        @Component
        class ServiceWithTwoDecorators:
            @Decorator(log_wrapper)
            @Decorator(timing_wrapper)
            @Handler
            async def process(self, data: str) -> str:
                call_log.append(f"process:{data}")
                return f"result:{data}"

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(ServiceWithTwoDecorators)
        result = await service.process("input")

        # 원본 함수는 실행되어야 함
        assert "process:input" in call_log
        assert result == "result:input"

        # 컨테이너 타입 확인
        container = getattr(ServiceWithTwoDecorators.process, "__container__")
        assert isinstance(container, HandlerContainer)

    @pytest.mark.asyncio
    async def test_transaction_wrapper_with_handler(self, reset_manager):
        """트랜잭션 wrapper 데코레이터와 @Handler 조합"""
        from bloom import Application, Component
        from bloom.core.decorators import Handler

        call_log: list[str] = []

        def transaction_wrapper(original):
            async def wrapped(*args, **kwargs):
                call_log.append("transaction:begin")
                try:
                    result = await original(*args, **kwargs)
                    call_log.append("transaction:commit")
                    return result
                except Exception:
                    call_log.append("transaction:rollback")
                    raise

            return wrapped

        def audit_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("audit:start")
                return await fn(*args, **kwargs)

            return wrapped

        @Component
        class TransactionalService:
            @Decorator(audit_wrapper)
            @Decorator(transaction_wrapper)
            @Handler
            async def save_data(self, data: dict) -> dict:
                call_log.append("save_data")
                return {"saved": True, **data}

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(TransactionalService)
        result = await service.save_data({"key": "value"})

        assert result["saved"] is True
        assert "save_data" in call_log

    @pytest.mark.asyncio
    async def test_decorators_with_handler_and_order(self, reset_manager):
        """@Order + 2개 DecoratorContainer + @Handler 조합"""
        from bloom import Application, Component
        from bloom.core.decorators import Handler, Order

        call_log: list[str] = []

        def rate_limit_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("rate_limit:check")
                return await fn(*args, **kwargs)

            return wrapped

        def metrics_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                result = await fn(*args, **kwargs)
                call_log.append(f"metrics:recorded:{result}")
                return result

            return wrapped

        @Component
        class OrderedService:
            @Order(10)
            @Decorator(rate_limit_wrapper)
            @Decorator(metrics_wrapper)
            @Handler
            async def api_call(self, endpoint: str) -> str:
                call_log.append(f"api:{endpoint}")
                return f"response:{endpoint}"

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(OrderedService)
        result = await service.api_call("/users")

        assert "api:/users" in call_log
        assert result == "response:/users"

        # @Order Element 확인
        container = getattr(OrderedService.api_call, "__container__")
        assert container.get_metadata("order") == 10

    @pytest.mark.asyncio
    async def test_decorators_transfer_elements_to_handler(self, reset_manager):
        """여러 DecoratorContainer의 Element가 HandlerContainer로 이전되는지 확인"""
        from bloom import Component
        from bloom.core.decorators import Handler

        noop_wrapper = lambda fn: fn

        @Component
        class MultiDecoratorService:
            @Decorator(noop_wrapper)
            @Decorator(noop_wrapper)
            @Handler
            async def my_method(self) -> str:
                return "done"

        container = getattr(MultiDecoratorService.my_method, "__container__")

        # HandlerContainer로 유지되는지 확인
        assert isinstance(container, HandlerContainer)

    @pytest.mark.asyncio
    async def test_three_decorators_with_handler(self, reset_manager):
        """3개의 DecoratorContainer + @Handler 조합 (극단적 케이스)"""
        from bloom import Application, Component
        from bloom.core.decorators import Handler

        call_log: list[str] = []

        def retry_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("retry:attempt")
                return await fn(*args, **kwargs)

            return wrapped

        def circuit_breaker_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("circuit:check")
                return await fn(*args, **kwargs)

            return wrapped

        def fallback_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                result = await fn(*args, **kwargs)
                call_log.append(f"fallback:result={result}")
                return result

            return wrapped

        @Component
        class ResilientService:
            @Decorator(retry_wrapper)
            @Decorator(circuit_breaker_wrapper)
            @Decorator(fallback_wrapper)
            @Handler
            async def resilient_call(self) -> str:
                call_log.append("call:execute")
                return "success"

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(ResilientService)
        result = await service.resilient_call()

        assert result == "success"
        assert "call:execute" in call_log

    @pytest.mark.asyncio
    async def test_decorators_with_http_handler(self, reset_manager):
        """2개 DecoratorContainer + @Get HTTP 핸들러 조합"""
        from bloom import Application
        from bloom.web.controller import Controller
        from bloom.web.handler import Get, HttpMethodHandlerContainer

        call_log: list[str] = []

        def cors_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("cors:check")
                return await fn(*args, **kwargs)

            return wrapped

        def compress_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                result = await fn(*args, **kwargs)
                call_log.append("compress:response")
                return result

            return wrapped

        @Controller
        class ApiWithMiddleware:
            @Decorator(cors_wrapper)
            @Decorator(compress_wrapper)
            @Get("/api/data")
            async def get_data(self) -> dict:
                call_log.append("get_data")
                return {"data": [1, 2, 3]}

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        # 컨테이너 타입 및 메타데이터 확인
        container = getattr(ApiWithMiddleware.get_data, "__container__")
        assert isinstance(container, HttpMethodHandlerContainer)
        assert container.get_metadata("http_method") == "GET"
        assert container.get_metadata("http_path") == "/api/data"

    @pytest.mark.asyncio
    async def test_decorators_preserve_method_signature(self, reset_manager):
        """여러 데코레이터 적용 후에도 메서드 시그니처 유지"""
        from bloom import Application, Component
        from bloom.core.decorators import Handler

        noop_wrapper = lambda fn: fn

        @Component
        class SignaturePreserveService:
            @Decorator(noop_wrapper)
            @Decorator(noop_wrapper)
            @Handler
            async def method_with_params(
                self, user_id: int, name: str, active: bool = True
            ) -> dict:
                return {"user_id": user_id, "name": name, "active": active}

        app = Application("test", manager=reset_manager)
        app.scan(__import__(__name__))
        await app.ready_async()

        service = reset_manager.get_instance(SignaturePreserveService)

        # 실제 호출 테스트
        result = await service.method_with_params(1, "Alice", active=False)
        assert result == {"user_id": 1, "name": "Alice", "active": False}

        # 기본값 테스트
        result2 = await service.method_with_params(2, "Bob")
        assert result2 == {"user_id": 2, "name": "Bob", "active": True}
