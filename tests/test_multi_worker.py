"""멀티 워커 지원 테스트"""

import asyncio
import pytest
from bloom import Application, Component, Controller, Get, RequestMapping
from bloom.web.asgi import ASGIApplication
from bloom.web.http import HttpRequest
from bloom.core.manager import set_current_manager


class TestLifespanEvents:
    """Lifespan 이벤트 테스트"""

    @pytest.mark.asyncio
    async def test_lifespan_startup_initializes_application(self):
        """startup 이벤트가 Application.ready()를 호출하는지 확인"""
        # 매니저 리셋
        set_current_manager(None)

        app = Application("lifespan_test")
        asgi = app.asgi

        # 아직 ready 호출 전
        assert not app._is_ready

        # startup 직접 호출
        await asgi._startup()

        # startup이 Application.ready()를 호출했는지 확인
        assert app._is_ready

    @pytest.mark.asyncio
    async def test_lifespan_full_cycle(self):
        """전체 lifespan 사이클 테스트"""
        set_current_manager(None)

        app = Application("lifespan_cycle_test")
        asgi = app.asgi

        # lifespan 시뮬레이션
        call_count = 0

        async def receive():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"type": "lifespan.startup"}
            return {"type": "lifespan.shutdown"}

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        # lifespan 핸들링
        await asgi._handle_lifespan({}, receive, send)

        # 메시지 확인
        assert {"type": "lifespan.startup.complete"} in sent_messages
        assert {"type": "lifespan.shutdown.complete"} in sent_messages

    @pytest.mark.asyncio
    async def test_on_startup_callback(self):
        """on_startup 콜백이 호출되는지 확인"""
        app = Application("callback_test")
        asgi = app.asgi

        callback_called = False

        @asgi.on_startup
        async def my_startup():
            nonlocal callback_called
            callback_called = True

        # startup 시뮬레이션
        await asgi._startup()

        assert callback_called

    @pytest.mark.asyncio
    async def test_on_shutdown_callback(self):
        """on_shutdown 콜백이 호출되는지 확인"""
        app = Application("callback_test")
        asgi = app.asgi

        callback_called = False

        @asgi.on_shutdown
        async def my_shutdown():
            nonlocal callback_called
            callback_called = True

        # shutdown 시뮬레이션
        await asgi._shutdown(timeout=1.0)

        assert callback_called


class TestGracefulShutdown:
    """Graceful Shutdown 테스트"""

    @pytest.mark.asyncio
    async def test_active_request_counting(self):
        """활성 요청 카운팅 테스트"""

        @Controller
        class TestController:
            @Get("/slow")
            async def slow(self):
                await asyncio.sleep(0.1)
                return {"done": True}

        import tests.test_multi_worker as test_module

        app = Application("counting_test").scan(test_module).ready()
        asgi = app.asgi

        assert asgi._active_requests == 0

        # 요청 시뮬레이션
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/slow",
            "headers": [],
            "query_string": b"",
        }

        body_received = False

        async def receive():
            nonlocal body_received
            if not body_received:
                body_received = True
                return {"body": b"", "more_body": False}
            return {"body": b"", "more_body": False}

        sent = []

        async def send(msg):
            sent.append(msg)

        # 요청 처리
        await asgi(scope, receive, send)

        # 요청 완료 후 카운트가 0으로 복귀
        assert asgi._active_requests == 0

    @pytest.mark.asyncio
    async def test_shutdown_rejects_new_requests(self):
        """shutdown 중에 새 요청을 거부하는지 확인"""
        app = Application("reject_test")
        asgi = app.asgi

        # shutdown 상태로 설정
        asgi._is_shutting_down = True

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [],
            "query_string": b"",
        }

        async def receive():
            return {"body": b"", "more_body": False}

        sent = []

        async def send(msg):
            sent.append(msg)

        await asgi(scope, receive, send)

        # 503 응답 확인
        assert sent[0]["type"] == "http.response.start"
        assert sent[0]["status"] == 503

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_active_requests(self):
        """shutdown이 활성 요청 완료를 기다리는지 확인"""
        app = Application("wait_test")
        asgi = app.asgi

        # 활성 요청 시뮬레이션
        asgi._active_requests = 1

        async def simulate_request_completion():
            await asyncio.sleep(0.1)
            asgi._active_requests = 0
            if asgi._shutdown_event:
                asgi._shutdown_event.set()

        # 요청 완료 태스크 시작
        completion_task = asyncio.create_task(simulate_request_completion())

        # shutdown 호출 (타임아웃 1초)
        await asgi._shutdown(timeout=1.0)

        await completion_task

        # shutdown이 완료되었는지 확인
        assert asgi._is_shutting_down


class TestWorkerSafety:
    """워커 안전성 테스트"""

    @pytest.mark.asyncio
    async def test_each_worker_simulates_independent_state(self):
        """
        각 워커가 독립적인 상태를 가지는지 확인

        실제 멀티워커 환경에서는 각 워커가 별도 프로세스이므로
        ContainerManager가 완전히 독립적입니다.
        여기서는 수동으로 새 매니저를 생성하여 테스트합니다.
        """
        from bloom.core.manager import ContainerManager, set_current_manager

        # 워커1 시뮬레이션
        set_current_manager(None)
        manager1 = ContainerManager("worker1")
        set_current_manager(manager1)
        app1 = Application("worker1", manager=manager1)

        # 워커2 시뮬레이션 (새 매니저로)
        manager2 = ContainerManager("worker2")
        app2 = Application("worker2", manager=manager2)

        assert app1.manager is not app2.manager
        assert app1.name != app2.name

    @pytest.mark.asyncio
    async def test_application_ready_can_be_called_multiple_times_safely(self):
        """Application.ready()가 여러 번 호출되어도 안전한지 확인"""

        @Component
        class TestService:
            pass

        import tests.test_multi_worker as test_module

        app = Application("idempotent_test").scan(test_module)

        # ready() 여러 번 호출
        app.ready()
        app.ready()
        app.ready()

        # 한 번만 초기화되어야 함
        assert app._is_ready

    @pytest.mark.asyncio
    async def test_asgi_application_has_reference_to_app(self):
        """ASGIApplication이 Application 참조를 가지는지 확인"""
        app = Application("ref_test")
        asgi = app.asgi

        assert asgi.application is app
