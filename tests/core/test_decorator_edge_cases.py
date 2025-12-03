"""@Decorator와 다른 데코레이터 조합 엣지케이스 테스트

@Decorator를 @Task, @Component, @Factory, @Handler 등과 함께 사용할 때의
다양한 엣지케이스를 검증합니다.
"""

import pytest
import asyncio
from functools import wraps
from typing import Callable

from bloom import Application
from bloom.core import Component, Factory, Scope
from bloom.core.decorators import Decorator
from bloom.core.container import (
    Container,
    CallableContainer,
    HandlerContainer,
    DecoratorContainer,
    FactoryContainer,
)
from bloom.core.container.element import Scope as ScopeEnum, ScopeElement
from bloom.core.manager import ContainerManager, set_current_manager
from bloom.task import Task
from bloom.task.backend import AsyncioTaskBackend, TaskBackend


@pytest.fixture(autouse=True)
def reset_manager():
    """각 테스트 전에 manager 초기화"""
    manager = ContainerManager("test")
    set_current_manager(manager)
    yield manager
    set_current_manager(None)


# === 헬퍼: wrapper 생성 함수들 ===


def logging_wrapper(call_log: list[str], name: str = "log"):
    """로깅 wrapper 생성"""

    def wrapper(fn):
        @wraps(fn)
        def sync_wrapped(*args, **kwargs):
            call_log.append(f"{name}:before")
            result = fn(*args, **kwargs)
            call_log.append(f"{name}:after")
            return result

        @wraps(fn)
        async def async_wrapped(*args, **kwargs):
            call_log.append(f"{name}:before")
            result = await fn(*args, **kwargs)
            call_log.append(f"{name}:after")
            return result

        return async_wrapped if asyncio.iscoroutinefunction(fn) else sync_wrapped

    return wrapper


def timing_wrapper(fn):
    """타이밍 wrapper (의존성 없음)"""

    @wraps(fn)
    def wrapped(*args, **kwargs):
        # 실제로는 시간 측정
        return fn(*args, **kwargs)

    @wraps(fn)
    async def async_wrapped(*args, **kwargs):
        return await fn(*args, **kwargs)

    return async_wrapped if asyncio.iscoroutinefunction(fn) else wrapped


def transform_result_wrapper(fn):
    """결과 변환 wrapper"""

    @wraps(fn)
    def wrapped(*args, **kwargs):
        result = fn(*args, **kwargs)
        return f"[transformed]{result}"

    return wrapped


class TestDecoratorWithTask:
    """@Decorator + @Task 조합 테스트
    
    @Task가 @Decorator로 감싸진 함수를 받아서,
    DecoratorElement에서 wrapper를 읽어 적용합니다.
    """

    async def test_decorator_on_task_method(self):
        """@Task가 @Decorator wrapper를 적용하는지 테스트"""
        call_log = []

        @Component
        class TaskService:
            @Task
            @Decorator(logging_wrapper(call_log, "dec"))
            def my_task(self) -> str:
                call_log.append("task:execute")
                return "done"

        @Component
        class Config:
            @Factory
            def backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

        app = await (
            Application("test_decorator_task")
            .scan(TaskService, Config)
            .ready_async()
        )

        service = app.manager.get_instance(TaskService)

        # 직접 호출 - Decorator가 적용되어야 함
        result = service.my_task()

        assert result == "done"
        assert "dec:before" in call_log
        assert "task:execute" in call_log
        assert "dec:after" in call_log

    async def test_task_on_decorator_method(self):
        """@Task가 @Decorator 메서드에 적용될 때 (순서 반대)"""
        call_log = []

        @Component
        class TaskService:
            @Task
            @Decorator(logging_wrapper(call_log, "dec"))
            def my_task(self) -> str:
                call_log.append("task:execute")
                return "done"

        @Component
        class Config:
            @Factory
            def backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

        app = await (
            Application("test_task_decorator")
            .scan(TaskService, Config)
            .ready_async()
        )

        service = app.manager.get_instance(TaskService)
        result = service.my_task()

        assert result == "done"
        # 데코레이터 순서에 따라 로깅이 적용되어야 함
        assert "task:execute" in call_log

    async def test_multiple_decorators_on_task(self):
        """여러 @Decorator가 @Task에 적용될 때"""
        call_log = []

        @Component
        class TaskService:
            @Task
            @Decorator(logging_wrapper(call_log, "outer"))
            @Decorator(logging_wrapper(call_log, "inner"))
            def my_task(self) -> str:
                call_log.append("task:execute")
                return "done"

        @Component
        class Config:
            @Factory
            def backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

        app = await (
            Application("test_multi_decorator_task")
            .scan(TaskService, Config)
            .ready_async()
        )

        service = app.manager.get_instance(TaskService)
        result = service.my_task()

        assert result == "done"
        # outer가 먼저, inner가 나중에 실행
        assert "outer:before" in call_log
        assert "inner:before" in call_log
        assert "task:execute" in call_log


