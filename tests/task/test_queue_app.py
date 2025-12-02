"""QueueApplication 테스트"""

import pytest
import asyncio

from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.task import (
    Task,
    DistributedTaskBackend,
    InMemoryBroker,
    QueueApplication,
)


@pytest.fixture
async def app_with_queue(reset_container_manager):
    """QueueApplication이 설정된 앱"""

    @Component
    class EmailService:
        @Task(name="send_email")
        def send_email(self, to: str, subject: str) -> str:
            return f"Sent to {to}: {subject}"

        @Task(name="send_notification")
        async def send_notification(self, user_id: int) -> str:
            return f"Notified user {user_id}"

    @Component
    class TaskConfig:
        @Factory
        def task_backend(self) -> DistributedTaskBackend:
            broker = InMemoryBroker()
            return DistributedTaskBackend(broker)

    app = Application("test_queue")
    app.scan(__name__)
    await app.ready_async()

    return app


class TestQueueApplication:
    """QueueApplication 기본 테스트"""

    async def test_queue_property(self, app_with_queue):
        """app.queue 프로퍼티가 QueueApplication을 반환"""
        queue = app_with_queue.queue

        assert isinstance(queue, QueueApplication)
        assert queue.application is app_with_queue

    async def test_queue_backend_lazy_resolve(self, app_with_queue):
        """QueueApplication.backend가 lazy하게 DistributedTaskBackend 조회"""
        queue = app_with_queue.queue

        # backend 프로퍼티 접근 시 ContainerManager에서 조회
        backend = queue.backend

        assert isinstance(backend, DistributedTaskBackend)

    async def test_queue_registry_before_startup(self, app_with_queue):
        """startup() 전에는 registry가 None"""
        queue = app_with_queue.queue

        # startup 전에는 registry가 None
        registry = queue.registry
        assert registry is None

    @pytest.mark.asyncio
    async def test_startup_registers_tasks(self, app_with_queue):
        """startup() 시 태스크가 레지스트리에 등록됨"""
        queue = app_with_queue.queue

        await queue.startup()

        try:
            # startup 후에는 registry가 설정됨
            registry = queue.registry
            assert registry is not None

            # 태스크 이름은 ComponentClass.method_name 형식이거나
            # @Task(name="...") 으로 지정한 이름
            tasks = registry.names()
            # "send_email" 또는 "EmailService.send_email" 형태
            assert any("send_email" in t for t in tasks)
            assert any("send_notification" in t for t in tasks)
        finally:
            await queue.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown(self, app_with_queue):
        """shutdown() 시 정상 종료"""
        queue = app_with_queue.queue

        await queue.startup()
        await queue.shutdown()

        # is_running이 False여야 함
        assert not queue._is_running


class TestQueueApplicationCallbacks:
    """라이프사이클 콜백 테스트"""

    @pytest.mark.asyncio
    async def test_on_startup_callback(self, app_with_queue):
        """on_startup 콜백 실행"""
        queue = app_with_queue.queue
        callback_called = []

        async def startup_callback():
            callback_called.append("startup")

        queue.on_startup(startup_callback)

        await queue.startup()
        try:
            assert "startup" in callback_called
        finally:
            await queue.shutdown()

    @pytest.mark.asyncio
    async def test_on_shutdown_callback(self, app_with_queue):
        """on_shutdown 콜백 실행"""
        queue = app_with_queue.queue
        callback_called = []

        async def shutdown_callback():
            callback_called.append("shutdown")

        queue.on_shutdown(shutdown_callback)

        await queue.startup()
        await queue.shutdown()

        assert "shutdown" in callback_called


class TestQueueApplicationWithoutBackend:
    """DistributedTaskBackend 없이 QueueApplication 사용 시"""

    async def test_queue_without_backend_raises_error(self, reset_container_manager):
        """DistributedTaskBackend가 없으면 startup 시 에러"""

        @Component
        class DummyService:
            pass

        app = Application("test_no_backend")
        app.scan(__name__)
        await app.ready_async()

        queue = app.queue

        # backend가 None
        assert queue.backend is None

    @pytest.mark.asyncio
    async def test_startup_without_backend_raises(self, reset_container_manager):
        """DistributedTaskBackend 없이 startup() 호출 시 RuntimeError"""

        @Component
        class DummyService:
            pass

        app = Application("test_no_backend")
        app.scan(__name__)
        await app.ready_async()

        queue = app.queue

        with pytest.raises(RuntimeError, match="DistributedTaskBackend"):
            await queue.startup()
