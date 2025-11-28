"""의존성 그래프 시각화 모듈"""

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bloom.core.container import Container, FactoryContainer
    from bloom.core.manager import ContainerManager


def generate_dependency_graph(
    manager: "ContainerManager",
    output_path: str | Path | None = None,
) -> str:
    """
    컨테이너 간의 의존성 그래프를 ASCII 아트로 생성

    Args:
        manager: ContainerManager 인스턴스
        output_path: 출력 파일 경로 (None이면 파일 저장하지 않음)

    Returns:
        str: 의존성 그래프 문자열

    Example:
        >>> from bloom.logging.graph import generate_dependency_graph
        >>> graph = generate_dependency_graph(app.manager, "dependency-graph.txt")
    """
    from bloom.core.container import FactoryContainer
    from bloom.core.container.element import OrderElement

    lines: list[str] = []

    # 헤더
    lines.append("=" * 80)
    lines.append("Bloom Framework - Dependency Graph")
    lines.append(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 80)
    lines.append("")

    # 모든 컨테이너 수집
    all_containers: list["Container"] = []
    for containers in manager.get_all_containers().values():
        all_containers.extend(containers)

    if not all_containers:
        lines.append("No containers registered.")
        result = "\n".join(lines)
        if output_path:
            Path(output_path).write_text(result, encoding="utf-8")
        return result

    # 타입별 그룹핑
    type_to_containers: dict[type, list["Container"]] = defaultdict(list)
    for container in all_containers:
        type_to_containers[container.target].append(container)

    # Factory Chain 식별
    factory_chains: dict[type, list["FactoryContainer"]] = {}
    for target_type, containers in type_to_containers.items():
        factories = [c for c in containers if isinstance(c, FactoryContainer)]
        if len(factories) >= 2:
            factory_chains[target_type] = factories

    # === 1. 요약 정보 ===
    lines.append("## Summary")
    lines.append("-" * 40)
    lines.append(f"Total Containers: {len(all_containers)}")
    lines.append(f"Unique Types: {len(type_to_containers)}")
    lines.append(f"Factory Chains: {len(factory_chains)}")
    lines.append("")

    # === 2. 타입별 컨테이너 목록 ===
    lines.append("## Containers by Type")
    lines.append("-" * 40)

    for target_type, containers in sorted(
        type_to_containers.items(), key=lambda x: x[0].__name__
    ):
        type_name = target_type.__name__

        if len(containers) == 1:
            container = containers[0]
            container_kind = _get_container_kind(container)
            lines.append(f"  {type_name} ({container_kind})")
        else:
            lines.append(f"  {type_name} (Factory Chain - {len(containers)} factories)")
            for container in containers:
                if isinstance(container, FactoryContainer):
                    method_name = container.factory_method.__name__
                    order = _get_order(container)
                    order_str = f" @Order({order})" if order is not None else ""
                    lines.append(f"    └─ {method_name}(){order_str}")
    lines.append("")

    # === 3. 의존성 그래프 ===
    lines.append("## Dependency Graph")
    lines.append("-" * 40)
    lines.append("")

    # 의존성 매핑 생성
    dep_graph: dict[type, set[type]] = defaultdict(set)
    for container in all_containers:
        for dep_type in container.get_dependencies():
            if dep_type in type_to_containers:
                dep_graph[container.target].add(dep_type)

    # === 3.1. 다중레벨 의존성 분석 ===
    multi_level_chains = _analyze_multi_level_dependencies(dep_graph, type_to_containers)

    # === 3.2. 다이아몬드 의존성 분석 ===
    diamond_patterns = _analyze_diamond_dependencies(dep_graph, type_to_containers)

    # 그래프 시각화
    visited: set[type] = set()

    def draw_tree(
        target_type: type, prefix: str = "", is_last: bool = True, depth: int = 0
    ) -> None:
        if depth > 10:  # 무한 재귀 방지
            return

        connector = "└── " if is_last else "├── "

        if depth == 0:
            lines.append(f"{target_type.__name__}")
        else:
            lines.append(f"{prefix}{connector}{target_type.__name__}")

        if target_type in visited:
            return
        visited.add(target_type)

        deps = sorted(dep_graph.get(target_type, set()), key=lambda x: x.__name__)
        for i, dep in enumerate(deps):
            is_last_dep = i == len(deps) - 1
            new_prefix = prefix + ("    " if is_last else "│   ")
            draw_tree(dep, new_prefix, is_last_dep, depth + 1)

    # 루트 노드 찾기 (다른 타입에 의존하지 않는 타입)
    all_types = set(type_to_containers.keys())
    dependent_types: set[type] = set()
    for deps in dep_graph.values():
        dependent_types.update(deps)

    root_types = all_types - dependent_types
    if not root_types:
        root_types = all_types  # 순환이 있으면 모두 루트로

    for root_type in sorted(root_types, key=lambda x: x.__name__):
        visited.clear()
        draw_tree(root_type)
        lines.append("")

    # === 4. Factory Chain 상세 ===
    if factory_chains:
        lines.append("## Factory Chains (Detailed)")
        lines.append("-" * 40)
        lines.append("")

        for target_type, factories in sorted(
            factory_chains.items(), key=lambda x: x[0].__name__
        ):
            lines.append(f"### {target_type.__name__} Chain")
            lines.append("")

            # Factory 정렬
            sorted_factories = _sort_factories(factories, target_type)

            # ASCII 체인 그리기
            chain_parts: list[tuple[str, list[str], int | None]] = []
            for factory in sorted_factories:
                method_name = factory.factory_method.__name__
                order = _get_order(factory)

                # 외부 의존성 확인
                external_deps = [
                    d.__name__
                    for d in factory.get_dependencies()
                    if d != target_type and d in type_to_containers
                ]

                if order is not None:
                    part = f"{method_name}()"
                else:
                    part = f"{method_name}()"

                chain_parts.append((part, external_deps, order))

            # 체인 그리기
            for i, (part, external_deps, order) in enumerate(chain_parts):
                order_str = f" @Order({order})" if order is not None else " [Creator]"

                if i == 0:
                    lines.append(f"  ┌─────────────────┐")
                    lines.append(f"  │ {part:<15} │{order_str}")
                    lines.append(f"  └────────┬────────┘")
                else:
                    lines.append(f"           │")
                    if external_deps:
                        for dep in external_deps:
                            lines.append(f"           │ ◀── {dep}")
                    lines.append(f"           ▼")
                    lines.append(f"  ┌─────────────────┐")
                    lines.append(f"  │ {part:<15} │{order_str}")
                    lines.append(f"  └────────┬────────┘")

            lines.append(f"           │")
            lines.append(f"           ▼")
            lines.append(f"      [{target_type.__name__}]")
            lines.append("")

    # === 5. 다중레벨 의존성 ===
    if multi_level_chains:
        lines.append("## Multi-Level Dependencies")
        lines.append("-" * 40)
        lines.append("")
        lines.append("Chains with 3+ levels of dependency depth:")
        lines.append("")

        for chain in multi_level_chains:
            depth = len(chain)
            chain_names = [t.__name__ for t in chain]
            lines.append(f"  [{depth} levels] {' → '.join(chain_names)}")
            
            # ASCII 시각화
            lines.append("")
            for i, t in enumerate(chain):
                indent = "    " * i
                if i == 0:
                    lines.append(f"  {t.__name__}")
                else:
                    lines.append(f"  {indent}└── {t.__name__}")
            lines.append("")

    # === 6. 다이아몬드 의존성 ===
    if diamond_patterns:
        lines.append("## Diamond Dependencies")
        lines.append("-" * 40)
        lines.append("")
        lines.append("Patterns where multiple paths lead to a common dependency:")
        lines.append("")

        for diamond in diamond_patterns:
            top = diamond["top"]
            left = diamond["left"]
            right = diamond["right"]
            bottom = diamond["bottom"]

            # 이름 길이에 따라 박스 크기 조정
            top_name = top.__name__
            left_name = left.__name__
            right_name = right.__name__
            bottom_name = bottom.__name__

            lines.append(f"  Diamond: {top_name} → ({left_name}, {right_name}) → {bottom_name}")
            lines.append("")
            lines.append(f"                 ┌──────────────┐")
            lines.append(f"                 │ {top_name:^12} │")
            lines.append(f"                 └──────┬───────┘")
            lines.append(f"              ┌─────────┴─────────┐")
            lines.append(f"              ▼                   ▼")
            lines.append(f"     ┌────────────────┐  ┌────────────────┐")
            lines.append(f"     │ {left_name:^14} │  │ {right_name:^14} │")
            lines.append(f"     └───────┬────────┘  └───────┬────────┘")
            lines.append(f"             └───────────┬───────┘")
            lines.append(f"                         ▼")
            lines.append(f"                ┌────────────────┐")
            lines.append(f"                │ {bottom_name:^14} │")
            lines.append(f"                └────────────────┘")
            lines.append("")

    # === 7. 의존성 매트릭스 ===
    lines.append("## Dependency Matrix")
    lines.append("-" * 40)
    lines.append("")

    sorted_types = sorted(type_to_containers.keys(), key=lambda x: x.__name__)
    max_name_len = max(len(t.__name__) for t in sorted_types) if sorted_types else 10

    # 헤더
    header = " " * (max_name_len + 2)
    for t in sorted_types:
        header += f" {t.__name__[0]}"
    lines.append(header)
    lines.append(" " * (max_name_len + 2) + "-" * (len(sorted_types) * 2))

    # 매트릭스
    for row_type in sorted_types:
        row = f"{row_type.__name__:<{max_name_len}} │"
        for col_type in sorted_types:
            if col_type in dep_graph.get(row_type, set()):
                row += " ●"
            else:
                row += " ·"
        lines.append(row)

    lines.append("")
    lines.append("Legend: ● = depends on, · = no dependency")
    lines.append("")

    # === 푸터 ===
    lines.append("=" * 80)
    lines.append("End of Dependency Graph")
    lines.append("=" * 80)

    result = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result


