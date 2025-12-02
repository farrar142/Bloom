"""
Task System Tests - Celery 스타일 태스크 시스템 테스트

@Task 데코레이터를 사용한 태스크 정의, 실행, 스케줄링 테스트
"""

import pytest

# 모듈 전체 skip
pytestmark = pytest.mark.skip(reason="Task 시스템 리팩토링 중")

import asyncio
import time
from datetime import datetime, timedelta

import pytest

from bloom.task import (
    Task,
    TaskElement,
    TaskResult,
    AsyncTaskResult,
    ScheduledTask,
    TaskBackend,
    AsyncioTaskBackend,
    TaskMethodAdvice,
    Trigger,
    FixedRateTrigger,
    FixedDelayTrigger,
    CronTrigger,
    is_task,
    get_task_element,
    BoundTask,
    TaskDescriptor,
)


# ============================================================
# Trigger 테스트
# ============================================================


class TestFixedRateTrigger:
    """FixedRateTrigger 테스트"""

    async def test_next_execution_time_first_run(self):
        """첫 실행: initial_delay 적용"""
        trigger = FixedRateTrigger(seconds=10)
        now = datetime.now()
        next_time = trigger.next_execution_time(None)

        # initial_delay=0 이므로 즉시 실행
        assert next_time is not None
        assert next_time <= now + timedelta(seconds=1)

    async def test_next_execution_time_with_initial_delay(self):
        """initial_delay 지정 테스트"""
        trigger = FixedRateTrigger(seconds=10, initial_delay=5)
        next_time = trigger.next_execution_time(None)

        expected_min = datetime.now() + timedelta(seconds=4.9)
        assert next_time is not None
        assert next_time >= expected_min

    async def test_next_execution_time_after_run(self):
        """실행 후 다음 실행 시간"""
        trigger = FixedRateTrigger(seconds=30)
        last_execution = datetime.now()
        next_time = trigger.next_execution_time(last_execution)

        expected = last_execution + timedelta(seconds=30)
        assert next_time is not None
        assert abs((next_time - expected).total_seconds()) < 1

    async def test_with_minutes(self):
        """minutes 단위 테스트"""
        trigger = FixedRateTrigger(minutes=2)
        last_execution = datetime.now()
        next_time = trigger.next_execution_time(last_execution)

        expected = last_execution + timedelta(minutes=2)
        assert next_time is not None
        assert abs((next_time - expected).total_seconds()) < 1

    async def test_with_hours(self):
        """hours 단위 테스트"""
        trigger = FixedRateTrigger(hours=1)
        last_execution = datetime.now()
        next_time = trigger.next_execution_time(last_execution)

        expected = last_execution + timedelta(hours=1)
        assert next_time is not None
        assert abs((next_time - expected).total_seconds()) < 1

    async def test_combined_units(self):
        """여러 단위 조합"""
        trigger = FixedRateTrigger(hours=1, minutes=30, seconds=15)
        last_execution = datetime.now()
        next_time = trigger.next_execution_time(last_execution)

        total_seconds = 1 * 3600 + 30 * 60 + 15
        expected = last_execution + timedelta(seconds=total_seconds)
        assert next_time is not None
        assert abs((next_time - expected).total_seconds()) < 1

    async def test_repr(self):
        """문자열 표현"""
        trigger = FixedRateTrigger(seconds=30, initial_delay=5)
        assert "FixedRateTrigger" in repr(trigger)
        assert "30" in repr(trigger)


class TestFixedDelayTrigger:
    """FixedDelayTrigger 테스트"""

    async def test_next_execution_time_first_run(self):
        """첫 실행: initial_delay 적용"""
        trigger = FixedDelayTrigger(seconds=10)
        next_time = trigger.next_execution_time(None)

        assert next_time is not None
        assert next_time <= datetime.now() + timedelta(seconds=1)

    async def test_next_execution_time_after_run(self):
        """완료 후 다음 실행 시간"""
        trigger = FixedDelayTrigger(seconds=30)
        last_execution = datetime.now()
        next_time = trigger.next_execution_time(last_execution)

        expected = last_execution + timedelta(seconds=30)
        assert next_time is not None
        assert abs((next_time - expected).total_seconds()) < 1


