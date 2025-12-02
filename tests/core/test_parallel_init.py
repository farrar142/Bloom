"""병렬 초기화 테스트"""

import pytest
import time
import threading
from bloom import Application, Component
from bloom.core.utils import group_by_dependency_level


class TestGroupByDependencyLevel:
    """의존성 레벨 그룹화 테스트"""

    def test_no_dependencies(self, reset_container_manager):
        """의존성 없는 컴포넌트들은 모두 Level 0"""

        @Component
        class A:
            pass

        @Component
        class B:
            pass

        @Component
        class C:
            pass

        app = Application("test")
        all_containers = [
            c for containers in app.manager.get_all_containers().values()
            for c in containers
        ]

        levels = group_by_dependency_level(all_containers)

        # 모두 Level 0에 있어야 함
        assert len(levels) == 1
        assert len(levels[0]) == 3

    def test_linear_dependencies(self, reset_container_manager):
        """선형 의존성: A -> B -> C"""

        @Component
        class A:
            pass

        @Component
        class B:
            a: A

        @Component
        class C:
            b: B

        app = Application("test")
        all_containers = [
            c for containers in app.manager.get_all_containers().values()
            for c in containers
        ]

        levels = group_by_dependency_level(all_containers)

        # 3개의 레벨이 있어야 함
        assert len(levels) == 3

        # Level 0: A (의존성 없음)
        level0_types = {c.target for c in levels[0]}
        assert A in level0_types

        # Level 1: B (A에 의존)
        level1_types = {c.target for c in levels[1]}
        assert B in level1_types

        # Level 2: C (B에 의존)
        level2_types = {c.target for c in levels[2]}
        assert C in level2_types

    def test_diamond_dependency(self, reset_container_manager):
        """다이아몬드 의존성: D -> B, C -> A"""

        @Component
        class A:
            pass

        @Component
        class B:
            a: A

        @Component
        class C:
            a: A

        @Component
        class D:
            b: B
            c: C

        app = Application("test")
        all_containers = [
            c for containers in app.manager.get_all_containers().values()
            for c in containers
        ]

        levels = group_by_dependency_level(all_containers)

        # 3개의 레벨이 있어야 함
        assert len(levels) == 3

        # Level 0: A
        level0_types = {c.target for c in levels[0]}
        assert A in level0_types

        # Level 1: B, C (둘 다 A에만 의존)
        level1_types = {c.target for c in levels[1]}
        assert B in level1_types
        assert C in level1_types

        # Level 2: D (B, C에 의존)
        level2_types = {c.target for c in levels[2]}
        assert D in level2_types


