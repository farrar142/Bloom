"""의존성 분석 함수 (순수 함수)"""

from .types import GraphData, DiamondPattern


def analyze_multi_level_dependencies(
    dep_graph: dict[str, set[str]],
    all_types: set[str],
    min_depth: int = 3,
) -> list[list[str]]:
    """
    다중레벨 의존성 체인을 분석 (순수 함수)

    Args:
        dep_graph: 의존성 그래프 (타입 이름 -> 의존 타입 이름들)
        all_types: 모든 타입 이름 집합
        min_depth: 최소 깊이 (기본 3)

    Returns:
        list[list[str]]: 각 체인은 최상위부터 최하위까지의 타입 이름 리스트

    Example:
        >>> dep_graph = {"Controller": {"Service"}, "Service": {"Repository"}, "Repository": set()}
        >>> chains = analyze_multi_level_dependencies(dep_graph, {"Controller", "Service", "Repository"})
        >>> # [["Controller", "Service", "Repository"]]
    """
    chains: list[list[str]] = []

    def find_longest_chain(start_type: str, visited: set[str]) -> list[str]:
        """DFS로 가장 긴 체인 찾기"""
        if start_type in visited:
            return []

        visited.add(start_type)
        deps = dep_graph.get(start_type, set())

        if not deps:
            return [start_type]

        longest_sub_chain: list[str] = []
        for dep in deps:
            sub_chain = find_longest_chain(dep, visited.copy())
            if len(sub_chain) > len(longest_sub_chain):
                longest_sub_chain = sub_chain

        return [start_type] + longest_sub_chain

    # 루트 타입들 찾기
    dependent_types: set[str] = set()
    for deps in dep_graph.values():
        dependent_types.update(deps)

    root_types = all_types - dependent_types
    if not root_types:
        root_types = all_types

    seen_chains: set[tuple[str, ...]] = set()

    for root_type in root_types:
        chain = find_longest_chain(root_type, set())
        if len(chain) >= min_depth:
            chain_key = tuple(chain)
            if chain_key not in seen_chains:
                seen_chains.add(chain_key)
                chains.append(chain)

    # 길이 역순 정렬
    chains.sort(key=lambda x: -len(x))

    return chains


def analyze_diamond_dependencies(
    dep_graph: dict[str, set[str]],
) -> list[DiamondPattern]:
    """
    다이아몬드 의존성 패턴을 분석 (순수 함수)

    다이아몬드 패턴: A가 B와 C에 의존하고, B와 C가 모두 D에 의존

         A (top)
        / \\
       B   C (left, right)
        \\ /
         D (bottom)

    Args:
        dep_graph: 의존성 그래프 (타입 이름 -> 의존 타입 이름들)

    Returns:
        list[DiamondPattern]: 감지된 다이아몬드 패턴들
    """
    diamonds: list[DiamondPattern] = []
    seen_diamonds: set[tuple[str, str, str, str]] = set()

    for top_type, direct_deps in dep_graph.items():
        if len(direct_deps) < 2:
            continue

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
                    sorted_middle = tuple(sorted([left, right]))
                    diamond_key = (
                        top_type,
                        sorted_middle[0],
                        sorted_middle[1],
                        bottom,
                    )

                    if diamond_key not in seen_diamonds:
                        seen_diamonds.add(diamond_key)
                        diamonds.append(
                            DiamondPattern(
                                top=top_type,
                                left=left,
                                right=right,
                                bottom=bottom,
                            )
                        )

    return diamonds


def analyze_initialization_order(
    dep_graph: dict[str, set[str]],
    all_types: set[str],
) -> list[tuple[int, list[str]]]:
    """
    토폴로지 정렬로 초기화 순서 분석 (순수 함수)

    같은 레벨의 컴포넌트들은 병렬 초기화 가능

    Args:
        dep_graph: 의존성 그래프 (타입 이름 -> 의존 타입 이름들)
        all_types: 모든 타입 이름 집합

    Returns:
        list[tuple[int, list[str]]]: (레벨, 해당 레벨 타입들) 리스트
        레벨 0이 먼저 초기화, 레벨 1은 레벨 0 이후 초기화 가능...
    """
    # 역방향 그래프 (누가 나에게 의존하는가)
    reverse_graph: dict[str, set[str]] = {t: set() for t in all_types}
    for t, deps in dep_graph.items():
        for dep in deps:
            if dep in reverse_graph:
                reverse_graph[dep].add(t)

    # 진입 차수 계산 (내가 의존하는 타입 수)
    in_degree: dict[str, int] = {}
    for t in all_types:
        in_degree[t] = len(dep_graph.get(t, set()) & all_types)

    # Kahn's algorithm으로 레벨별 정렬
    levels: list[tuple[int, list[str]]] = []
    remaining = set(all_types)
    level = 0

    while remaining:
        # 진입 차수가 0인 노드들 (의존성이 모두 해결된 노드)
        ready = [t for t in remaining if in_degree.get(t, 0) == 0]

        if not ready:
            # 순환 의존성 - 남은 것들은 마지막 레벨로
            levels.append((level, sorted(remaining)))
            break

        levels.append((level, sorted(ready)))

        # 처리된 노드 제거 및 진입 차수 업데이트
        for t in ready:
            remaining.discard(t)
            # 나에게 의존하는 타입들의 진입 차수 감소
            for dependent in reverse_graph.get(t, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1

        level += 1

    return levels


def analyze_waiting_dependencies(
    dep_graph: dict[str, set[str]],
    all_types: set[str],
) -> dict[str, list[str]]:
    """
    각 타입이 초기화되기 위해 대기해야 하는 의존성 분석

    Args:
        dep_graph: 의존성 그래프
        all_types: 모든 타입 이름 집합

    Returns:
        dict[str, list[str]]: 타입 -> 대기해야 하는 의존성 리스트 (초기화 순서대로)
    """
    # 초기화 순서 계산
    levels = analyze_initialization_order(dep_graph, all_types)

    # 타입 -> 레벨 매핑
    type_to_level: dict[str, int] = {}
    for level, types in levels:
        for t in types:
            type_to_level[t] = level

    # 각 타입별로 대기해야 하는 의존성 (레벨 순서대로)
    waiting: dict[str, list[str]] = {}

    for t in all_types:
        deps = dep_graph.get(t, set()) & all_types
        if deps:
            # 의존성을 레벨 순으로 정렬 (먼저 초기화되어야 하는 순서)
            sorted_deps = sorted(deps, key=lambda d: (type_to_level.get(d, 0), d))
            waiting[t] = sorted_deps

    return waiting
