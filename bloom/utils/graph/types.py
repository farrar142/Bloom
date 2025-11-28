"""의존성 그래프 타입 정의"""

from dataclasses import dataclass, field
from typing import Literal


ContainerKind = Literal["Component", "Factory", "Handler"]


@dataclass
class FactoryInfo:
    """Factory 메서드 정보"""

    method_name: str
    order: int | None = None
    external_deps: list[str] = field(default_factory=list)


@dataclass
class ContainerInfo:
    """컨테이너 정보 (순수 데이터)"""

    name: str
    kind: ContainerKind
    dependencies: list[str] = field(default_factory=list)
    # Lazy 의존성 (순환 해결용 지연 로딩)
    lazy_dependencies: list[str] = field(default_factory=list)
    # Factory Chain인 경우
    factories: list[FactoryInfo] = field(default_factory=list)
    # 순환 의존성에 포함된 컨테이너인지
    in_cycle: bool = False

    @property
    def is_factory_chain(self) -> bool:
        return len(self.factories) >= 2

    @property
    def all_dependencies(self) -> list[str]:
        """모든 의존성 (일반 + Lazy)"""
        return self.dependencies + self.lazy_dependencies


@dataclass
class DiamondPattern:
    """다이아몬드 의존성 패턴"""

    top: str
    left: str
    right: str
    bottom: str


@dataclass
class GraphData:
    """그래프 생성에 필요한 순수 데이터"""

    # 타입 이름 -> 컨테이너 정보
    containers: dict[str, ContainerInfo] = field(default_factory=dict)

    # 의존성 그래프: 타입 이름 -> 의존하는 타입 이름들
    dep_graph: dict[str, set[str]] = field(default_factory=dict)

    # Lazy 의존성 그래프: 타입 이름 -> Lazy로 의존하는 타입 이름들
    lazy_dep_graph: dict[str, set[str]] = field(default_factory=dict)

    # 순환 의존성에 포함된 타입들
    cycle_types: list[str] = field(default_factory=list)

    def add_container(self, info: ContainerInfo) -> None:
        """컨테이너 추가"""
        self.containers[info.name] = info
        # 의존성 그래프에 추가
        if info.name not in self.dep_graph:
            self.dep_graph[info.name] = set()
        for dep in info.dependencies:
            self.dep_graph[info.name].add(dep)
        # Lazy 의존성 그래프에 추가
        if info.lazy_dependencies:
            if info.name not in self.lazy_dep_graph:
                self.lazy_dep_graph[info.name] = set()
            for dep in info.lazy_dependencies:
                self.lazy_dep_graph[info.name].add(dep)

    @property
    def total_containers(self) -> int:
        return len(self.containers)

    @property
    def factory_chains(self) -> dict[str, ContainerInfo]:
        return {
            name: info
            for name, info in self.containers.items()
            if info.is_factory_chain
        }

    def get_root_types(self) -> set[str]:
        """루트 타입들 반환 (다른 타입에 의존되지 않는 타입)"""
        all_types = set(self.containers.keys())
        dependent_types: set[str] = set()
        for deps in self.dep_graph.values():
            dependent_types.update(deps)
        root_types = all_types - dependent_types
        return root_types if root_types else all_types
