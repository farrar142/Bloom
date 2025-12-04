"""@PostConstruct, @PreDestroy, AutoCloseable 라이프사이클 테스트"""

import pytest

from bloom.core import (
    Component,
    PostConstruct,
    PreDestroy,
    AutoCloseable,
    ScopeEnum,
    Scope,
    Handler,
    get_container_manager,
)


class TestLifecycle:
    """@PostConstruct, @PreDestroy, AutoCloseable 테스트"""

    @pytest.mark.asyncio
    async def test_post_construct_called(self):
        """@PostConstruct가 초기화 시 호출되는지"""
        called = {"init": False}

        @Component
        class ServiceWithInit:
            @PostConstruct
            async def init(self):
                called["init"] = True

        manager = get_container_manager()
        await manager.initialize()

        assert called["init"] is True

    @pytest.mark.asyncio
    async def test_pre_destroy_called(self):
        """@PreDestroy가 종료 시 호출되는지"""
        called = {"destroy": False}

        @Component
        class ServiceWithDestroy:
            @PreDestroy
            async def cleanup(self):
                called["destroy"] = True

        manager = get_container_manager()
        await manager.initialize()
        await manager.shutdown()

        assert called["destroy"] is True

    @pytest.mark.asyncio
    async def test_auto_closable(self):
        """AutoCloseable.close()가 종료 시 호출되는지"""
        called = {"close": False}

        @Component
        class ResourceService(AutoCloseable):
            async def close(self):
                called["close"] = True

        manager = get_container_manager()
        await manager.initialize()
        await manager.shutdown()

        assert called["close"] is True