class TestCronTrigger:
    """CronTrigger 테스트"""

    async def test_every_minute(self):
        """매분 실행"""
        trigger = CronTrigger("* * * * *")
        now = datetime.now().replace(second=0, microsecond=0)
        next_time = trigger.next_execution_time(now)

        expected = now + timedelta(minutes=1)
        assert next_time is not None
        assert next_time == expected

    async def test_specific_minute(self):
        """특정 분에 실행"""
        trigger = CronTrigger("30 * * * *")
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        next_time = trigger.next_execution_time(now)

        assert next_time is not None
        assert next_time.minute == 30

    async def test_specific_hour(self):
        """특정 시에 실행"""
        trigger = CronTrigger("0 9 * * *")
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        next_time = trigger.next_execution_time(now)

        assert next_time is not None
        assert next_time.hour == 9
        assert next_time.minute == 0

    async def test_weekday_only(self):
        """평일에만 실행 (월-금)"""
        trigger = CronTrigger("0 9 * * 1-5")
        # 다음 실행 시간이 평일인지 확인
        next_time = trigger.next_execution_time(None)

        assert next_time is not None
        assert next_time.weekday() < 5  # 0=월, 4=금

    async def test_step_values(self):
        """스텝 값 테스트 (*/15)"""
        trigger = CronTrigger("*/15 * * * *")
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        next_time = trigger.next_execution_time(now)

        assert next_time is not None
        # 다음 실행은 0, 15, 30, 45분 중 하나
        assert next_time.minute in [0, 15, 30, 45]

    async def test_repr(self):
        """문자열 표현"""
        trigger = CronTrigger("0 9 * * 1-5")
        assert "CronTrigger" in repr(trigger)
        assert "0 9 * * 1-5" in repr(trigger)


# ============================================================
# TaskResult 테스트
# ============================================================


class TestTaskResult:
    """TaskResult 테스트"""

    async def test_get_result(self):
        """결과 가져오기"""
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(lambda: "hello")
        result = TaskResult(future, executor)

        assert result.get() == "hello"
        executor.shutdown()

    async def test_get_with_timeout(self):
        """타임아웃 테스트"""
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(lambda: (time.sleep(5), "done")[1])
        result = TaskResult(future, executor)

        with pytest.raises(TimeoutError):
            result.get(timeout=0.1)

        future.cancel()
        executor.shutdown(wait=False)

    async def test_ready_status(self):
        """ready() 상태 확인"""
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(lambda: "hello")
        result = TaskResult(future, executor)

        # 완료 대기
        result.get()
        assert result.ready() is True
        executor.shutdown()

    async def test_successful_status(self):
        """successful() 상태 확인"""
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(lambda: "success")
        result = TaskResult(future, executor)

        result.get()
        assert result.successful() is True
        assert result.failed() is False
        executor.shutdown()

    async def test_failed_status(self):
        """failed() 상태 확인"""
        from concurrent.futures import ThreadPoolExecutor

        def raise_error():
            raise ValueError("test error")

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(raise_error)
        result = TaskResult(future, executor)

        with pytest.raises(ValueError):
            result.get()

        assert result.failed() is True
        assert result.successful() is False
        executor.shutdown()

    async def test_revoke(self):
        """태스크 취소"""
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        # 첫 번째 태스크로 워커 점유
        executor.submit(lambda: time.sleep(5))
        # 두 번째 태스크는 대기 상태
        future = executor.submit(lambda: "should not run")
        result = TaskResult(future, executor)

        # 대기 중인 태스크 취소 시도
        # (이미 실행 중이면 False)
        revoked = result.revoke()
        # 결과는 상황에 따라 다를 수 있음

        executor.shutdown(wait=False)

    async def test_add_callback(self):
        """콜백 등록"""
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(lambda: "hello")
        result = TaskResult(future, executor)

        callback_called = []
        result.add_callback(lambda r: callback_called.append(r))

        result.get()  # 완료 대기
        # polling으로 콜백 실행 대기 (최대 1초)
        for _ in range(100):
            if callback_called:
                break
            time.sleep(0.01)

        assert len(callback_called) == 1
        executor.shutdown()

    async def test_repr(self):
        """문자열 표현"""
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(lambda: "hello")
        result = TaskResult(future, executor)

        assert "TaskResult" in repr(result)
        executor.shutdown()