def _get_container_kind(container: "Container") -> str:
    """컨테이너 종류 반환"""
    from bloom.core.container import FactoryContainer, HandlerContainer

    if isinstance(container, FactoryContainer):
        return "Factory"
    elif isinstance(container, HandlerContainer):
        return "Handler"
    else:
        return "Component"


def _get_order(factory: "FactoryContainer") -> int | None:
    """Factory의 Order 값 반환"""
    from bloom.core.container.element import OrderElement

    order_elem = factory.get_element(OrderElement)
    if order_elem is not None:
        return order_elem.order
    return None


def _sort_factories(
    factories: list["FactoryContainer"], target_type: type
) -> list["FactoryContainer"]:
    """Factory Chain 내 순서 정렬"""
    from bloom.core.container.element import OrderElement

    def get_sort_key(factory: "FactoryContainer") -> tuple[int, int]:
        order_elem = factory.get_element(OrderElement)
        if order_elem is not None:
            return (1, order_elem.order)

        deps = factory.get_dependencies()
        if target_type in deps:
            return (0, 1000)  # Modifier
        else:
            return (0, -1000)  # Creator

    return sorted(factories, key=get_sort_key)


def _analyze_multi_level_dependencies(
    dep_graph: dict[type, set[type]],
    type_to_containers: dict[type, list["Container"]],
) -> list[list[type]]:
    """
    다중레벨 의존성 체인을 분석
    
    3단계 이상의 의존성 체인을 찾아서 반환합니다.
    예: Controller → Service → Repository → Database (4레벨)
    
    Returns:
        list[list[type]]: 각 체인은 최상위부터 최하위까지의 타입 리스트
    """
    chains: list[list[type]] = []
    
    def find_longest_chain(start_type: type, visited: set[type]) -> list[type]:
        """DFS로 가장 긴 체인 찾기"""
        if start_type in visited:
            return []
        
        visited.add(start_type)
        deps = dep_graph.get(start_type, set())
        
        if not deps:
            return [start_type]
        
        longest_sub_chain: list[type] = []
        for dep in deps:
            sub_chain = find_longest_chain(dep, visited.copy())
            if len(sub_chain) > len(longest_sub_chain):
                longest_sub_chain = sub_chain
        
        return [start_type] + longest_sub_chain
    
    # 각 타입에서 시작하는 가장 긴 체인 찾기
    all_types = set(type_to_containers.keys())
    
    # 루트 타입들 (다른 것에 의존되지 않는 타입)
    dependent_types: set[type] = set()
    for deps in dep_graph.values():
        dependent_types.update(deps)
    
    root_types = all_types - dependent_types
    if not root_types:
        root_types = all_types
    
    seen_chains: set[tuple[str, ...]] = set()
    
    for root_type in root_types:
        chain = find_longest_chain(root_type, set())
        if len(chain) >= 3:  # 3레벨 이상만
            chain_key = tuple(t.__name__ for t in chain)
            if chain_key not in seen_chains:
                seen_chains.add(chain_key)
                chains.append(chain)
    
    # 길이 역순 정렬 (가장 긴 체인 먼저)
    chains.sort(key=lambda x: -len(x))
    
    return chains


