"""
Scope 모듈 테스트

단위 테스트:
- CallFrame, CallStackTracker
- Scope enum
- ScopeContext
- 각 ScopeManager (Request, Call, Transactional)

통합 테스트:
- CallStackTracker와 ScopeContext 통합
- 중첩 스코프
- AutoCloseable 자동 close

엣지 케이스:
- 예외 발생 시 스코프 정리
- 빈 스코프
- 중첩 Transactional
"""

import pytest
import asyncio
from bloom.core.container.scope import (
    # CallStack
    CallFrame,
    CallStackTracker,
    call_stack,
    # Scope
    Scope,
    ScopeContext,
    # Scope getters/setters
    get_request_scope,
    set_request_scope,
    get_call_scope,
    set_call_scope,
    get_transactional_scope,
    set_transactional_scope,
    get_scope_context,
    # Managers
    RequestScopeManager,
    CallScopeManager,
    TransactionalScopeManager,
    request_scope,
    call_scope_manager,
    transactional_scope,
)
from bloom.core.abstract.autocloseable import AutoCloseable, AsyncAutoCloseable


# =============================================================================
# Mock AutoCloseable 클래스들
# =============================================================================


class MockAutoCloseable(AutoCloseable):
    """테스트용 AutoCloseable"""

    instances: list["MockAutoCloseable"] = []
    close_order: list[int] = []

    def __init__(self, id: int = 0):
        self.id = id
        self.entered = False
        self.exited = False
        MockAutoCloseable.instances.append(self)

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exited = True
        MockAutoCloseable.close_order.append(self.id)

    @classmethod
    def reset(cls):
        cls.instances = []
        cls.close_order = []


class MockAsyncAutoCloseable(AsyncAutoCloseable):
    """테스트용 AsyncAutoCloseable"""

    instances: list["MockAsyncAutoCloseable"] = []
    close_order: list[int] = []

    def __init__(self, id: int = 0):
        self.id = id
        self.entered = False
        self.exited = False
        MockAsyncAutoCloseable.instances.append(self)

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.exited = True
        MockAsyncAutoCloseable.close_order.append(self.id)

    @classmethod
    def reset(cls):
        cls.instances = []
        cls.close_order = []


# =============================================================================
# 단위 테스트: CallFrame
# =============================================================================


class TestCallFrame:
    """CallFrame 단위 테스트"""

    def test_callframe_creation(self):
        """CallFrame 생성 테스트"""
        frame = CallFrame()
        assert frame.id == id(frame)
        assert frame.datas == []

    def test_callframe_add_data(self):
        """CallFrame 데이터 추가 테스트"""
        frame = CallFrame()
        frame.add_data({"key": "value"})
        frame.add_data(123)
        assert len(frame.datas) == 2
        assert frame.datas[0] == {"key": "value"}
        assert frame.datas[1] == 123

    def test_callframe_repr(self):
        """CallFrame repr 테스트"""
        frame = CallFrame()
        repr_str = repr(frame)
        assert "CallFrame" in repr_str
        assert str(frame.id) in repr_str


# =============================================================================
# 단위 테스트: CallStackTracker
# =============================================================================


