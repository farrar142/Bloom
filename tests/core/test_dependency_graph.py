"""의존성 그래프 시각화 테스트"""

import tempfile
from pathlib import Path

import pytest

from bloom import Application, Component
from bloom.core.decorators import Factory
from bloom.log import generate_dependency_graph


class TestDependencyGraph:
    """의존성 그래프 생성 테스트"""

    def test_simple_dependency_graph(self):
        """간단한 의존성 그래프 생성"""

        @Component
        class Repository:
            pass

        @Component
        class Service:
            repository: Repository

        @Component
        class Controller:
            service: Service

        app = Application("test").ready()

        graph = generate_dependency_graph(app.manager)

        assert "Repository" in graph
        assert "Service" in graph
        assert "Controller" in graph
        assert "Dependency Graph" in graph

    def test_factory_chain_visualization(self):
        """Factory Chain 시각화"""

        class Counter:
            def __init__(self, value: int = 0):
                self.value = value

        @Component
        class CounterConfig:
            @Factory
            def create_counter(self) -> Counter:
                return Counter(0)

            @Factory
            def add_one(self, counter: Counter) -> Counter:
                counter.value += 1
                return counter

        app = Application("test").ready()

        graph = generate_dependency_graph(app.manager)

        assert "Counter" in graph
        assert "Factory Chain" in graph
        assert "create_counter" in graph
        assert "add_one" in graph

    def test_save_to_file(self):
        """파일로 저장"""

        @Component
        class SimpleService:
            pass

        app = Application("test").ready()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "graph.txt"
            graph = generate_dependency_graph(app.manager, output_path)

            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            assert content == graph
            assert "SimpleService" in content

    def test_dependency_matrix(self):
        """의존성 매트릭스 생성"""

        @Component
        class A:
            pass

        @Component
        class B:
            a: A

        @Component
        class C:
            a: A
            b: B

        app = Application("test").ready()

        graph = generate_dependency_graph(app.manager)

        assert "Dependency Matrix" in graph
        assert "●" in graph  # 의존성 있음
        assert "·" in graph  # 의존성 없음

    def test_diamond_dependency(self):
        """다이아몬드 의존성 시각화"""

        class Result:
            def __init__(self, values: list[str] | None = None):
                self.values = values or []

        @Component
        class Base:
            pass

        @Component
        class Left:
            base: Base

        @Component
        class Right:
            base: Base

        @Component
        class Top:
            left: Left
            right: Right

        @Component
        class ResultConfig:
            @Factory
            def create_result(self) -> Result:
                return Result()

            @Factory
            def add_from_left(self, result: Result, left: Left) -> Result:
                result.values.append("left")
                return result

            @Factory
            def add_from_right(self, result: Result, right: Right) -> Result:
                result.values.append("right")
                return result

        app = Application("test").ready()

        graph = generate_dependency_graph(app.manager)

        assert "Base" in graph
        assert "Left" in graph
        assert "Right" in graph
        assert "Top" in graph
        assert "Result" in graph
        assert "Factory Chain" in graph

    # def test_empty_manager(self):
    #     """빈 매니저"""
    #     app = Application("test")  # ready() 호출하지 않음

    #     graph = generate_dependency_graph(app.manager)

    #     assert "No containers registered" in graph