def _analyze_diamond_dependencies(
    dep_graph: dict[type, set[type]],
    type_to_containers: dict[type, list["Container"]],
) -> list[dict[str, type]]:
    """
    다이아몬드 의존성 패턴을 분석
    
    다이아몬드 패턴: A가 B와 C에 의존하고, B와 C가 모두 D에 의존
    
         A (top)
        / \\
       B   C (left, right)
        \\ /
         D (bottom)
    
    Returns:
        list[dict]: 각 다이아몬드의 top, left, right, bottom 타입
    """
    diamonds: list[dict[str, type]] = []
    seen_diamonds: set[tuple[str, str, str, str]] = set()
    
    for top_type, direct_deps in dep_graph.items():
        # top이 최소 2개 이상의 타입에 의존해야 함
        if len(direct_deps) < 2:
            continue
        
        # 각 직접 의존성의 의존성들을 수집
        dep_list = list(direct_deps)
        
        for i in range(len(dep_list)):
            for j in range(i + 1, len(dep_list)):
                left = dep_list[i]
                right = dep_list[j]
                
                left_deps = dep_graph.get(left, set())
                right_deps = dep_graph.get(right, set())
                
                # 공통 의존성 찾기
                common_deps = left_deps & right_deps
                
                for bottom in common_deps:
                    # 다이아몬드 키 생성 (정렬하여 중복 방지)
                    sorted_middle = tuple(sorted([left.__name__, right.__name__]))
                    diamond_key = (
                        top_type.__name__,
                        sorted_middle[0],
                        sorted_middle[1],
                        bottom.__name__,
                    )
                    
                    if diamond_key not in seen_diamonds:
                        seen_diamonds.add(diamond_key)
                        diamonds.append({
                            "top": top_type,
                            "left": left,
                            "right": right,
                            "bottom": bottom,
                        })
    
    return diamonds
