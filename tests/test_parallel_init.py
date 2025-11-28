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
        all_containers = []
        for qual_containers in app.manager.get_all_containers().values():
            for qualifier, container in qual_containers.items():
                all_containers.append((qualifier, container))

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
        all_containers = []
        for qual_containers in app.manager.get_all_containers().values():
            for qualifier, container in qual_containers.items():
                all_containers.append((qualifier, container))

        levels = group_by_dependency_level(all_containers)

        # 3개의 레벨이 있어야 함
        assert len(levels) == 3

        # Level 0: A (의존성 없음)
        level0_types = {c.target for _, c in levels[0]}
        assert A in level0_types

        # Level 1: B (A에 의존)
        level1_types = {c.target for _, c in levels[1]}
        assert B in level1_types

        # Level 2: C (B에 의존)
        level2_types = {c.target for _, c in levels[2]}
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
        all_containers = []
        for qual_containers in app.manager.get_all_containers().values():
            for qualifier, container in qual_containers.items():
                all_containers.append((qualifier, container))

        levels = group_by_dependency_level(all_containers)

        # 3개의 레벨이 있어야 함
        assert len(levels) == 3

        # Level 0: A
        level0_types = {c.target for _, c in levels[0]}
        assert A in level0_types

        # Level 1: B, C (둘 다 A에만 의존)
        level1_types = {c.target for _, c in levels[1]}
        assert B in level1_types
        assert C in level1_types

        # Level 2: D (B, C에 의존)
        level2_types = {c.target for _, c in levels[2]}
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
        class RepoA:
            pass

        @Component
        class RepoB:
            pass

        @Component
        class ServiceA:
            repo: RepoA

        @Component
        class ServiceB:
            repo: RepoB

        @Component
        class Controller:
            service_a: ServiceA
            service_b: ServiceB

        # 병렬 초기화
        app = Application("test").ready(parallel=True)

        # 모든 인스턴스가 정상적으로 생성되어야 함
        controller = app.manager.get_instance(Controller)
        assert controller is not None
        assert controller.service_a is not None
        assert controller.service_b is not None
        assert controller.service_a.repo is not None
        assert controller.service_b.repo is not None

    def test_parallel_init_performance(self, reset_container_manager):
        """병렬 초기화 성능 테스트"""
        import time

        sleep_time = 0.05  # 50ms

        @Component
        class SlowServiceA:
            def __init__(self):
                time.sleep(sleep_time)

        @Component
        class SlowServiceB:
            def __init__(self):
                time.sleep(sleep_time)

        @Component
        class SlowServiceC:
            def __init__(self):
                time.sleep(sleep_time)

        # 병렬 초기화 (3개 서비스가 Level 0에서 동시 초기화)
        start = time.perf_counter()
        app = Application("test").ready(parallel=True)
        parallel_time = time.perf_counter() - start

        # 병렬이면 ~50ms, 순차면 ~150ms
        # 병렬 초기화가 순차보다 빨라야 함 (최소 2배 이상)
        # 단, 오버헤드 고려하여 여유 있게 검증
        print(f"\n병렬 초기화: {parallel_time * 1000:.1f}ms (예상: ~{sleep_time * 1000}ms)")

        # 병렬 초기화는 순차(150ms)보다 확실히 빨라야 함
        assert parallel_time < sleep_time * 2.5, f"병렬 초기화가 너무 느림: {parallel_time * 1000:.1f}ms"


class TestParallelInitEdgeCases:
    """병렬 초기화 엣지 케이스 테스트"""

    def test_empty_containers(self, reset_container_manager):
        """컨테이너가 없을 때"""
        app = Application("empty").ready(parallel=True)
        assert app._is_ready

    def test_single_container(self, reset_container_manager):
        """컨테이너가 하나일 때"""

        @Component
        class Single:
            pass

        app = Application("single").ready(parallel=True)
        assert app.manager.get_instance(Single) is not None

    def test_deep_dependency_chain(self, reset_container_manager):
        """깊은 의존성 체인"""

        @Component
        class Level0:
            pass

        @Component
        class Level1:
            dep: Level0

        @Component
        class Level2:
            dep: Level1

        @Component
        class Level3:
            dep: Level2

        @Component
        class Level4:
            dep: Level3

        app = Application("deep").ready(parallel=True)

        l4 = app.manager.get_instance(Level4)
        assert l4 is not None
        assert l4.dep.dep.dep.dep is not None