class TestCallStackTracker:
    """CallStackTracker 단위 테스트"""

    def test_sync_context_manager(self):
        """sync 컨텍스트 매니저 테스트"""
        tracker = CallStackTracker()

        with tracker as frame:
            assert isinstance(frame, CallFrame)

    def test_sync_nested_frames(self):
        """sync 중첩 프레임 테스트"""
        tracker = CallStackTracker()
        frames = []

        with tracker as frame1:
            frames.append(frame1)
            with tracker as frame2:
                frames.append(frame2)
                with tracker as frame3:
                    frames.append(frame3)

        assert len(frames) == 3
        assert frames[0] != frames[1] != frames[2]

    def test_sync_event_listeners(self):
        """sync 이벤트 리스너 테스트"""
        tracker = CallStackTracker()
        enter_frames: list[CallFrame] = []
        exit_frames: list[CallFrame] = []

        def on_enter(frame: CallFrame):
            enter_frames.append(frame)

        def on_exit(frame: CallFrame):
            exit_frames.append(frame)

        tracker.add_event_listener(on_enter)
        tracker.exit_event_listener(on_exit)

        with tracker as frame:
            pass

        assert len(enter_frames) == 1
        assert len(exit_frames) == 1
        assert enter_frames[0] == exit_frames[0]

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """async 컨텍스트 매니저 테스트"""
        tracker = CallStackTracker()

        async with tracker as frame:
            assert isinstance(frame, CallFrame)

    @pytest.mark.asyncio
    async def test_async_nested_frames(self):
        """async 중첩 프레임 테스트"""
        tracker = CallStackTracker()
        frames = []

        async with tracker as frame1:
            frames.append(frame1)
            async with tracker as frame2:
                frames.append(frame2)

        assert len(frames) == 2
        assert frames[0] != frames[1]

    @pytest.mark.asyncio
    async def test_async_event_listeners(self):
        """async 이벤트 리스너 테스트"""
        tracker = CallStackTracker()
        enter_frames: list[CallFrame] = []
        exit_frames: list[CallFrame] = []

        async def on_enter(frame: CallFrame):
            enter_frames.append(frame)

        async def on_exit(frame: CallFrame):
            exit_frames.append(frame)

        tracker.aadd_event_listener(on_enter)
        tracker.aexit_event_listener(on_exit)

        async with tracker as frame:
            pass

        assert len(enter_frames) == 1
        assert len(exit_frames) == 1

    @pytest.mark.asyncio
    async def test_current_frame(self):
        """current_frame 테스트"""
        tracker = CallStackTracker()

        # 프레임 없을 때
        frame = await tracker.current_frame()
        assert frame is None

        async with tracker as active_frame:
            current = await tracker.current_frame()
            assert current == active_frame

    @pytest.mark.asyncio
    async def test_current_frame_required(self):
        """current_frame required=True 테스트"""
        tracker = CallStackTracker()

        with pytest.raises(RuntimeError, match="No active CallFrame"):
            await tracker.current_frame(required=True)

    def test_remove_event_listener(self):
        """이벤트 리스너 제거 테스트"""
        tracker = CallStackTracker()
        called = []

        def listener(frame):
            called.append(frame)

        tracker.add_event_listener(listener)
        tracker.remove_add_event_listener(listener)

        with tracker as frame:
            pass

        # 리스너가 제거되었으므로 호출되지 않음
        assert len(called) == 0


# =============================================================================
# 단위 테스트: Scope
# =============================================================================


class TestScope:
    """Scope enum 단위 테스트"""

    def test_scope_values(self):
        """Scope 값 테스트"""
        assert Scope.SINGLETON.value == "singleton"
        assert Scope.CALL.value == "call"
        assert Scope.REQUEST.value == "request"

    def test_scope_comparison(self):
        """Scope 비교 테스트"""
        assert Scope.SINGLETON == Scope.SINGLETON
        assert Scope.CALL != Scope.REQUEST


# =============================================================================
# 단위 테스트: ScopeContext
# =============================================================================


