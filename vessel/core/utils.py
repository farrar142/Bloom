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