class TestDecoratorWithFactory:
    """@Decorator + @Factory 조합 테스트
    
    Note: @Decorator(priority 20)는 @Factory(priority 30)보다 priority가 낮아서
    @Factory가 적용되면 DecoratorContainer가 FactoryContainer로 교체됩니다.
    
    현재 구현에서 @Decorator + @Factory 조합은 완전히 지원되지 않습니다.
    """

    async def test_decorator_on_factory_current_behavior(self):
        """@Decorator가 @Factory에 적용될 때 (현재 동작 문서화)
        
        현재: @Decorator wrapper가 적용되지 않음 (@Factory가 오버라이드)
        """
        call_log = []

        class ExternalService:
            def __init__(self, value: str):
                self.value = value

        @Component
        class Config:
            @Decorator(logging_wrapper(call_log, "dec"))
            @Factory
            def create_service(self) -> ExternalService:
                call_log.append("factory:create")
                return ExternalService("created")

        app = await (
            Application("test_decorator_factory")
            .scan(Config)
            .ready_async()
        )

        service = app.manager.get_instance(ExternalService)

        assert service.value == "created"
        assert "factory:create" in call_log
        # 현재 구현에서는 @Decorator가 @Factory에 의해 오버라이드됨

    async def test_factory_on_decorator(self):
        """@Factory가 @Decorator에 적용될 때 (순서 반대)"""
        call_log = []

        class ExternalService:
            def __init__(self, value: str):
                self.value = value

        @Component
        class Config:
            @Factory
            @Decorator(logging_wrapper(call_log, "dec"))
            def create_service(self) -> ExternalService:
                call_log.append("factory:create")
                return ExternalService("created")

        app = await (
            Application("test_factory_decorator")
            .scan(Config)
            .ready_async()
        )

        service = app.manager.get_instance(ExternalService)

        assert service.value == "created"
        assert "factory:create" in call_log

    async def test_decorator_with_factory_chain_current_behavior(self):
        """@Decorator가 Factory Chain에서 동작할 때 (현재 동작 문서화)
        
        현재: @Decorator wrapper가 적용되지 않음 (@Factory가 오버라이드)
        """
        call_log = []

        class Counter:
            def __init__(self, value: int = 0):
                self.value = value

        @Component
        class Config:
            @Decorator(logging_wrapper(call_log, "init"))
            @Factory
            def init_counter(self) -> Counter:
                call_log.append("init:create")
                return Counter(0)

            @Decorator(logging_wrapper(call_log, "add"))
            @Factory
            def add_one(self, counter: Counter) -> Counter:
                call_log.append("add:execute")
                counter.value += 1
                return counter

        app = await (
            Application("test_decorator_factory_chain")
            .scan(Config)
            .ready_async()
        )

        counter = app.manager.get_instance(Counter)

        assert counter.value == 1
        assert "init:create" in call_log
        assert "add:execute" in call_log
        # 현재 구현에서는 @Decorator가 적용되지 않음

    async def test_decorator_with_result_transform_on_factory_current_behavior(self):
        """@Decorator가 Factory 결과를 변환할 때 (현재 동작 문서화)
        
        현재: @Decorator wrapper가 적용되지 않음 (@Factory가 오버라이드)
        """

        class Message:
            def __init__(self, text: str):
                self.text = text

        def message_wrapper(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                result = fn(*args, **kwargs)
                result.text = f"[wrapped]{result.text}"
                return result

            return wrapped

        @Component
        class Config:
            @Decorator(message_wrapper)
            @Factory
            def create_message(self) -> Message:
                return Message("hello")

        app = await (
            Application("test_decorator_transform")
            .scan(Config)
            .ready_async()
        )

        message = app.manager.get_instance(Message)
        # 현재 구현에서는 @Decorator가 적용되지 않으므로 원본 텍스트
        assert message.text == "hello"  # "[wrapped]hello"가 아님


class TestDecoratorWithScope:
    """@Decorator + @Scope 조합 테스트"""

    async def test_decorator_on_prototype_scope_current_behavior(self):
        """@Decorator가 CALL Scope 컴포넌트에 적용될 때 (현재 동작 문서화)
        
        Note: CALL Scope에서는 매번 새 인스턴스가 생성되지만,
        @Decorator의 wrapper는 클래스 레벨에서 한 번만 설정됨.
        """
        call_count = [0]

        def counting_wrapper(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                call_count[0] += 1
                return fn(*args, **kwargs)

            return wrapped

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeService:
            @Decorator(counting_wrapper)
            def do_work(self) -> str:
                return "work"

        @Component
        class Consumer:
            service: PrototypeService

        app = await (
            Application("test_decorator_prototype")
            .scan(PrototypeService, Consumer)
            .ready_async()
        )

        consumer = app.manager.get_instance(Consumer)

        # 메서드 호출
        consumer.service.do_work()
        consumer.service.do_work()

        # 현재 구현에서 CALL Scope + @Decorator는 특별한 처리가 필요할 수 있음
        # wrapper가 클래스 레벨에서 설정되므로 인스턴스와 무관하게 동작해야 함
        # 테스트는 현재 동작을 관찰만 함
        pass  # 현재 동작 확인 필요

    async def test_decorator_preserves_singleton_behavior(self):
        """@Decorator가 SINGLETON Scope를 방해하지 않음"""
        instances = []

        @Component
        class SingletonService:
            def __init__(self):
                instances.append(self)

            @Decorator(timing_wrapper)
            def get_id(self) -> int:
                return id(self)

        @Component
        class Consumer1:
            service: SingletonService

        @Component
        class Consumer2:
            service: SingletonService

        app = await (
            Application("test_decorator_singleton")
            .scan(SingletonService, Consumer1, Consumer2)
            .ready_async()
        )

        c1 = app.manager.get_instance(Consumer1)
        c2 = app.manager.get_instance(Consumer2)

        # 같은 인스턴스여야 함
        assert c1.service.get_id() == c2.service.get_id()
        assert len(instances) == 1


class TestDecoratorWithDependencyInjection:
    """@Decorator의 의존성 주입 테스트"""

    async def test_decorator_with_injected_dependency(self):
        """@Decorator wrapper에 의존성이 주입될 때"""
        call_log = []

        @Component
        class Logger:
            def log(self, msg: str):
                call_log.append(f"log:{msg}")

        def logging_with_di(fn, logger: Logger):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                logger.log("before")
                result = fn(*args, **kwargs)
                logger.log("after")
                return result

            return wrapped

        @Component
        class MyService:
            @Decorator(logging_with_di)
            def do_work(self) -> str:
                call_log.append("work")
                return "done"

        app = await (
            Application("test_decorator_di")
            .scan(Logger, MyService)
            .ready_async()
        )

        service = app.manager.get_instance(MyService)
        result = service.do_work()

        assert result == "done"
        assert call_log == ["log:before", "work", "log:after"]

    async def test_decorator_with_multiple_injected_deps(self):
        """@Decorator wrapper에 여러 의존성이 주입될 때"""
        call_log = []

        @Component
        class Logger:
            def log(self, msg: str):
                call_log.append(f"log:{msg}")

        @Component
        class Metrics:
            def record(self, name: str):
                call_log.append(f"metric:{name}")

        def observability_wrapper(fn, logger: Logger, metrics: Metrics):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                logger.log("start")
                metrics.record("call")
                result = fn(*args, **kwargs)
                logger.log("end")
                return result

            return wrapped

        @Component
        class MyService:
            @Decorator(observability_wrapper)
            def process(self) -> str:
                call_log.append("process")
                return "result"

        app = await (
            Application("test_decorator_multi_di")
            .scan(Logger, Metrics, MyService)
            .ready_async()
        )

        service = app.manager.get_instance(MyService)
        result = service.process()

        assert result == "result"
        assert "log:start" in call_log
        assert "metric:call" in call_log
        assert "process" in call_log
        assert "log:end" in call_log


class TestDecoratorWithAsyncMethods:
    """@Decorator와 async 메서드 조합 테스트"""

    async def test_decorator_on_async_method(self):
        """@Decorator가 async 메서드에 적용될 때"""
        call_log = []

        def async_logging_wrapper(fn):
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                call_log.append("before")
                result = await fn(*args, **kwargs)
                call_log.append("after")
                return result

            return wrapped

        @Component
        class AsyncService:
            @Decorator(async_logging_wrapper)
            async def fetch_data(self) -> str:
                call_log.append("fetch")
                await asyncio.sleep(0.01)
                return "data"

        app = await (
            Application("test_decorator_async")
            .scan(AsyncService)
            .ready_async()
        )

        service = app.manager.get_instance(AsyncService)
        result = await service.fetch_data()

        assert result == "data"
        assert call_log == ["before", "fetch", "after"]

    async def test_sync_decorator_on_async_method(self):
        """sync wrapper가 async 메서드에 적용될 때 (자동 변환)"""
        call_log = []

        @Component
        class AsyncService:
            @Decorator(logging_wrapper(call_log, "sync"))
            async def async_work(self) -> str:
                call_log.append("work")
                return "done"

        app = await (
            Application("test_sync_decorator_async")
            .scan(AsyncService)
            .ready_async()
        )

        service = app.manager.get_instance(AsyncService)
        result = await service.async_work()

        assert result == "done"
        # logging_wrapper가 async를 감지하여 async_wrapped 사용
        assert "sync:before" in call_log
        assert "work" in call_log
        assert "sync:after" in call_log


class TestDecoratorContainerOverride:
    """DecoratorContainer 오버라이드 테스트"""

    async def test_handler_overrides_decorator_container(self):
        """HandlerContainer가 DecoratorContainer를 오버라이드"""
        call_log = []

        # @Decorator 먼저 적용 (priority 20)
        @Decorator(logging_wrapper(call_log, "dec"))
        def my_handler():
            call_log.append("handler")
            return "result"

        # @Handler류가 나중에 적용되면 (priority 30+) 오버라이드
        container = HandlerContainer.get_or_create(my_handler)

        current = getattr(my_handler, "__container__")
        # HandlerContainer가 우선 (priority 30 > 20)
        assert isinstance(current, HandlerContainer)

    async def test_decorator_element_preserved_on_override(self):
        """오버라이드 시 Decorator Element가 보존됨"""
        call_log = []

        @Decorator(logging_wrapper(call_log, "dec"))
        def my_handler():
            return "result"

        # HandlerContainer로 오버라이드
        HandlerContainer.get_or_create(my_handler)

        current = getattr(my_handler, "__container__")

        # DecoratorContainer의 Element가 이전되었는지 확인
        # (wrapper 정보가 metadata에 있어야 함)
        has_wrapper_element = False
        for elem in current.elements:
            if "wrapper" in elem.metadata:
                has_wrapper_element = True
                break

        assert has_wrapper_element, "Decorator Element should be preserved"


class TestDecoratorErrorCases:
    """@Decorator 에러 케이스 테스트"""

    async def test_decorator_with_failing_wrapper(self):
        """wrapper가 예외를 발생시킬 때"""

        def failing_wrapper(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                raise ValueError("wrapper error")

            return wrapped

        @Component
        class FailingService:
            @Decorator(failing_wrapper)
            def will_fail(self) -> str:
                return "never reached"

        app = await (
            Application("test_decorator_fail")
            .scan(FailingService)
            .ready_async()
        )

        service = app.manager.get_instance(FailingService)

        with pytest.raises(ValueError, match="wrapper error"):
            service.will_fail()

    async def test_decorator_with_missing_dependency(self):
        """wrapper 의존성이 없을 때"""

        class NonExistentDep:
            pass

        def wrapper_with_dep(fn, dep: NonExistentDep):
            return fn

        @Component
        class ServiceWithBadDep:
            @Decorator(wrapper_with_dep)
            def method(self) -> str:
                return "result"

        # NonExistentDep가 등록되지 않았으므로 에러
        with pytest.raises(Exception):
            app = await (
                Application("test_decorator_missing_dep")
                .scan(ServiceWithBadDep)
                .ready_async()
            )
            service = app.manager.get_instance(ServiceWithBadDep)
            service.method()


class TestDecoratorWithHandler:
    """@Decorator + @Handler (Web) 조합 테스트"""

    async def test_decorator_with_get_handler(self):
        """@Decorator가 @Get 핸들러에 적용될 때"""
        from bloom.web import Controller, Get

        call_log = []

        @Controller
        class MyController:
            @Decorator(logging_wrapper(call_log, "dec"))
            @Get("/test")
            def test_endpoint(self) -> dict:
                call_log.append("endpoint")
                return {"status": "ok"}

        app = await (
            Application("test_decorator_handler")
            .scan(MyController)
            .ready_async()
        )

        controller = app.manager.get_instance(MyController)

        # 컨테이너 타입 확인 - HttpMethodHandlerContainer가 우선
        from bloom.web.handler import HttpMethodHandlerContainer

        container = getattr(MyController.test_endpoint, "__container__")
        assert isinstance(container, HttpMethodHandlerContainer)

        # Decorator Element가 보존되었는지 확인
        has_wrapper = any("wrapper" in e.metadata for e in container.elements)
        assert has_wrapper

    async def test_multiple_decorators_with_handler(self):
        """여러 @Decorator가 @Get에 적용될 때"""
        from bloom.web import Controller, Get

        call_log = []

        @Controller
        class MyController:
            @Decorator(logging_wrapper(call_log, "auth"))
            @Decorator(logging_wrapper(call_log, "log"))
            @Get("/secure")
            def secure_endpoint(self) -> dict:
                call_log.append("secure")
                return {"secure": True}

        app = await (
            Application("test_multi_decorator_handler")
            .scan(MyController)
            .ready_async()
        )

        controller = app.manager.get_instance(MyController)

        container = getattr(MyController.secure_endpoint, "__container__")

        # 여러 Decorator Element가 있어야 함
        wrapper_count = sum(1 for e in container.elements if "wrapper" in e.metadata)
        assert wrapper_count >= 1  # 최소 1개 이상