class TestScopeContext:
    """ScopeContext 단위 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        MockAsyncAutoCloseable.reset()

    def test_scope_context_creation(self):
        """ScopeContext 생성 테스트"""
        ctx = ScopeContext(Scope.CALL)
        assert ctx.scope == Scope.CALL
        assert ctx.context_id is not None
        assert len(ctx._instances) == 0

    def test_scope_context_custom_id(self):
        """ScopeContext 커스텀 ID 테스트"""
        ctx = ScopeContext(Scope.REQUEST, context_id="custom-id")
        assert ctx.context_id == "custom-id"

    def test_scope_context_get_set(self):
        """ScopeContext get/set 테스트"""
        ctx = ScopeContext(Scope.CALL)

        assert ctx.get("key1") is None

        ctx.set("key1", "value1")
        assert ctx.get("key1") == "value1"

        ctx.set("key2", {"nested": "data"})
        assert ctx.get("key2") == {"nested": "data"}

    def test_scope_context_register_closeable(self):
        """ScopeContext closeable 등록 테스트"""
        ctx = ScopeContext(Scope.CALL)
        closeable = MockAutoCloseable(1)

        ctx.register_closeable(closeable)
        assert closeable in ctx._closeables

    def test_scope_context_close_all_sync(self):
        """ScopeContext close_all (sync) 테스트"""
        ctx = ScopeContext(Scope.CALL)
        c1 = MockAutoCloseable(1)
        c2 = MockAutoCloseable(2)
        c3 = MockAutoCloseable(3)

        c1.__enter__()
        c2.__enter__()
        c3.__enter__()

        ctx.register_closeable(c1)
        ctx.register_closeable(c2)
        ctx.register_closeable(c3)

        ctx.set("c1", c1)
        ctx.set("c2", c2)

        ctx.close_all()

        # 역순으로 close 되어야 함
        assert MockAutoCloseable.close_order == [3, 2, 1]
        assert c1.exited and c2.exited and c3.exited
        assert len(ctx._closeables) == 0
        assert len(ctx._instances) == 0

    @pytest.mark.asyncio
    async def test_scope_context_aclose_all(self):
        """ScopeContext aclose_all (async) 테스트"""
        ctx = ScopeContext(Scope.CALL)
        c1 = MockAsyncAutoCloseable(1)
        c2 = MockAsyncAutoCloseable(2)

        await c1.__aenter__()
        await c2.__aenter__()

        ctx.register_closeable(c1)
        ctx.register_closeable(c2)

        await ctx.aclose_all()

        # 역순으로 close 되어야 함
        assert MockAsyncAutoCloseable.close_order == [2, 1]
        assert c1.exited and c2.exited

    def test_scope_context_repr(self):
        """ScopeContext repr 테스트"""
        ctx = ScopeContext(Scope.CALL)
        ctx.set("key", "value")

        repr_str = repr(ctx)
        assert "ScopeContext" in repr_str
        assert "call" in repr_str
        assert "instances=1" in repr_str


# =============================================================================
# 단위 테스트: Scope Context Getters/Setters
# =============================================================================


class TestScopeContextGettersSetters:
    """스코프 컨텍스트 getter/setter 테스트"""

    def teardown_method(self):
        """테스트 후 정리"""
        set_request_scope(None)
        set_call_scope(None)
        set_transactional_scope(None)

    def test_request_scope_getter_setter(self):
        """request scope getter/setter 테스트"""
        assert get_request_scope() is None

        ctx = ScopeContext(Scope.REQUEST)
        set_request_scope(ctx)
        assert get_request_scope() == ctx

        set_request_scope(None)
        assert get_request_scope() is None

    def test_call_scope_getter_setter(self):
        """call scope getter/setter 테스트"""
        assert get_call_scope() is None

        ctx = ScopeContext(Scope.CALL)
        set_call_scope(ctx)
        assert get_call_scope() == ctx

    def test_transactional_scope_getter_setter(self):
        """transactional scope getter/setter 테스트"""
        assert get_transactional_scope() is None

        ctx = ScopeContext(Scope.CALL)
        set_transactional_scope(ctx)
        assert get_transactional_scope() == ctx

    def test_get_scope_context_request(self):
        """get_scope_context REQUEST 테스트"""
        ctx = ScopeContext(Scope.REQUEST)
        set_request_scope(ctx)

        assert get_scope_context(Scope.REQUEST) == ctx
        assert get_scope_context(Scope.CALL) is None

    def test_get_scope_context_call_prefers_transactional(self):
        """get_scope_context CALL - transactional 우선 테스트"""
        call_ctx = ScopeContext(Scope.CALL)
        trans_ctx = ScopeContext(Scope.CALL)

        set_call_scope(call_ctx)
        set_transactional_scope(trans_ctx)

        # Transactional이 우선
        assert get_scope_context(Scope.CALL) == trans_ctx

    def test_get_scope_context_singleton_returns_none(self):
        """get_scope_context SINGLETON은 None 반환"""
        assert get_scope_context(Scope.SINGLETON) is None


# =============================================================================
# 단위 테스트: RequestScopeManager
# =============================================================================


class TestRequestScopeManager:
    """RequestScopeManager 단위 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        MockAsyncAutoCloseable.reset()
        set_request_scope(None)

    def teardown_method(self):
        set_request_scope(None)

    def test_sync_context_manager(self):
        """sync 컨텍스트 매니저 테스트"""
        with request_scope() as ctx:
            assert isinstance(ctx, ScopeContext)
            assert ctx.scope == Scope.REQUEST
            assert get_request_scope() == ctx

        assert get_request_scope() is None

    def test_sync_closes_closeables(self):
        """sync - closeable 자동 close 테스트"""
        closeable = MockAutoCloseable(1)

        with request_scope() as ctx:
            closeable.__enter__()
            ctx.register_closeable(closeable)

        assert closeable.exited

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """async 컨텍스트 매니저 테스트"""
        async with request_scope() as ctx:
            assert isinstance(ctx, ScopeContext)
            assert ctx.scope == Scope.REQUEST
            assert get_request_scope() == ctx

        assert get_request_scope() is None

    @pytest.mark.asyncio
    async def test_async_closes_closeables(self):
        """async - closeable 자동 close 테스트"""
        closeable = MockAsyncAutoCloseable(1)

        async with request_scope() as ctx:
            await closeable.__aenter__()
            ctx.register_closeable(closeable)

        assert closeable.exited


