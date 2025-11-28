"""유틸리티 함수들"""

from collections import defaultdict
from typing import Protocol, TypeVar


class DependencySortable(Protocol):
    """의존성 정렬이 가능한 객체를 위한 프로토콜"""

    target: type

    def get_dependencies(self) -> list[type]: ...


T = TypeVar("T", bound=DependencySortable)


def topological_sort(items: list[tuple[str, T]]) -> list[tuple[str, T]]:
    """DependencySortable 객체들을 의존성 기반으로 토폴로지컬 정렬

    같은 target 타입을 가진 여러 컨테이너 (예: 여러 Handler)를 지원합니다.

    Args:
        items: (qualifier, sortable) 튜플 리스트

    Returns:
        의존성 순서대로 정렬된 (qualifier, sortable) 리스트

    Raises:
        Exception: 순환 의존성이 감지된 경우
    """
    # 고유 키: (target, qualifier) -> 아이템
    # 같은 타입의 여러 컨테이너를 구분
    item_key = lambda q, it: (it.target, q)
    key_to_item: dict[tuple[type, str], tuple[str, T]] = {}
    for qualifier, item in items:
        key_to_item[item_key(qualifier, item)] = (qualifier, item)

    # 타입별로 그룹핑 (의존성 해결용)
    type_to_keys: dict[type, list[tuple[type, str]]] = defaultdict(list)
    for qualifier, item in items:
        type_to_keys[item.target].append(item_key(qualifier, item))

    # 인접 리스트와 진입 차수 계산
    in_degree: dict[tuple[type, str], int] = defaultdict(int)
    graph: dict[type, list[tuple[type, str]]] = defaultdict(list)

    all_keys = set(key_to_item.keys())

    for key in all_keys:
        in_degree[key] = 0

    for qualifier, item in items:
        key = item_key(qualifier, item)
        dependencies = item.get_dependencies()
        for dep_type in dependencies:
            # 의존하는 타입이 등록되어 있으면 연결
            if dep_type in type_to_keys:
                graph[dep_type].append(key)
                in_degree[key] += 1

    # 진입 차수가 0인 노드들로 시작
    queue = [k for k in all_keys if in_degree[k] == 0]
    sorted_items: list[tuple[str, T]] = []
    visited_types: set[type] = set()

    while queue:
        current_key = queue.pop(0)
        current_type = current_key[0]

        if current_key in key_to_item:
            sorted_items.append(key_to_item[current_key])

        # 이 타입을 처음 방문할 때만 의존하는 컨테이너들의 진입 차수 감소
        if current_type not in visited_types:
            visited_types.add(current_type)
            for neighbor_key in graph[current_type]:
                in_degree[neighbor_key] -= 1
                if in_degree[neighbor_key] == 0:
                    queue.append(neighbor_key)

    # 사이클 감지
    if len(sorted_items) != len(items):
        raise Exception("Circular dependency detected")

    return sorted_items


def group_by_dependency_level(items: list[tuple[str, T]]) -> list[list[tuple[str, T]]]:
    """
    컨테이너들을 의존성 레벨별로 그룹화

    의존성 깊이가 같은 컨테이너들을 같은 레벨로 묶어 반환합니다.
    - Level 0: 의존성이 없는 컨테이너들
    - Level 1: Level 0의 컨테이너에만 의존하는 컨테이너들
    - Level N: Level N-1 이하의 컨테이너들에 의존하는 컨테이너들

    Args:
        items: (qualifier, container) 튜플 리스트

    Returns:
        레벨별로 그룹화된 리스트의 리스트

    Raises:
        Exception: 순환 의존성이 감지된 경우
    """
    if not items:
        return []

    # 타입별 레벨 매핑
    type_to_level: dict[type, int] = {}

    # 의존성 그래프 구축
    type_to_deps: dict[type, set[type]] = {}
    all_types: set[type] = set()

    for _, item in items:
        target = item.target
        all_types.add(target)
        deps = set(item.get_dependencies())
        # 등록된 타입들만 의존성으로 간주
        type_to_deps[target] = deps & all_types if deps else set()

    # BFS로 레벨 계산
    # Level 0: 의존성이 없는 타입들
    for target in all_types:
        if not type_to_deps.get(target):
            type_to_level[target] = 0

    # 나머지 타입들의 레벨 계산 (반복)
    changed = True
    max_iterations = len(all_types) + 1  # 순환 감지용
    iteration = 0

    while changed and iteration < max_iterations:
        changed = False
        iteration += 1
        for target in all_types:
            if target in type_to_level:
                continue
            deps = type_to_deps[target]
            # 모든 의존성의 레벨이 결정되었는지 확인
            if all(dep in type_to_level for dep in deps):
                type_to_level[target] = max(type_to_level[dep] for dep in deps) + 1
                changed = True

    # 레벨이 결정되지 않은 타입이 있으면 순환 의존성
    if len(type_to_level) != len(all_types):
        unresolved = all_types - set(type_to_level.keys())
        raise Exception(f"Circular dependency detected among: {unresolved}")

    # 아이템들을 레벨별로 그룹화
    level_to_items: dict[int, list[tuple[str, T]]] = defaultdict(list)
    for qualifier, item in items:
        level = type_to_level[item.target]
        level_to_items[level].append((qualifier, item))

    # 레벨 순서대로 리스트로 변환
    max_level = max(level_to_items.keys()) if level_to_items else -1
    return [level_to_items[level] for level in range(max_level + 1)]
