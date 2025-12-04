"""bloom.core.resolver - 의존성 해결 및 토폴로지 정렬"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, TYPE_CHECKING

from .exceptions import CircularDependencyError

if TYPE_CHECKING:
    from .container import Container
    from .manager import ContainerManager


class DependencyGraph:
    """의존성 그래프"""

    def __init__(self) -> None:
        # 노드 → 의존하는 노드들 (A → [B, C] = A가 B, C에 의존)
        self._edges: dict[type, set[type]] = defaultdict(set)
        # 모든 노드
        self._nodes: set[type] = set()

    def add_node(self, node: type) -> None:
        """노드 추가"""
        self._nodes.add(node)

    def add_edge(self, from_node: type, to_node: type) -> None:
        """
        의존성 추가.
        from_node가 to_node에 의존함.
        """
        self._nodes.add(from_node)
        self._nodes.add(to_node)
        self._edges[from_node].add(to_node)

    def get_dependencies(self, node: type) -> set[type]:
        """노드의 의존성 목록"""
        return self._edges.get(node, set())

    def get_all_nodes(self) -> set[type]:
        """모든 노드"""
        return self._nodes.copy()

    def detect_cycle(self) -> list[type] | None:
        """
        순환 의존성 감지.

        Returns:
            순환이 있으면 순환 경로, 없으면 None
        """
        # 색상: 0=미방문, 1=방문중, 2=완료
        color: dict[type, int] = {node: 0 for node in self._nodes}
        # 부모 추적 (순환 경로 재구성용)
        parent: dict[type, type | None] = {node: None for node in self._nodes}

        def dfs(node: type) -> list[type] | None:
            color[node] = 1  # 방문 중

            for neighbor in self._edges.get(node, set()):
                if neighbor not in color:
                    continue

                if color[neighbor] == 1:
                    # 순환 발견! 경로 재구성
                    cycle = [neighbor, node]
                    current = node
                    while (_current := parent.get(current)) and current != neighbor:
                        current = _current
                        cycle.append(current)
                    cycle.append(neighbor)
                    return list(reversed(cycle))

                if color[neighbor] == 0:
                    parent[neighbor] = node
                    result = dfs(neighbor)
                    if result:
                        return result

            color[node] = 2  # 완료
            return None

        for node in self._nodes:
            if color[node] == 0:
                result = dfs(node)
                if result:
                    return result

        return None

    def topological_sort(self) -> list[type]:
        """
        토폴로지 정렬 (Kahn's algorithm).
        의존성이 먼저 생성되어야 하는 순서로 정렬.

        Returns:
            정렬된 노드 리스트

        Raises:
            CircularDependencyError: 순환 의존성이 있을 때
        """
        # 순환 먼저 체크
        cycle = self.detect_cycle()
        if cycle:
            raise CircularDependencyError(cycle)

        # 진입 차수 계산
        in_degree: dict[type, int] = {node: 0 for node in self._nodes}
        for node in self._nodes:
            for dep in self._edges.get(node, set()):
                if dep in in_degree:
                    in_degree[node] += 1

        # 진입 차수 0인 노드들로 시작
        queue: list[type] = [node for node, degree in in_degree.items() if degree == 0]
        result: list[type] = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            # 이 노드를 의존하는 노드들의 진입 차수 감소
            for other in self._nodes:
                if node in self._edges.get(other, set()):
                    in_degree[other] -= 1
                    if in_degree[other] == 0:
                        queue.append(other)

        return result


class DependencyResolver:
    """
    의존성 해결기.

    ContainerManager의 모든 컨테이너를 분석하여
    의존성 그래프를 구축하고 토폴로지 정렬.
    """

    def __init__(self, manager: "ContainerManager") -> None:
        self._manager = manager
        self._graph: DependencyGraph | None = None

    def build_graph(self) -> DependencyGraph:
        """의존성 그래프 구축"""
        graph = DependencyGraph()

        containers = self._manager.get_all_containers()

        for container in containers:
            # 노드 추가
            graph.add_node(container.target)

            # 의존성 추가
            for dep in container.dependencies:
                dep_container = self._manager.get_container(dep.field_type)
                if dep_container:
                    graph.add_edge(container.target, dep.field_type)

            # @Factory 의존성도 추가
            if container.factory:
                for dep in container.factory.dependencies:
                    dep_container = self._manager.get_container(dep.field_type)
                    if dep_container:
                        graph.add_edge(container.target, dep.field_type)

        self._graph = graph
        return graph

    def topological_sort(self) -> list["Container[Any]"]:
        """
        토폴로지 정렬된 컨테이너 목록 반환.
        의존성이 먼저 생성되는 순서.
        """
        if self._graph is None:
            self.build_graph()

        assert self._graph is not None

        sorted_types = self._graph.topological_sort()

        # type → Container 변환
        result: list[Container[Any]] = []
        for t in sorted_types:
            container = self._manager.get_container(t)
            if container:
                result.append(container)

        return result

    def detect_circular_dependency(self) -> list[type] | None:
        """순환 의존성 감지"""
        if self._graph is None:
            self.build_graph()

        assert self._graph is not None
        return self._graph.detect_cycle()

    def get_dependency_order_for[T](self, cls: type[T]) -> list["Container[Any]"]:
        """
        특정 클래스의 의존성 생성 순서.
        해당 클래스와 모든 의존성을 포함.
        """
        if self._graph is None:
            self.build_graph()

        assert self._graph is not None

        # BFS로 모든 의존성 수집
        visited: set[type] = set()
        queue: list[type] = [cls]
        dependencies: set[type] = set()

        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            dependencies.add(node)

            for dep in self._graph.get_dependencies(node):
                if dep not in visited:
                    queue.append(dep)

        # 전체 토폴로지 정렬에서 해당 의존성만 필터링
        sorted_types = self._graph.topological_sort()
        result: list[Container[Any]] = []

        for t in sorted_types:
            if t in dependencies:
                container = self._manager.get_container(t)
                if container:
                    result.append(container)

        return result