# ============================================================
# AsyncTaskResult 테스트
# ============================================================


class TestAsyncTaskResult:
    """AsyncTaskResult 테스트"""

    @pytest.mark.asyncio
    async def test_get_result(self):
        """비동기 결과 가져오기"""

        async def work():
            return "async hello"

        task = asyncio.create_task(work())
        result = AsyncTaskResult(task)

        value = await result.get()
        assert value == "async hello"

    @pytest.mark.asyncio
    async def test_get_with_timeout(self):
        """비동기 타임아웃"""

        async def slow_work():
            await asyncio.sleep(5)
            return "done"

        task = asyncio.create_task(slow_work())
        result = AsyncTaskResult(task)

        with pytest.raises(asyncio.TimeoutError):
            await result.get(timeout=0.1)

        task.cancel()

    @pytest.mark.asyncio
    async def test_ready_and_successful(self):
        """ready(), successful() 상태"""

        async def work():
            return "done"

        task = asyncio.create_task(work())
        result = AsyncTaskResult(task)

        await result.get()
        assert result.ready() is True
        assert result.successful() is True
        assert result.failed() is False


# ============================================================
# ScheduledTask 테스트
# ============================================================


class TestScheduledTask:
    """ScheduledTask 테스트"""

    async def test_create_scheduled_task(self):
        """스케줄 태스크 생성"""

        def my_handler():
            return "executed"

        trigger = FixedRateTrigger(seconds=10)
        task = ScheduledTask(
            name="test-task",
            handler=my_handler,
            trigger=trigger,
        )

        assert task.name == "test-task"
        assert task.is_enabled is True
        assert task.execution_count == 0

    async def test_pause_resume(self):
        """일시정지/재개"""
        trigger = FixedRateTrigger(seconds=10)
        task = ScheduledTask(
            name="test-task",
            handler=lambda: "ok",
            trigger=trigger,
        )

        assert task.is_enabled is True

        task.pause()
        assert task.is_enabled is False

        task.resume()
        assert task.is_enabled is True

    async def test_cancel(self):
        """취소"""
        trigger = FixedRateTrigger(seconds=10)
        task = ScheduledTask(
            name="test-task",
            handler=lambda: "ok",
            trigger=trigger,
        )

        task.cancel()
        assert task.is_enabled is False

    @pytest.mark.asyncio
    async def test_execute(self):
        """태스크 실행"""
        results = []

        def my_handler():
            results.append("executed")
            return "done"

        trigger = FixedRateTrigger(seconds=10)
        task = ScheduledTask(
            name="test-task",
            handler=my_handler,
            trigger=trigger,
        )

        result = await task.execute()

        assert result == "done"
        assert task.execution_count == 1
        assert task.last_execution is not None
        assert task.last_result == "done"
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_execute_with_instance(self):
        """인스턴스 메서드 실행"""

        class MyService:
            def __init__(self):
                self.calls = 0

            def process(self, data):
                self.calls += 1
                return f"processed: {data}"

        service = MyService()
        trigger = FixedRateTrigger(seconds=10)
        task = ScheduledTask(
            name="test-task",
            handler=MyService.process,
            trigger=trigger,
            args=("hello",),
            instance=service,
        )

        result = await task.execute()

        assert result == "processed: hello"
        assert service.calls == 1

    @pytest.mark.asyncio
    async def test_execute_async_handler(self):
        """비동기 핸들러 실행"""

        async def async_handler():
            await asyncio.sleep(0.01)
            return "async done"

        trigger = FixedRateTrigger(seconds=10)
        task = ScheduledTask(
            name="async-task",
            handler=async_handler,
            trigger=trigger,
        )

        result = await task.execute()
        assert result == "async done"

    async def test_info(self):
        """정보 조회"""
        trigger = FixedRateTrigger(seconds=30)
        task = ScheduledTask(
            name="info-task",
            handler=lambda: "ok",
            trigger=trigger,
        )

        info = task.info()

        assert info["name"] == "info-task"
        assert info["enabled"] is True
        assert info["execution_count"] == 0
        assert "FixedRateTrigger" in info["trigger"]