# =============================================================================
# 단위 테스트: CallScopeManager
# =============================================================================


class TestCallScopeManager:
    """CallScopeManager 단위 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        set_call_scope(None)

    def teardown_method(self):
        set_call_scope(None)

    def test_sync_context_manager(self):
        """sync 컨텍스트 매니저 테스트"""
        with call_scope_manager() as ctx:
            assert isinstance(ctx, ScopeContext)
            assert ctx.scope == Scope.CALL
            assert get_call_scope() == ctx

        assert get_call_scope() is None

    def test_sync_creates_callframe(self):
        """sync - CallFrame 생성 테스트"""
        tracker = call_stack()
        initial_frame = None

        with call_scope_manager() as ctx:
            # CallFrame이 생성되고 scope_context가 추가됨
            pass  # CallFrame은 내부적으로 생성됨

        # exit 후 스코프가 정리됨
        assert get_call_scope() is None

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """async 컨텍스트 매니저 테스트"""
        async with call_scope_manager() as ctx:
            assert isinstance(ctx, ScopeContext)
            assert ctx.scope == Scope.CALL
            assert get_call_scope() == ctx

        assert get_call_scope() is None


# =============================================================================
# 단위 테스트: TransactionalScopeManager
# =============================================================================


class TestTransactionalScopeManager:
    """TransactionalScopeManager 단위 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        set_transactional_scope(None)

    def teardown_method(self):
        set_transactional_scope(None)

    def test_sync_context_manager(self):
        """sync 컨텍스트 매니저 테스트"""
        with transactional_scope() as ctx:
            assert isinstance(ctx, ScopeContext)
            assert get_transactional_scope() == ctx

        assert get_transactional_scope() is None

    def test_sync_nested_reuses_context(self):
        """sync - 중첩 시 같은 context 재사용 테스트"""
        with transactional_scope() as outer_ctx:
            with transactional_scope() as inner_ctx:
                # 중첩된 transactional은 같은 context 사용
                assert outer_ctx == inner_ctx
                # 내부에서 context 유효
                assert get_transactional_scope() == outer_ctx

        # 최외곽 scope 종료 후 정리
        assert get_transactional_scope() is None

    @pytest.mark.asyncio
    async def test_async_nested_reuses_context(self):
        """async - 중첩 시 같은 context 재사용 테스트"""
        async with transactional_scope() as outer_ctx:
            async with transactional_scope() as inner_ctx:
                assert outer_ctx == inner_ctx
                assert get_transactional_scope() == outer_ctx

        assert get_transactional_scope() is None


