"""의존성 그래프 생성기 (순수 함수 기반)"""

from datetime import datetime
from pathlib import Path

from .types import GraphData, DiamondPattern
from .analyzer import (
    analyze_multi_level_dependencies,
    analyze_diamond_dependencies,
    analyze_initialization_order,
    analyze_waiting_dependencies,
)
from .renderer import (
    render_header,
    render_summary,
    render_containers_by_type,
    render_dependency_tree,
    render_factory_chains,
    render_lazy_dependencies,
    render_multi_level_chains,
    render_diamond_patterns,
    render_initialization_order,
    render_dependency_matrix,
    render_footer,
)


def generate_graph(
    data: GraphData,
    output_path: str | Path | None = None,
    title: str = "Dependency Graph",
) -> str:
    """
    의존성 그래프를 ASCII 아트로 생성 (순수 함수)

    Args:
        data: GraphData 인스턴스 (순수 데이터)
        output_path: 출력 파일 경로 (None이면 파일 저장하지 않음)
        title: 그래프 제목

    Returns:
        str: 의존성 그래프 문자열

    Example:
        >>> from bloom.utils.graph import generate_graph, GraphData, ContainerInfo
        >>> data = GraphData()
        >>> data.add_container(ContainerInfo(name="Service", kind="Component", dependencies=["Repository"]))
        >>> data.add_container(ContainerInfo(name="Repository", kind="Component", dependencies=[]))
        >>> graph = generate_graph(data)
    """
    lines: list[str] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 헤더
    lines.extend(render_header(title, timestamp))

    # 빈 데이터 체크
    if not data.containers:
        lines.append("No containers registered.")
        result = "\n".join(lines)
        if output_path:
            Path(output_path).write_text(result, encoding="utf-8")
        return result

    # 요약
    lines.extend(render_summary(data))

    # 타입별 컨테이너
    lines.extend(render_containers_by_type(data))

    # 의존성 트리
    lines.extend(render_dependency_tree(data))

    # Factory Chain 상세
    lines.extend(render_factory_chains(data))

    # Lazy 의존성
    lines.extend(render_lazy_dependencies(data))

    # 분석
    all_types = set(data.containers.keys())
    multi_level_chains = analyze_multi_level_dependencies(data.dep_graph, all_types)
    diamond_patterns = analyze_diamond_dependencies(data.dep_graph)
    init_order = analyze_initialization_order(data.dep_graph, all_types)
    waiting_deps = analyze_waiting_dependencies(data.dep_graph, all_types)

    # 다중레벨 의존성
    lines.extend(render_multi_level_chains(multi_level_chains))

    # 다이아몬드 의존성
    lines.extend(render_diamond_patterns(diamond_patterns))

    # 초기화 순서 및 의존성 대기
    lines.extend(render_initialization_order(init_order, waiting_deps))

    # 의존성 매트릭스
    lines.extend(render_dependency_matrix(data))

    # 푸터
    lines.extend(render_footer())

    result = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result