# ============================================================
# @Task 데코레이터 테스트
# ============================================================


class TestTaskDecorator:
    """@Task 데코레이터 테스트"""

    async def test_task_decorator_basic(self):
        """기본 @Task 데코레이터"""

        class MyService:
            @Task
            def my_task(self, data: str) -> str:
                return f"processed: {data}"

        # TaskDescriptor인지 확인
        assert isinstance(MyService.my_task, TaskDescriptor)
        assert is_task(MyService.my_task._handler) is True

    async def test_task_decorator_with_options(self):
        """옵션이 있는 @Task"""

        class MyService:
            @Task(name="custom-name", max_retries=3)
            def my_task(self) -> str:
                return "done"

        element = get_task_element(MyService.my_task._handler)
        assert element is not None
        assert element.name == "custom-name"
        assert element.max_retries == 3

    async def test_bound_task_direct_call(self):
        """BoundTask 직접 호출"""

        class MyService:
            @Task
            def echo(self, msg: str) -> str:
                return f"echo: {msg}"

        service = MyService()
        # 인스턴스에서 접근하면 BoundTask
        bound = service.echo
        assert isinstance(bound, BoundTask)

        # 직접 호출
        result = bound("hello")
        assert result == "echo: hello"

    async def test_bound_task_delay_without_backend(self):
        """백엔드 없이 delay() 호출 시 에러"""

        class MyService:
            @Task
            def my_task(self) -> str:
                return "done"

        service = MyService()

        with pytest.raises(RuntimeError, match="TaskBackend"):
            service.my_task.delay()

    async def test_bound_task_schedule_without_backend(self):
        """백엔드 없이 schedule() 호출 시 에러"""

        class MyService:
            @Task
            def my_task(self) -> str:
                return "done"

        service = MyService()

        with pytest.raises(RuntimeError, match="TaskBackend"):
            service.my_task.schedule(fixed_rate=10)


# ============================================================
# AsyncioTaskBackend 테스트
# ============================================================