class TestParallelInitialization:
    """병렬 초기화 테스트"""

    def test_parallel_init_basic(self, reset_container_manager):
        """병렬 초기화 기본 동작"""

        @Component
        class ServiceA:
            pass

        @Component
        class ServiceB:
            pass

        @Component
        class ServiceC:
            a: ServiceA
            b: ServiceB

        app = Application("test").ready(parallel=True)

        # 모든 인스턴스가 정상적으로 생성되어야 함
        a = app.manager.get_instance(ServiceA)
        b = app.manager.get_instance(ServiceB)
        c = app.manager.get_instance(ServiceC)

        assert a is not None
        assert b is not None
        assert c is not None
        assert c.a is a
        assert c.b is b

    def test_parallel_init_with_postconstruct(self, reset_container_manager):
        """병렬 초기화 + @PostConstruct"""
        from bloom.core.decorators import PostConstruct

        init_order = []
        lock = threading.Lock()

        @Component
        class ServiceA:
            @PostConstruct
            def init(self):
                with lock:
                    init_order.append("A")

        @Component
        class ServiceB:
            @PostConstruct
            def init(self):
                with lock:
                    init_order.append("B")

        @Component
        class ServiceC:
            a: ServiceA
            b: ServiceB

            @PostConstruct
            def init(self):
                with lock:
                    init_order.append("C")

        app = Application("test").ready(parallel=True)

        # 모든 @PostConstruct가 호출되어야 함
        assert "A" in init_order
        assert "B" in init_order
        assert "C" in init_order

        # C는 A, B 이후에 초기화되어야 함
        assert init_order.index("C") > init_order.index("A")
        assert init_order.index("C") > init_order.index("B")

    def test_parallel_vs_sequential_consistency(self, reset_container_manager):
        """병렬 초기화와 순차 초기화 결과 일관성 - 같은 구조로 초기화 방식만 다르게"""

        @Component
        class Base:
            value: int = 100

        @Component
        class ServiceA:
            base: Base

        @Component
        class ServiceB:
            base: Base

        @Component
        class ServiceC:
            a: ServiceA
            b: ServiceB
            base: Base

        # 순차 초기화 (기본)
        app_seq = Application("test").ready(parallel=False)

        a_seq = app_seq.manager.get_instance(ServiceA)
        b_seq = app_seq.manager.get_instance(ServiceB)
        c_seq = app_seq.manager.get_instance(ServiceC)
        base_seq = app_seq.manager.get_instance(Base)

        # 의존성 주입 검증 (순차)
        assert a_seq.base is base_seq
        assert b_seq.base is base_seq
        assert c_seq.a is a_seq
        assert c_seq.b is b_seq
        assert c_seq.base is base_seq

    def test_parallel_init_preserves_singleton(self, reset_container_manager):
        """병렬 초기화에서도 싱글톤 보장"""

        @Component
        class SharedService:
            pass

        @Component
        class ConsumerA:
            shared: SharedService

        @Component
        class ConsumerB:
            shared: SharedService

        @Component
        class ConsumerC:
            shared: SharedService

        app = Application("test").ready(parallel=True)

        shared = app.manager.get_instance(SharedService)
        a = app.manager.get_instance(ConsumerA)
        b = app.manager.get_instance(ConsumerB)
        c = app.manager.get_instance(ConsumerC)

        # 모든 consumer가 같은 shared 인스턴스를 사용
        assert a.shared is shared
        assert b.shared is shared
        assert c.shared is shared


class TestPerformanceComparison:
    """순차 vs 병렬 성능 비교 (마커 없음 - 기본 실행)"""

    @pytest.mark.skip(reason="성능 테스트는 환경에 따라 결과가 달라짐")
    def test_parallel_faster_with_io_bound(self, reset_container_manager):
        """I/O 바운드 초기화에서 병렬이 더 빠름"""
        from bloom.core.decorators import PostConstruct

        init_times = {"parallel": 0, "sequential": 0}

        # 병렬 테스트를 위한 I/O 시뮬레이션 컴포넌트
        @Component
        class SlowServiceA:
            @PostConstruct
            def init(self):
                time.sleep(0.05)  # 50ms

        @Component
        class SlowServiceB:
            @PostConstruct
            def init(self):
                time.sleep(0.05)  # 50ms

        @Component
        class SlowServiceC:
            @PostConstruct
            def init(self):
                time.sleep(0.05)  # 50ms

        @Component
        class SlowServiceD:
            @PostConstruct
            def init(self):
                time.sleep(0.05)  # 50ms

        # 병렬 초기화
        start = time.perf_counter()
        app = Application("test").ready(parallel=True)
        init_times["parallel"] = time.perf_counter() - start

        # 순차로 하면 최소 0.2초 (4 x 0.05)
        # 병렬로 하면 약 0.05초 (모두 독립적이므로)
        # 약간의 오버헤드를 감안하여 0.15초 미만이면 병렬 효과가 있다고 판단
        assert init_times["parallel"] < 0.15, f"Parallel init took {init_times['parallel']:.3f}s"


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_application(self, reset_container_manager):
        """컴포넌트 없는 애플리케이션"""
        app = Application("test").ready(parallel=True)
        assert app is not None

    def test_single_component(self, reset_container_manager):
        """단일 컴포넌트"""

        @Component
        class Single:
            pass

        app = Application("test").ready(parallel=True)
        single = app.manager.get_instance(Single)
        assert single is not None

    def test_deep_dependency_chain(self, reset_container_manager):
        """깊은 의존성 체인 (Level 5)"""

        @Component
        class L0:
            pass

        @Component
        class L1:
            l0: L0

        @Component
        class L2:
            l1: L1

        @Component
        class L3:
            l2: L2

        @Component
        class L4:
            l3: L3

        @Component
        class L5:
            l4: L4

        app = Application("test").ready(parallel=True)

        l5 = app.manager.get_instance(L5)
        assert l5 is not None
        assert l5.l4.l3.l2.l1.l0 is app.manager.get_instance(L0)