class TestCallScopeLifecycle:
    """CALL 스코프 라이프사이클 테스트"""

    @pytest.mark.asyncio
    async def test_call_scope_basic_lifecycle(self):
        """CALL 스코프 기본 라이프사이클 (동기 PostConstruct)"""
        events = []

        # 동기 factory, 동기 PostConstruct인 경우 LazyProxy로 접근 가능
        @Component
        @Scope(ScopeEnum.CALL)
        class CallScopedService:
            @PostConstruct
            def init(self):  # 동기 메서드
                events.append("init")

            @PreDestroy
            async def cleanup(self):
                events.append("destroy")

            def work(self):
                events.append("work")

        @Component
        class WorkerService:
            call_service: CallScopedService

            @Handler
            async def do_work(self):
                self.call_service.work()
                return "done"

        manager = get_container_manager()
        await manager.initialize()

        worker = manager.get_instance(WorkerService)
        result = await worker.do_work()

        assert result == "done"
        # Handler 내에서 생성되고, Handler 종료 시 정리됨
        assert "init" in events
        assert "work" in events
        assert "destroy" in events
        # 순서 확인: init -> work -> destroy
        assert events.index("init") < events.index("work")
        assert events.index("work") < events.index("destroy")

    @pytest.mark.asyncio
    async def test_call_scope_nested_handlers(self):
        """중첩 Handler에서 CALL 스코프 격리"""
        events = []
        instance_ids = []

        @Component
        @Scope(ScopeEnum.CALL)
        class NestedCallService:
            def __init__(self):
                self.id = id(self)
                instance_ids.append(self.id)
                events.append(f"create:{self.id}")

            @PreDestroy
            async def cleanup(self):
                events.append(f"destroy:{self.id}")

        @Component
        class OuterService:
            nested: NestedCallService

            @Handler
            async def outer_handler(self):
                events.append("outer:start")
                outer_id = self.nested.id

                # 내부 Handler 호출
                inner = get_container_manager().get_instance(InnerService)
                await inner.inner_handler()

                # outer의 인스턴스가 여전히 동일한지 확인
                assert self.nested.id == outer_id, "Outer instance should be same"
                events.append("outer:end")
                return outer_id

        @Component
        class InnerService:
            nested: NestedCallService

            @Handler
            async def inner_handler(self):
                events.append("inner:start")
                inner_id = self.nested.id
                events.append("inner:end")
                return inner_id

        manager = get_container_manager()
        await manager.initialize()

        outer = manager.get_instance(OuterService)
        outer_id = await outer.outer_handler()

        # 2개의 다른 인스턴스가 생성되어야 함 (outer용, inner용)
        assert len(instance_ids) == 2
        assert instance_ids[0] != instance_ids[1]

        # 두 인스턴스 모두 destroy 호출됨
        destroy_events = [e for e in events if e.startswith("destroy:")]
        assert len(destroy_events) == 2

    @pytest.mark.asyncio
    async def test_call_scope_inherit_parent(self):
        """inherit_parent 옵션으로 부모 컨텍스트 인스턴스 상속"""
        events = []
        instance_ids = []

        @Component
        @Scope(ScopeEnum.CALL)
        class SharedCallService:
            def __init__(self):
                self.id = id(self)
                instance_ids.append(self.id)
                events.append(f"create:{self.id}")

            @PreDestroy
            async def cleanup(self):
                events.append(f"destroy:{self.id}")

        manager = get_container_manager()
        scope_manager = manager.scope_manager

        # asynccontextmanager 사용
        async with scope_manager.call_scope() as parent_frame:
            # 부모에서 인스턴스 생성
            parent_instance = await manager.get_instance_async(SharedCallService)
            parent_id = parent_instance.id
            events.append("parent:got_instance")

            # 자식 컨텍스트 시작 (inherit_parent=True, destroy_instances=False)
            async with scope_manager.call_scope(
                inherit_parent=True, destroy_instances=False
            ):
                # 자식에서 같은 인스턴스를 받아야 함
                child_instance = await manager.get_instance_async(SharedCallService)
                child_id = child_instance.id
                events.append("child:got_instance")

                # 같은 인스턴스여야 함
                assert parent_id == child_id, "Should inherit parent's instance"

            # 자식 컨텍스트 종료 후, 아직 destroy 안 됨
            assert "destroy:" + str(parent_id) not in events

        # 부모 컨텍스트 종료 후, 이제 destroy 됨
        assert f"destroy:{parent_id}" in events

        # 인스턴스는 1개만 생성됨
        assert len(instance_ids) == 1

    @pytest.mark.asyncio
    async def test_call_scope_frame_stack_depth(self):
        """frame 스택 깊이 확인 (asynccontextmanager 사용)"""
        manager = get_container_manager()
        await manager.initialize()
        scope_manager = manager.scope_manager

        # 초기 상태
        assert scope_manager.get_frame_stack_depth() == 0
        assert not scope_manager.is_in_call_context()

        # asynccontextmanager로 중첩 테스트
        async with scope_manager.call_scope() as frame1:
            assert scope_manager.get_frame_stack_depth() == 1
            assert scope_manager.is_in_call_context()
            assert scope_manager.get_current_frame_id() == frame1

            async with scope_manager.call_scope() as frame2:
                assert scope_manager.get_frame_stack_depth() == 2
                assert scope_manager.get_current_frame_id() == frame2

                async with scope_manager.call_scope() as frame3:
                    assert scope_manager.get_frame_stack_depth() == 3
                    assert scope_manager.get_current_frame_id() == frame3

                # frame3 종료 후
                assert scope_manager.get_frame_stack_depth() == 2
                assert scope_manager.get_current_frame_id() == frame2

            # frame2 종료 후
            assert scope_manager.get_frame_stack_depth() == 1
            assert scope_manager.get_current_frame_id() == frame1

        # 모두 종료 후
        assert scope_manager.get_frame_stack_depth() == 0
        assert not scope_manager.is_in_call_context()

    @pytest.mark.asyncio
    async def test_call_scope_destroy_order(self):
        """CALL 스코프 인스턴스 역순 정리"""
        destroy_order = []

        @Component
        @Scope(ScopeEnum.CALL)
        class FirstService:
            @PreDestroy
            async def cleanup(self):
                destroy_order.append("first")

        @Component
        @Scope(ScopeEnum.CALL)
        class SecondService:
            first: FirstService  # FirstService에 의존

            @PreDestroy
            async def cleanup(self):
                destroy_order.append("second")

        @Component
        @Scope(ScopeEnum.CALL)
        class ThirdService:
            second: SecondService  # SecondService에 의존

            @PreDestroy
            async def cleanup(self):
                destroy_order.append("third")

        @Component
        class OrchestratorService:
            third: ThirdService

            @Handler
            async def orchestrate(self):
                # ThirdService 접근 -> SecondService 생성 -> FirstService 생성
                _ = self.third.second.first
                return "done"

        manager = get_container_manager()
        await manager.initialize()

        orchestrator = manager.get_instance(OrchestratorService)
        await orchestrator.orchestrate()

        # 역순으로 정리되어야 함: third -> second -> first
        assert destroy_order == ["third", "second", "first"]