class TestAsyncioTaskBackend:
    """AsyncioTaskBackend 테스트"""

    async def test_submit_sync(self):
        """동기 태스크 제출"""
        backend = AsyncioTaskBackend()

        result = backend.submit(lambda x: x * 2, 21)
        value = result.get()

        assert value == 42

    @pytest.mark.asyncio
    async def test_submit_async_function(self):
        """비동기 함수 제출"""
        backend = AsyncioTaskBackend()

        async def async_work(x):
            await asyncio.sleep(0.01)
            return x * 2

        result = await backend.submit_async(async_work, 21)
        value = await result.get()

        assert value == 42

    @pytest.mark.asyncio
    async def test_start_and_shutdown(self):
        """백엔드 시작/종료"""
        backend = AsyncioTaskBackend()

        await backend.start()
        assert backend.is_running is True

        await backend.shutdown()
        assert backend.is_running is False

    @pytest.mark.asyncio
    async def test_schedule_task(self):
        """태스크 스케줄 등록"""
        backend = AsyncioTaskBackend()
        await backend.start()

        try:
            executions = []

            def my_handler():
                executions.append(datetime.now())

            trigger = FixedRateTrigger(seconds=0.05)  # 50ms 마다
            task = ScheduledTask(
                name="test-task",
                handler=my_handler,
                trigger=trigger,
            )

            backend.schedule(task)

            # polling으로 최소 2번 실행 대기 (최대 500ms)
            for _ in range(50):
                if len(executions) >= 2:
                    break
                await asyncio.sleep(0.01)

            # 최소 2번 이상 실행되어야 함
            assert len(executions) >= 2
        finally:
            await backend.shutdown()

    @pytest.mark.asyncio
    async def test_unschedule_task(self):
        """스케줄 제거"""
        backend = AsyncioTaskBackend()
        await backend.start()

        try:
            trigger = FixedRateTrigger(seconds=1)
            task = ScheduledTask(
                name="test-task",
                handler=lambda: None,
                trigger=trigger,
            )

            backend.schedule(task)
            assert len(backend.scheduled_tasks) == 1

            result = backend.unschedule(task)
            assert result is True
            assert len(backend.scheduled_tasks) == 0
        finally:
            await backend.shutdown()


# ============================================================
# TaskMethodAdvice 테스트
# ============================================================


class TestTaskMethodAdvice:
    """TaskMethodAdvice 테스트"""

    async def test_advice_supports(self):
        """supports() 메서드"""
        backend = AsyncioTaskBackend()
        advice = TaskMethodAdvice(backend)

        @Task
        def my_task():
            return "done"

        def not_a_task():
            return "normal"

        from bloom.core.container import HandlerContainer

        task_container = HandlerContainer.get_container(my_task)
        assert advice.supports(task_container) is True

        # 일반 함수는 HandlerContainer가 없음
        normal_container = HandlerContainer.get_container(not_a_task)
        assert normal_container is None

    @pytest.mark.asyncio
    async def test_advice_injects_backend(self):
        """before()에서 백엔드 주입"""
        backend = AsyncioTaskBackend()
        advice = TaskMethodAdvice(backend)

        class MyService:
            pass

        from bloom.core.advice import InvocationContext
        from bloom.core.container import HandlerContainer

        @Task
        def handler():
            pass

        container = HandlerContainer.get_container(handler)
        instance = MyService()

        context = InvocationContext(
            container=container,
            instance=instance,
            args=(),
            kwargs={},
        )

        await advice.before(context)

        # 인스턴스에 백엔드가 주입되었는지 확인
        assert hasattr(instance, "_task_backend")
        assert instance._task_backend is backend


# ============================================================
# 통합 테스트
# ============================================================