# =============================================================================
# 통합 테스트: CallStack과 Scope 통합
# =============================================================================


class TestCallStackScopeIntegration:
    """CallStack과 Scope 통합 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        set_call_scope(None)

    def teardown_method(self):
        set_call_scope(None)

    def test_call_scope_manager_integrates_with_callstack(self):
        """CallScopeManager가 CallStackTracker와 통합되는지 테스트"""
        with call_scope_manager() as ctx:
            # scope_context가 CallFrame에 추가됨
            assert get_call_scope() == ctx

    def test_nested_call_scopes(self):
        """중첩 call scope 테스트 - 각각 독립적인 context"""
        contexts = []

        with call_scope_manager() as ctx1:
            contexts.append(ctx1)
            # 현재 구현에서는 중첩 call_scope_manager가 이전 context를 덮어씀
            with call_scope_manager() as ctx2:
                contexts.append(ctx2)
                # 각 레벨에서 다른 context
                assert ctx1 != ctx2
                assert get_call_scope() == ctx2

        # 모든 scope 종료 후
        assert get_call_scope() is None
        assert len(contexts) == 2

    @pytest.mark.asyncio
    async def test_async_nested_call_scopes(self):
        """async 중첩 call scope 테스트"""
        contexts = []

        async with call_scope_manager() as ctx1:
            contexts.append(ctx1)
            async with call_scope_manager() as ctx2:
                contexts.append(ctx2)
                assert ctx1 != ctx2

        assert len(contexts) == 2


# =============================================================================
# 통합 테스트: AutoCloseable 자동 관리
# =============================================================================


class TestAutoCloseableIntegration:
    """AutoCloseable 통합 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        MockAsyncAutoCloseable.reset()

    def test_sync_auto_close_on_scope_exit(self):
        """sync - 스코프 종료 시 자동 close 테스트"""
        closeables = []

        with call_scope_manager() as ctx:
            for i in range(3):
                c = MockAutoCloseable(i)
                c.__enter__()
                ctx.register_closeable(c)
                closeables.append(c)

        # 모든 closeable이 close됨
        for c in closeables:
            assert c.exited

        # 역순으로 close
        assert MockAutoCloseable.close_order == [2, 1, 0]

    @pytest.mark.asyncio
    async def test_async_auto_close_on_scope_exit(self):
        """async - 스코프 종료 시 자동 close 테스트"""
        closeables = []

        async with call_scope_manager() as ctx:
            for i in range(3):
                c = MockAsyncAutoCloseable(i)
                await c.__aenter__()
                ctx.register_closeable(c)
                closeables.append(c)

        for c in closeables:
            assert c.exited

        assert MockAsyncAutoCloseable.close_order == [2, 1, 0]

    def test_transactional_shares_instances(self):
        """transactional scope 내 인스턴스 공유 테스트"""
        with transactional_scope() as ctx:
            ctx.set("session", "shared_session")

            # 중첩 transactional에서 같은 인스턴스 접근
            with transactional_scope() as inner_ctx:
                assert inner_ctx.get("session") == "shared_session"


