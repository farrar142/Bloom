"""유틸리티 함수들"""

from collections import defaultdict
from typing import Protocol, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from .container import Container, FactoryContainer

from .exceptions import CircularDependencyError


class DependencySortable(Protocol):
    """의존성 정렬이 가능한 객체를 위한 프로토콜"""

    target: type

    def get_dependencies(self) -> list[type]: ...


T = TypeVar("T", bound=DependencySortable)


def topological_sort_with_order(items: list[T]) -> list[T]:
    """
    DependencySortable 객체들을 의존성 기반으로 토폴로지컬 정렬

    같은 타입을 가진 여러 컨테이너 (Factory Chain)가 있을 때:
    1. @Order가 있으면 Order 값으로 정렬
    2. @Order가 없으면 의존성 기반 (Creator → Modifier)

    개별 Factory 단위로 그래프를 구성하되, 같은 타입의 Factory들 사이에는
    내부 순서(Order/의존성)에 따른 명시적 엣지를 추가합니다.

    Args:
        items: sortable 객체 리스트

    Returns:
        의존성 순서대로 정렬된 리스트

    Raises:
        Exception: 순환 의존성이 감지된 경우
    """
    from .container import FactoryContainer
    from .container.element import OrderElement

    if not items:
        return []

    # 타입별로 그룹핑
    type_to_items: dict[type, list[T]] = defaultdict(list)
    for item in items:
        type_to_items[item.target].append(item)

    # 같은 타입 내에서 @Order 또는 의존성으로 정렬
    def get_intra_type_order(item: T, target_type: type) -> tuple[int, int]:
        """같은 타입 내에서의 순서 결정"""
        if isinstance(item, FactoryContainer):
            order_elem = item.get_element(OrderElement)
            if order_elem is not None:
                return (1, order_elem.order)

            # Order가 없으면 의존성 기반
            deps = item.get_dependencies()
            non_owner_deps = [d for d in deps if d != item.owner_cls]

            if target_type in non_owner_deps:
                # Modifier: 나중에 실행 (높은 값)
                return (0, 1000)
            else:
                # Creator: 먼저 실행 (낮은 값)
                return (0, -1000)
        return (0, 0)

    # 각 타입 그룹 내에서 정렬
    sorted_type_groups: dict[type, list[T]] = {}
    for target_type, group in type_to_items.items():
        sorted_group = sorted(group, key=lambda x: get_intra_type_order(x, target_type))
        sorted_type_groups[target_type] = sorted_group

    # === 개별 아이템 단위로 의존성 그래프 구축 ===
    item_ids = {id(item): item for item in items}
    in_degree: dict[int, int] = {id(item): 0 for item in items}
    graph: dict[int, list[int]] = defaultdict(list)  # item_id -> dependent item_ids

    # 중복 엣지 방지용
    edges_added: set[tuple[int, int]] = set()

    def add_edge(from_id: int, to_id: int) -> None:
        """중복 없이 엣지 추가"""
        if from_id == to_id:
            return
        edge = (from_id, to_id)
        if edge not in edges_added:
            edges_added.add(edge)
            graph[from_id].append(to_id)
            in_degree[to_id] += 1

    # 1. 같은 타입 내에서 순서대로 연결 (Factory Chain 내부 순서)
    for target_type, sorted_group in sorted_type_groups.items():
        for i in range(len(sorted_group) - 1):
            prev_id = id(sorted_group[i])
            next_id = id(sorted_group[i + 1])
            add_edge(prev_id, next_id)

    # 2. 외부 타입에 대한 의존성 연결
    # 핵심: Chain의 첫 번째 Factory(Creator)만 외부 연결의 대상
    # Modifier는 자기 타입 의존성을 가지므로 Chain 내부에서 순서가 정해짐
    for item in items:
        item_id = id(item)
        for dep_type in item.get_dependencies():
            # 자기 타입 의존성은 1번(Chain 내부)에서 처리됨 - 스킵
            if dep_type == item.target:
                continue

            # 의존하는 타입이 등록되어 있는지 확인
            if dep_type not in sorted_type_groups:
                continue

            dep_group = sorted_type_groups[dep_type]
            if not dep_group:
                continue

            # 의존 타입의 Chain에서 "자기 타입을 의존하지 않는 마지막 Factory"를 찾음
            # = Chain의 가장 마지막 Creator 또는 현재 item의 target을 의존하지 않는 Modifier
            #
            # 간단하게: Chain에서 현재 item.target을 의존하지 않는 Factory들 중 마지막
            eligible_deps = []
            for dep_item in dep_group:
                dep_deps = dep_item.get_dependencies()
                # 현재 아이템의 target 타입을 의존하지 않으면 eligible
                if item.target not in dep_deps:
                    eligible_deps.append(dep_item)

            if eligible_deps:
                # eligible한 Factory들 중 마지막 (Chain에서 가장 늦게 실행되는)
                last_eligible = eligible_deps[-1]
                add_edge(id(last_eligible), item_id)
            else:
                # 모두 item.target을 의존하면, Chain의 첫 번째에 연결
                # (순환 방지: 첫 번째는 Creator이므로 자기 타입 의존 없음)
                first_dep = dep_group[0]
                add_edge(id(first_dep), item_id)

    # 토폴로지 정렬 (아이템 단위)
    queue = [item_id for item_id, deg in in_degree.items() if deg == 0]
    sorted_items: list[T] = []

    while queue:
        # 결정적 순서를 위해 정렬 (타입명 + 메서드명)
        queue.sort(
            key=lambda x: (
                item_ids[x].target.__name__,
                (
                    getattr(item_ids[x], "factory_method", lambda: None).__name__
                    if hasattr(item_ids[x], "factory_method")
                    else ""
                ),
            )
        )
        current_id = queue.pop(0)
        sorted_items.append(item_ids[current_id])

        for neighbor_id in graph[current_id]:
            in_degree[neighbor_id] -= 1
            if in_degree[neighbor_id] == 0:
                queue.append(neighbor_id)

    # 사이클 감지
    if len(sorted_items) != len(items):
        unresolved = [item_ids[i] for i, deg in in_degree.items() if deg > 0]
        raise CircularDependencyError(
            f"Circular dependency detected among: {[c.target.__name__ for c in unresolved]}",
            unresolved_containers=unresolved,
            all_containers=items,
        )

    return sorted_items