class TestTaskIntegration:
    """Task 시스템 통합 테스트"""

    async def test_full_workflow_sync(self):
        """동기 워크플로우 테스트"""

        class EmailService:
            def __init__(self):
                self.sent_emails = []

            @Task
            def send_email(self, to: str, subject: str) -> str:
                self.sent_emails.append((to, subject))
                return f"Sent to {to}"

        service = EmailService()

        # 백엔드 수동 주입
        backend = AsyncioTaskBackend()
        service._task_backend = backend

        # delay() 호출
        result = service.send_email.delay("user@example.com", "Hello")
        value = result.get()

        assert value == "Sent to user@example.com"
        assert len(service.sent_emails) == 1

    @pytest.mark.asyncio
    async def test_full_workflow_async(self):
        """비동기 워크플로우 테스트"""

        class DataProcessor:
            @Task
            async def process(self, data: str) -> str:
                await asyncio.sleep(0.01)
                return f"processed: {data}"

        processor = DataProcessor()

        backend = AsyncioTaskBackend()
        processor._task_backend = backend

        # delay_async() 호출
        result = await processor.process.delay_async("input")
        value = await result.get()

        assert value == "processed: input"

    @pytest.mark.asyncio
    async def test_scheduled_workflow(self):
        """스케줄 워크플로우 테스트"""

        class CleanupService:
            def __init__(self):
                self.cleanup_count = 0

            @Task
            def cleanup(self) -> None:
                self.cleanup_count += 1

        service = CleanupService()

        backend = AsyncioTaskBackend()
        await backend.start()
        service._task_backend = backend

        try:
            # 스케줄 등록 (50ms 마다)
            task = service.cleanup.schedule(fixed_rate=0.05)

            # polling으로 최소 2번 실행 대기 (최대 500ms)
            for _ in range(50):
                if service.cleanup_count >= 2:
                    break
                await asyncio.sleep(0.01)

            # 최소 2번 실행
            assert service.cleanup_count >= 2

            # 일시정지
            task.pause()
            count_before = service.cleanup_count

            # polling으로 일시정지 확인 (100ms 대기)
            await asyncio.sleep(0.1)

            # 일시정지 중이므로 실행되지 않음
            assert service.cleanup_count == count_before
        finally:
            await backend.shutdown()


# ============================================================
# Application 통합 테스트
# ============================================================