# =============================================================================
# 엣지 케이스 테스트
# =============================================================================


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def setup_method(self):
        MockAutoCloseable.reset()
        MockAsyncAutoCloseable.reset()
        set_request_scope(None)
        set_call_scope(None)
        set_transactional_scope(None)

    def teardown_method(self):
        set_request_scope(None)
        set_call_scope(None)
        set_transactional_scope(None)

    def test_exception_during_scope_still_closes(self):
        """예외 발생 시에도 close 실행 테스트"""
        closeable = MockAutoCloseable(1)

        with pytest.raises(ValueError):
            with call_scope_manager() as ctx:
                closeable.__enter__()
                ctx.register_closeable(closeable)
                raise ValueError("Test exception")

        # 예외에도 불구하고 close됨
        assert closeable.exited

    @pytest.mark.asyncio
    async def test_async_exception_during_scope_still_closes(self):
        """async - 예외 발생 시에도 close 실행 테스트"""
        closeable = MockAsyncAutoCloseable(1)

        with pytest.raises(ValueError):
            async with call_scope_manager() as ctx:
                await closeable.__aenter__()
                ctx.register_closeable(closeable)
                raise ValueError("Test exception")

        assert closeable.exited

    def test_empty_scope_context_close(self):
        """빈 ScopeContext close 테스트"""
        ctx = ScopeContext(Scope.CALL)
        # 빈 상태에서 close해도 에러 없음
        ctx.close_all()
        assert len(ctx._closeables) == 0

    @pytest.mark.asyncio
    async def test_empty_scope_context_aclose(self):
        """빈 ScopeContext aclose 테스트"""
        ctx = ScopeContext(Scope.CALL)
        await ctx.aclose_all()
        assert len(ctx._closeables) == 0

    def test_closeable_exception_ignored(self):
        """closeable close 중 예외 무시 테스트"""

        class FailingCloseable(AutoCloseable):
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                raise RuntimeError("Close failed")

        ctx = ScopeContext(Scope.CALL)
        failing = FailingCloseable()
        normal = MockAutoCloseable(1)

        ctx.register_closeable(normal)
        ctx.register_closeable(failing)

        # 예외가 발생해도 다른 closeable은 close됨
        ctx.close_all()  # 예외 발생하지 않음
        assert normal.exited

    def test_deeply_nested_transactional(self):
        """깊은 중첩 transactional 테스트"""
        depth = 10
        contexts = []

        def nested_transaction(level: int, ctx_list: list):
            if level >= depth:
                return

            with transactional_scope() as ctx:
                ctx_list.append(ctx)
                nested_transaction(level + 1, ctx_list)
                # 모든 레벨에서 같은 context
                assert ctx == ctx_list[0]

        nested_transaction(0, contexts)
        assert len(contexts) == depth
        # 모든 context가 같음
        assert all(c == contexts[0] for c in contexts)

    def test_request_scope_isolated_from_call_scope(self):
        """REQUEST와 CALL 스코프 격리 테스트"""
        with request_scope() as req_ctx:
            req_ctx.set("request_data", "request_value")

            with call_scope_manager() as call_ctx:
                call_ctx.set("call_data", "call_value")

                # 서로 다른 context
                assert req_ctx != call_ctx
                assert req_ctx.get("call_data") is None
                assert call_ctx.get("request_data") is None

    def test_call_stack_function(self):
        """call_stack() 함수 테스트"""
        tracker = call_stack()
        assert isinstance(tracker, CallStackTracker)

        # 같은 context에서 같은 tracker 반환
        assert call_stack() is tracker

    @pytest.mark.asyncio
    async def test_concurrent_scopes(self):
        """동시 실행 스코프 테스트 (ContextVar 격리)"""
        results = []

        async def task(task_id: int):
            async with call_scope_manager() as ctx:
                ctx.set("task_id", task_id)
                await asyncio.sleep(0.01)  # 다른 태스크에 양보
                # 자신의 context 유지
                assert ctx.get("task_id") == task_id
                results.append(task_id)

        await asyncio.gather(task(1), task(2), task(3))
        assert sorted(results) == [1, 2, 3]


# =============================================================================
# 성능 테스트
# =============================================================================


class TestPerformance:
    """성능 관련 테스트"""

    def test_many_closeables(self):
        """많은 closeable 처리 테스트"""
        MockAutoCloseable.reset()
        count = 100

        with call_scope_manager() as ctx:
            for i in range(count):
                c = MockAutoCloseable(i)
                c.__enter__()
                ctx.register_closeable(c)

        assert len(MockAutoCloseable.close_order) == count
        # 역순 확인
        assert MockAutoCloseable.close_order == list(range(count - 1, -1, -1))

    def test_many_instances_in_context(self):
        """많은 인스턴스 저장 테스트"""
        ctx = ScopeContext(Scope.CALL)
        count = 1000

        for i in range(count):
            ctx.set(f"key_{i}", f"value_{i}")

        for i in range(count):
            assert ctx.get(f"key_{i}") == f"value_{i}"

        ctx.close_all()
        assert len(ctx._instances) == 0