# 기존 함수 호환성을 위한 별칭
def topological_sort(items: list[T]) -> list[T]:
    """DependencySortable 객체들을 의존성 기반으로 토폴로지컬 정렬

    같은 target 타입을 가진 여러 컨테이너 (예: 여러 Factory)를 지원합니다.

    Args:
        items: sortable 객체 리스트

    Returns:
        의존성 순서대로 정렬된 리스트

    Raises:
        Exception: 순환 의존성이 감지된 경우
    """
    return topological_sort_with_order(items)


def group_by_dependency_level(items: list[T]) -> list[list[T]]:
    """
    컨테이너들을 의존성 레벨별로 그룹화

    의존성 깊이가 같은 컨테이너들을 같은 레벨로 묶어 반환합니다.
    - Level 0: 의존성이 없는 컨테이너들
    - Level 1: Level 0의 컨테이너에만 의존하는 컨테이너들
    - Level N: Level N-1 이하의 컨테이너들에 의존하는 컨테이너들

    Args:
        items: container 리스트

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

    for item in items:
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
        unresolved_types = all_types - set(type_to_level.keys())
        unresolved = [item for item in items if item.target in unresolved_types]
        raise CircularDependencyError(
            f"Circular dependency detected among: {[t.__name__ for t in unresolved_types]}",
            unresolved_containers=unresolved,
            all_containers=items,
        )

    # 아이템들을 레벨별로 그룹화
    level_to_items: dict[int, list[T]] = defaultdict(list)
    for item in items:
        level = type_to_level[item.target]
        level_to_items[level].append(item)

    # 레벨 순서대로 리스트로 변환
    max_level = max(level_to_items.keys()) if level_to_items else -1
    return [level_to_items[level] for level in range(max_level + 1)]


class AmbiguousProviderError(Exception):
    """
    동일 타입을 생성하는 여러 Factory가 있고,
    그 타입을 주입받는 다른 Factory가 있어 모호한 경우 발생하는 에러
    """

    def __init__(
        self,
        target_type: type,
        conflicting_factories: list["FactoryContainer"],
        dependent_factory: "FactoryContainer",
    ):
        self.target_type = target_type
        self.conflicting_factories = conflicting_factories
        self.dependent_factory = dependent_factory

        factory_names = [f.factory_method.__name__ for f in conflicting_factories]
        message = (
            f"Ambiguous provider for type '{target_type.__name__}'.\n"
            f"Multiple factories produce this type: {factory_names}\n"
            f"Factory '{dependent_factory.factory_method.__name__}' requires "
            f"'{target_type.__name__}' as a dependency but cannot determine which provider to use.\n"
            f"This is an Ambiguous Provider Anti-pattern.\n"
            f"Solution: Use Factory Chain pattern where only ONE factory creates the initial instance, "
            f"and others modify it with @Order decorator."
        )
        super().__init__(message)


def detect_factory_chains(
    items: list["Container"],
) -> dict[type, list["FactoryContainer"]]:
    """
    동일 타입을 반환하는 Factory들을 감지하여 체인으로 그룹화

    Factory Chain: 동일 타입을 반환하는 여러 Factory
    - 의존성 없는 Factory: 최초 생성자 (Creator)
    - 해당 타입을 의존성으로 갖는 Factory: 수정자 (Modifier)

    Returns:
        타입 -> [factory_container] 매핑
    """
    from .container import FactoryContainer

    # 타입별 Factory 그룹핑
    type_to_factories: dict[type, list[FactoryContainer]] = defaultdict(list)

    for item in items:
        if isinstance(item, FactoryContainer):
            type_to_factories[item.target].append(item)

    # 2개 이상의 Factory가 동일 타입을 반환하는 경우만 반환
    return {t: fs for t, fs in type_to_factories.items() if len(fs) >= 2}


def validate_factory_chains(
    chains: dict[type, list["FactoryContainer"]],
) -> None:
    """
    Factory Chain의 유효성 검증

    Ambiguous Provider 패턴 감지:
    - 동일 타입을 생성하는 Creator가 2개 이상이고
    - 해당 타입을 의존성으로 갖는 Modifier가 있는 경우

    Raises:
        AmbiguousProviderError: 모호한 의존성이 감지된 경우
    """
    from .container import FactoryContainer

    for target_type, factories in chains.items():
        # Creator: 해당 타입을 의존성으로 갖지 않는 Factory
        # Modifier: 해당 타입을 의존성으로 갖는 Factory
        creators: list[FactoryContainer] = []
        modifiers: list[FactoryContainer] = []

        for factory in factories:
            deps = factory.get_dependencies()
            # owner_cls는 제외하고 확인
            non_owner_deps = [d for d in deps if d != factory.owner_cls]
            if target_type in non_owner_deps:
                modifiers.append(factory)
            else:
                creators.append(factory)

        # Creator가 2개 이상이고 Modifier가 있으면 Ambiguous
        if len(creators) >= 2 and modifiers:
            raise AmbiguousProviderError(
                target_type=target_type,
                conflicting_factories=creators,
                dependent_factory=modifiers[0],
            )


def sort_factory_chain(
    factories: list["FactoryContainer"],
    target_type: type,
) -> list["FactoryContainer"]:
    """
    Factory Chain 내에서 실행 순서 결정

    순서 결정 기준:
    1. @Order가 있으면 Order 값으로 정렬 (낮을수록 먼저)
    2. @Order가 없으면 의존성 그래프로 결정:
       - 해당 타입을 의존성으로 갖지 않는 Factory = Creator (먼저)
       - 해당 타입을 의존성으로 갖는 Factory = Modifier (나중)

    Returns:
        실행 순서대로 정렬된 Factory 리스트
    """
    from .container.element import OrderElement

    def get_order(factory: "FactoryContainer") -> tuple[int, int]:
        """
        (has_order, order_value or dependency_order) 튜플 반환
        has_order: Order가 없으면 0, 있으면 1
        order_value: Order 값 또는 의존성 기반 순서
        """
        # OrderElement 확인
        order_elem = factory.get_element(OrderElement)
        if order_elem is not None:
            return (1, order_elem.order)

        # Order가 없으면 의존성 기반
        deps = factory.get_dependencies()
        non_owner_deps = [d for d in deps if d != factory.owner_cls]

        if target_type in non_owner_deps:
            # Modifier: 나중에 실행 (높은 값)
            return (0, 1000)
        else:
            # Creator: 먼저 실행 (낮은 값)
            return (0, -1000)

    # 정렬: Order가 있는 것들끼리, 없는 것들끼리 각각 정렬
    return sorted(factories, key=lambda x: get_order(x))
