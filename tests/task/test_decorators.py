"""bloom.core.task.decorators 테스트"""

import pytest

from bloom.core.task.app import TaskApp, BoundTask
from bloom.core.task.decorators import (
    Task,
    get_task_metadata,
    has_task_metadata,
    get_task_methods,
    scan_task_methods,
)
from bloom.core.task.models import TaskPriority


class TestTaskDecorator:
    """@Task 데코레이터 테스트"""

    def test_task_decorator_without_app(self):
        """앱 없이 데코레이터 사용"""

        @Task()
        async def my_task():
            pass

        assert has_task_metadata(my_task)
        metadata = get_task_metadata(my_task)
        assert metadata is not None
        assert metadata.queue == "default"

    def test_task_decorator_with_options(self):
        """옵션과 함께 데코레이터"""

        @Task(
            queue="high",
            retry=3,
            timeout=60.0,
            priority=TaskPriority.HIGH,
        )
        async def my_task():
            pass

        metadata = get_task_metadata(my_task)
        assert metadata is not None
        assert metadata.queue == "high"
        assert metadata.retry == 3
        assert metadata.timeout == 60.0
        assert metadata.priority == TaskPriority.HIGH

    def test_task_decorator_with_app(self):
        """앱과 함께 데코레이터"""
        app = TaskApp("test")

        @Task(app)
        async def my_task():
            pass

        assert isinstance(my_task, BoundTask)
        assert my_task.name.endswith("my_task")


class TestClassMethodDecorator:
    """클래스 메서드에서의 @Task 데코레이터"""

    def test_task_on_method(self):
        """메서드에 태스크 적용"""

        class MyService:
            @Task(queue="emails")
            async def send_email(self, to: str) -> dict:
                return {"sent_to": to}

        assert has_task_metadata(MyService.send_email)
        metadata = get_task_metadata(MyService.send_email)
        assert metadata is not None
        assert metadata.queue == "emails"

    def test_multiple_task_methods(self):
        """여러 태스크 메서드"""

        class NotificationService:
            @Task(queue="emails", retry=3)
            async def send_email(self, to: str) -> None:
                pass

            @Task(queue="sms")
            async def send_sms(self, to: str) -> None:
                pass

            async def regular_method(self) -> None:
                pass

        # get_task_methods로 찾기
        methods = get_task_methods(NotificationService)
        assert len(methods) == 2

        names = [m[0] for m in methods]
        assert "send_email" in names
        assert "send_sms" in names
        assert "regular_method" not in names


class TestGetTaskMethods:
    """get_task_methods 테스트"""

    def test_find_task_methods_in_class(self):
        """클래스에서 태스크 메서드 찾기"""

        class TaskClass:
            @Task()
            async def task1(self):
                pass

            @Task(retry=3)
            async def task2(self):
                pass

            def not_a_task(self):
                pass

        methods = get_task_methods(TaskClass)
        assert len(methods) == 2

        for name, method, metadata in methods:
            assert name in ("task1", "task2")
            assert metadata is not None

    def test_empty_class(self):
        """태스크가 없는 클래스"""

        class NoTasks:
            def method(self):
                pass

        methods = get_task_methods(NoTasks)
        assert len(methods) == 0


class TestScanTaskMethods:
    """scan_task_methods 테스트"""

    def test_scan_instance_methods(self):
        """인스턴스에서 태스크 메서드 스캔"""

        class Service:
            @Task(queue="default")
            async def do_work(self):
                return "done"

        instance = Service()
        methods = scan_task_methods(instance)

        assert len(methods) == 1
        name, method, metadata = methods[0]
        assert name == "do_work"
        assert callable(method)

    async def test_scanned_method_is_bound(self):
        """스캔된 메서드가 바인딩됨"""

        class Counter:
            def __init__(self):
                self.count = 0

            @Task()
            async def increment(self):
                self.count += 1
                return self.count

        instance = Counter()
        methods = scan_task_methods(instance)

        name, method, metadata = methods[0]
        # bound method이므로 self 없이 호출 가능
        result = await method()
        assert result == 1
        assert instance.count == 1


class TestMetadataHelpers:
    """메타데이터 헬퍼 함수 테스트"""

    def test_has_task_metadata(self):
        """has_task_metadata"""

        @Task()
        async def with_metadata():
            pass

        async def without_metadata():
            pass

        assert has_task_metadata(with_metadata) is True
        assert has_task_metadata(without_metadata) is False

    def test_get_task_metadata(self):
        """get_task_metadata"""

        @Task(retry=5)
        async def my_task():
            pass

        metadata = get_task_metadata(my_task)
        assert metadata is not None
        assert metadata.retry == 5

    def test_get_task_metadata_none(self):
        """메타데이터 없는 함수"""

        async def regular_func():
            pass

        assert get_task_metadata(regular_func) is None

    def test_get_metadata_from_bound_method(self):
        """바운드 메서드에서 메타데이터 가져오기"""

        class Service:
            @Task(queue="special")
            async def task_method(self):
                pass

        instance = Service()
        # 인스턴스의 메서드 (bound method)
        metadata = get_task_metadata(instance.task_method)
        assert metadata is not None
        assert metadata.queue == "special"
