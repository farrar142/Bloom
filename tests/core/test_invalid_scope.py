"""InvalidScopeError 테스트

PROTOTYPE/REQUEST 스코프 컴포넌트에서 @Factory, @EventListener, @Task를 사용하면
InvalidScopeError가 발생하는지 테스트합니다.
"""

import pytest
from dataclasses import dataclass

from bloom import Application, Component
from bloom.core import Scope, ScopeEnum
from bloom.core.decorators import Factory
from bloom.core.exceptions import InvalidScopeError
from bloom.core.events import DomainEvent, EventListener


class TestInvalidScopeError:
    """InvalidScopeError 테스트"""

    async def test_factory_on_prototype_scope_raises_error(self):
        """PROTOTYPE 스코프 컴포넌트에서 @Factory 사용 시 에러 발생"""

        class Something:
            pass

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeConfig:
            @Factory
            def create_something(self) -> Something:
                return Something()

        with pytest.raises(InvalidScopeError) as exc_info:
            await Application("test").scan(PrototypeConfig).ready_async()

        error = exc_info.value
        assert error.component_type == PrototypeConfig
        assert error.handler_name == "create_something"
        assert error.handler_type == "Factory"
        assert error.scope == "prototype"
        assert "@Factory" in str(error)
        assert "SINGLETON" in str(error)

    async def test_factory_on_request_scope_raises_error(self):
        """REQUEST 스코프 컴포넌트에서 @Factory 사용 시 에러 발생"""

        class AnotherThing:
            pass

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestConfig:
            @Factory
            def create_another(self) -> AnotherThing:
                return AnotherThing()

        with pytest.raises(InvalidScopeError) as exc_info:
            await Application("test").scan(RequestConfig).ready_async()

        error = exc_info.value
        assert error.component_type == RequestConfig
        assert error.handler_type == "Factory"
        assert error.scope == "request"

    async def test_event_listener_on_prototype_scope_raises_error(self):
        """PROTOTYPE 스코프 컴포넌트에서 @EventListener 사용 시 에러 발생"""

        @dataclass
        class TestEvent(DomainEvent):
            message: str

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeEventHandler:
            @EventListener(TestEvent)
            def on_event(self, event: TestEvent):
                pass

        with pytest.raises(InvalidScopeError) as exc_info:
            await Application("test").scan(PrototypeEventHandler).ready_async()

        error = exc_info.value
        assert error.component_type == PrototypeEventHandler
        assert error.handler_name == "on_event"
        assert error.handler_type == "EventListener"
        assert error.scope == "prototype"

    async def test_event_listener_on_request_scope_raises_error(self):
        """REQUEST 스코프 컴포넌트에서 @EventListener 사용 시 에러 발생"""

        @dataclass
        class AnotherEvent(DomainEvent):
            data: str

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestEventHandler:
            @EventListener(AnotherEvent)
            def handle_event(self, event: AnotherEvent):
                pass

        with pytest.raises(InvalidScopeError) as exc_info:
            await Application("test").scan(RequestEventHandler).ready_async()

        error = exc_info.value
        assert error.handler_type == "EventListener"
        assert error.scope == "request"

    async def test_factory_on_singleton_scope_works(self):
        """SINGLETON 스코프 컴포넌트에서 @Factory 사용은 정상 동작"""

        class Widget:
            pass

        @Component
        class SingletonConfig:
            @Factory
            def create_widget(self) -> Widget:
                return Widget()

        # 에러 없이 정상 동작해야 함
        app = await Application("test").scan(SingletonConfig).ready_async()
        widget = app.manager.get_instance(Widget)
        assert widget is not None
        assert isinstance(widget, Widget)

    async def test_event_listener_on_singleton_scope_works(self):
        """SINGLETON 스코프 컴포넌트에서 @EventListener 사용은 정상 동작"""

        @dataclass
        class WorkingEvent(DomainEvent):
            value: int

        @Component
        class SingletonHandler:
            received_events: list

            def __init__(self):
                self.received_events = []

            @EventListener(WorkingEvent)
            def on_working_event(self, event: WorkingEvent):
                self.received_events.append(event)

        # 에러 없이 정상 동작해야 함
        app = await Application("test").scan(SingletonHandler).ready_async()
        handler = app.manager.get_instance(SingletonHandler)
        assert handler is not None

    async def test_multiple_handlers_on_prototype_all_fail(self):
        """PROTOTYPE 스코프에서 여러 singleton-only 핸들러가 있으면 첫 번째에서 에러"""

        class ThingA:
            pass

        class ThingB:
            pass

        @dataclass
        class MultiEvent(DomainEvent):
            x: int

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeMultiHandler:
            @Factory
            def create_a(self) -> ThingA:
                return ThingA()

            @Factory
            def create_b(self) -> ThingB:
                return ThingB()

            @EventListener(MultiEvent)
            def on_multi(self, event: MultiEvent):
                pass

        # 첫 번째 싱글톤-only 핸들러에서 에러 발생
        with pytest.raises(InvalidScopeError):
            await Application("test").scan(PrototypeMultiHandler).ready_async()

    async def test_error_message_is_informative(self):
        """에러 메시지가 충분히 상세한지 확인"""

        class ErrorTestThing:
            pass

        @Component
        @Scope(ScopeEnum.CALL)
        class ErrorTestConfig:
            @Factory
            def error_test_factory(self) -> ErrorTestThing:
                return ErrorTestThing()

        with pytest.raises(InvalidScopeError) as exc_info:
            await Application("test").scan(ErrorTestConfig).ready_async()

        message = str(exc_info.value)
        # 에러 메시지에 중요 정보가 포함되어야 함
        assert "ErrorTestConfig" in message
        assert "error_test_factory" in message
        assert "Factory" in message
        assert "prototype" in message.lower() or "PROTOTYPE" in message
        assert "SINGLETON" in message


class TestTaskOnInvalidScope:
    """@Task on PROTOTYPE/REQUEST 스코프 테스트"""

    async def test_task_on_prototype_scope_raises_error(self):
        """PROTOTYPE 스코프 컴포넌트에서 @Task 사용 시 에러 발생"""
        # Task는 별도 import 필요
        from bloom.task import Task

        @Component
        @Scope(ScopeEnum.CALL)
        class PrototypeTaskService:
            @Task
            def background_job(self) -> str:
                return "done"

        with pytest.raises(InvalidScopeError) as exc_info:
            await Application("test").scan(PrototypeTaskService).ready_async()

        error = exc_info.value
        assert error.component_type == PrototypeTaskService
        assert error.handler_name == "background_job"
        assert error.handler_type == "Task"
        assert error.scope == "prototype"

    async def test_task_on_request_scope_raises_error(self):
        """REQUEST 스코프 컴포넌트에서 @Task 사용 시 에러 발생"""
        from bloom.task import Task

        @Component
        @Scope(ScopeEnum.REQUEST)
        class RequestTaskService:
            @Task(name="my-task")
            def request_job(self) -> str:
                return "result"

        with pytest.raises(InvalidScopeError) as exc_info:
            await Application("test").scan(RequestTaskService).ready_async()

        error = exc_info.value
        assert error.handler_type == "Task"
        assert error.scope == "request"

    async def test_task_on_singleton_scope_works(self):
        """SINGLETON 스코프 컴포넌트에서 @Task 사용은 정상 동작"""
        from bloom.task import Task

        @Component
        class SingletonTaskService:
            @Task
            def working_task(self) -> str:
                return "works"

        # 에러 없이 정상 동작해야 함
        app = await Application("test").scan(SingletonTaskService).ready_async()
        service = app.manager.get_instance(SingletonTaskService)
        assert service is not None