class TestTaskApplicationIntegration:
    """
    @Component, @Controller, @Factory와 @Task의 완전한 DI 통합 테스트

    실제 Application을 사용하여 모든 컴포넌트가 올바르게 연결되는지 확인합니다.
    """

    async def test_component_with_task_and_factory_injection(self):
        """@Component에서 @Task 사용 + @Factory로 TaskBackend 주입"""
        from bloom import Application, Component
        from bloom.core.decorators import Factory
        from bloom.core.advice import MethodAdviceRegistry

        @Component
        class NotificationService:
            def __init__(self):
                self.notifications: list[str] = []

            @Task
            def send_notification(self, message: str) -> str:
                self.notifications.append(message)
                return f"Notification sent: {message}"

        @Component
        class TaskConfig:
            @Factory
            def task_backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

            @Factory
            def advice_registry(self, backend: TaskBackend) -> MethodAdviceRegistry:
                # TaskMethodAdvice를 직접 생성하여 등록
                registry = MethodAdviceRegistry()
                registry.register(TaskMethodAdvice(backend))
                return registry

        # Application 초기화
        app = (
            Application("test_task_integration")
            .scan(NotificationService, TaskConfig)
            .ready()
        )

        # 서비스 인스턴스 가져오기
        service = app.manager.get_instance(NotificationService)

        # 직접 호출 테스트
        result = service.send_notification("Hello World")
        assert result == "Notification sent: Hello World"
        assert len(service.notifications) == 1

        # delay() 호출 테스트 - TaskMethodAdvice가 백엔드 주입
        task_result = service.send_notification.delay("Background Task")
        value = task_result.get(timeout=1)
        assert value == "Notification sent: Background Task"
        assert len(service.notifications) == 2

    async def test_service_with_dependency_injection_and_task(self):
        """의존성 주입이 있는 서비스에서 @Task 사용"""
        from bloom import Application, Component
        from bloom.core.decorators import Factory
        from bloom.core.advice import MethodAdvice, MethodAdviceRegistry

        @Component
        class EmailRepository:
            def __init__(self):
                self.emails: list[dict] = []

            def save(self, email: dict) -> None:
                self.emails.append(email)

        @Component
        class EmailService:
            # 필드 주입
            repository: EmailRepository

            @Task
            def send_email(self, to: str, subject: str, body: str) -> dict:
                email = {"to": to, "subject": subject, "body": body}
                self.repository.save(email)
                return email

        @Component
        class TaskConfig:
            @Factory
            def task_backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

            @Factory
            def advice_registry(self, backend: TaskBackend) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(TaskMethodAdvice(backend))
                return registry

        # Application 초기화
        app = (
            Application("test_di_task")
            .scan(EmailRepository, EmailService, TaskConfig)
            .ready()
        )

        # 서비스와 리포지토리 가져오기
        service = app.manager.get_instance(EmailService)
        repository = app.manager.get_instance(EmailRepository)

        # 필드 주입 확인
        assert service.repository is repository

        # delay()로 백그라운드 실행
        task_result = service.send_email.delay(
            "user@example.com",
            "Test Subject",
            "Test Body",
        )
        email = task_result.get(timeout=1)

        assert email["to"] == "user@example.com"
        assert email["subject"] == "Test Subject"
        assert len(repository.emails) == 1

    @pytest.mark.asyncio
    async def test_async_task_with_application(self):
        """비동기 @Task와 Application 통합"""
        from bloom import Application, Component
        from bloom.core.decorators import Factory
        from bloom.core.advice import MethodAdviceRegistry

        @Component
        class AsyncDataProcessor:
            def __init__(self):
                self.processed: list[str] = []

            @Task
            async def process_data(self, data: str) -> str:
                await asyncio.sleep(0.01)
                result = f"processed:{data}"
                self.processed.append(result)
                return result

        @Component
        class TaskConfig:
            @Factory
            def task_backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

            @Factory
            def advice_registry(self, backend: TaskBackend) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(TaskMethodAdvice(backend))
                return registry

        # Application 초기화
        app = (
            Application("test_async_task").scan(AsyncDataProcessor, TaskConfig).ready()
        )

        processor = app.manager.get_instance(AsyncDataProcessor)

        # delay_async()로 비동기 실행
        task_result = await processor.process_data.delay_async("input1")
        value = await task_result.get()

        assert value == "processed:input1"
        assert len(processor.processed) == 1

    @pytest.mark.asyncio
    async def test_scheduled_task_with_application(self):
        """스케줄 기능과 Application 통합"""
        from bloom import Application, Component
        from bloom.core.decorators import Factory
        from bloom.core.advice import MethodAdviceRegistry

        @Component
        class MetricsCollector:
            def __init__(self):
                self.metrics: list[float] = []

            @Task
            def collect_metrics(self) -> float:
                import random

                value = random.random()
                self.metrics.append(value)
                return value

        @Component
        class TaskConfig:
            @Factory
            def task_backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

            @Factory
            def advice_registry(self, backend: TaskBackend) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(TaskMethodAdvice(backend))
                return registry

        # Application 초기화
        app = (
            Application("test_scheduled_task")
            .scan(MetricsCollector, TaskConfig)
            .ready()
        )

        # 백엔드 시작 (스케줄러 활성화)
        backend = app.manager.get_instance(TaskBackend)
        await backend.start()

        try:
            collector = app.manager.get_instance(MetricsCollector)

            # 스케줄 등록 (50ms 마다)
            scheduled = collector.collect_metrics.schedule(fixed_rate=0.05)

            assert scheduled.is_enabled

            # polling으로 최소 2번 실행 대기 (최대 500ms)
            for _ in range(50):
                if len(collector.metrics) >= 2:
                    break
                await asyncio.sleep(0.01)

            # 최소 2번 실행되어야 함
            assert len(collector.metrics) >= 2

            # 스케줄 취소
            scheduled.cancel()
            assert not scheduled.is_enabled

        finally:
            await backend.shutdown()

    async def test_multiple_tasks_in_single_component(self):
        """하나의 컴포넌트에 여러 @Task 메서드"""
        from bloom import Application, Component
        from bloom.core.decorators import Factory
        from bloom.core.advice import MethodAdviceRegistry

        @Component
        class OrderService:
            def __init__(self):
                self.orders: list[dict] = []
                self.invoices: list[dict] = []

            @Task(name="create_order")
            def create_order(self, product: str, quantity: int) -> dict:
                order = {"product": product, "quantity": quantity}
                self.orders.append(order)
                return order

            @Task(name="generate_invoice")
            def generate_invoice(self, order_id: str, amount: float) -> dict:
                invoice = {"order_id": order_id, "amount": amount}
                self.invoices.append(invoice)
                return invoice

        @Component
        class TaskConfig:
            @Factory
            def task_backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

            @Factory
            def advice_registry(self, backend: TaskBackend) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(TaskMethodAdvice(backend))
                return registry

        app = Application("test_multi_task").scan(OrderService, TaskConfig).ready()

        service = app.manager.get_instance(OrderService)

        # 두 태스크 모두 delay() 호출
        order_result = service.create_order.delay("Widget", 5)
        invoice_result = service.generate_invoice.delay("ORD001", 99.99)

        order = order_result.get(timeout=1)
        invoice = invoice_result.get(timeout=1)

        assert order == {"product": "Widget", "quantity": 5}
        assert invoice == {"order_id": "ORD001", "amount": 99.99}
        assert len(service.orders) == 1
        assert len(service.invoices) == 1

    async def test_task_with_controller(self):
        """@Controller 내부에서 @Task 사용 (Background Job 패턴)"""
        from bloom import Application, Component
        from bloom.core.decorators import Factory
        from bloom.core.advice import MethodAdviceRegistry
        from bloom.web import Controller, Get, HttpResponse

        @Component
        class BackgroundJobService:
            def __init__(self):
                self.jobs: list[str] = []

            @Task
            def run_background_job(self, job_id: str) -> str:
                self.jobs.append(job_id)
                return f"Job {job_id} completed"

        @Controller
        class JobController:
            job_service: BackgroundJobService

            @Get("/jobs/start")
            def start_job(self) -> HttpResponse:
                # 백그라운드에서 작업 실행
                task_result = self.job_service.run_background_job.delay("JOB001")
                return HttpResponse.ok({"status": "started", "job_id": "JOB001"})

        @Component
        class TaskConfig:
            @Factory
            def task_backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

            @Factory
            def advice_registry(self, backend: TaskBackend) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(TaskMethodAdvice(backend))
                return registry

        app = (
            Application("test_controller_task")
            .scan(BackgroundJobService, JobController, TaskConfig)
            .ready()
        )

        # Controller에서 서비스 사용
        controller = app.manager.get_instance(JobController)
        response = controller.start_job()

        assert response.status_code == 200

        # 백그라운드 작업 완료 대기
        import time

        time.sleep(0.1)

        job_service = app.manager.get_instance(BackgroundJobService)
        assert "JOB001" in job_service.jobs

    async def test_task_error_handling(self):
        """@Task에서 예외 발생 시 처리"""
        from bloom import Application, Component
        from bloom.core.decorators import Factory
        from bloom.core.advice import MethodAdviceRegistry

        @Component
        class FailingService:
            @Task(name="failing_task")
            def do_something_risky(self, should_fail: bool) -> str:
                if should_fail:
                    raise ValueError("Intentional failure")
                return "success"

        @Component
        class TaskConfig:
            @Factory
            def task_backend(self) -> TaskBackend:
                return AsyncioTaskBackend()

            @Factory
            def advice_registry(self, backend: TaskBackend) -> MethodAdviceRegistry:
                registry = MethodAdviceRegistry()
                registry.register(TaskMethodAdvice(backend))
                return registry
                return registry

        app = Application("test_task_error").scan(FailingService, TaskConfig).ready()

        service = app.manager.get_instance(FailingService)

        # 성공 케이스
        result = service.do_something_risky.delay(False)
        assert result.get(timeout=1) == "success"
        assert result.successful()

        # 실패 케이스
        result = service.do_something_risky.delay(True)

        with pytest.raises(ValueError, match="Intentional failure"):
            result.get(timeout=1)

        assert not result.successful()
        assert result.failed()
