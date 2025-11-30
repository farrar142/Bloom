"""의존성 그래프 시각화 모듈 (ContainerManager 어댑터)"""

from pathlib import Path
from typing import TYPE_CHECKING

from bloom.utils.graph import (
    generate_graph,
    GraphData,
    ContainerInfo,
    FactoryInfo,
    ContainerKind,
)

if TYPE_CHECKING:
    from bloom.core.container import Container, FactoryContainer
    from bloom.core.exceptions import CircularDependencyError
    from bloom.core.manager import ContainerManager


def generate_dependency_graph(
    manager: "ContainerManager",
    output_path: str | Path | None = None,
    include_cycle_info: bool = False,
    cycle_error: "CircularDependencyError | None" = None,
) -> str:
    """
    컨테이너 간의 의존성 그래프를 ASCII 아트로 생성

    이 함수는 ContainerManager를 순수 GraphData로 변환한 후
    bloom.utils.graph.generate_graph를 호출합니다.

    Args:
        manager: ContainerManager 인스턴스
        output_path: 출력 파일 경로 (None이면 파일 저장하지 않음)
        include_cycle_info: 순환 의존성 정보 포함 여부
        cycle_error: CircularDependencyError 예외 객체 (순환 의존성 시)

    Returns:
        str: 의존성 그래프 문자열

    Example:
        >>> from bloom.log.graph import generate_dependency_graph
        >>> graph = generate_dependency_graph(app.manager, "dependency-graph.txt")
    """
    # ContainerManager -> GraphData 변환
    if cycle_error is not None and cycle_error.all_containers:
        # 순환 의존성 시: 예외에서 컨테이너 정보 추출
        data = _extract_graph_data_from_containers(
            cycle_error.all_containers,
            cycle_error.unresolved_containers,
        )
    else:
        data = _extract_graph_data(manager)

    # 순수 함수 호출
    return generate_graph(data, output_path)


def _extract_graph_data_from_containers(
    all_containers: list["Container"],
    unresolved_containers: list["Container"] | None = None,
) -> GraphData:
    """컨테이너 리스트에서 GraphData 추출 (순환 의존성 감지 시 사용)

    Args:
        all_containers: 모든 컨테이너 리스트
        unresolved_containers: 순환 의존성에 포함된 컨테이너들

    Returns:
        GraphData 객체
    """
    from bloom.core.container import FactoryContainer
    from bloom.core.container.element import OrderElement

    data = GraphData()

    if not all_containers:
        return data

    # 순환 의존성 컨테이너 타입 집합
    cycle_types = set()
    if unresolved_containers:
        cycle_types = {c.target for c in unresolved_containers}
        data.cycle_types = [t.__name__ for t in cycle_types]

    # 타입별 그룹핑
    type_to_containers: dict[type, list["Container"]] = {}
    for container in all_containers:
        if container.target not in type_to_containers:
            type_to_containers[container.target] = []
        type_to_containers[container.target].append(container)

    # 타입 이름 집합 (의존성 필터링용)
    valid_type_names = {t.__name__ for t in type_to_containers.keys()}

    # 각 타입에 대해 ContainerInfo 생성
    for target_type, containers in type_to_containers.items():
        type_name = target_type.__name__

        # 의존성 수집 (유효한 타입만)
        dependencies: set[str] = set()
        lazy_dependencies: set[str] = set()

        for container in containers:
            for dep_type in container.get_dependencies():
                dep_name = dep_type.__name__
                if dep_name in valid_type_names:
                    dependencies.add(dep_name)

            # Lazy 의존성 수집
            for dep_type in container.get_lazy_dependencies():
                dep_name = dep_type.__name__
                if dep_name in valid_type_names:
                    lazy_dependencies.add(dep_name)

        # Factory Chain 확인
        factories = [c for c in containers if isinstance(c, FactoryContainer)]

        if len(factories) >= 2:
            # Factory Chain
            sorted_factories = _sort_factories(factories, target_type)
            factory_infos = []

            for factory in sorted_factories:
                method_name = factory.factory_method.__name__
                order = _get_order(factory)

                # 외부 의존성 (자기 타입 제외)
                external_deps = [
                    d.__name__
                    for d in factory.get_dependencies()
                    if d != target_type and d.__name__ in valid_type_names
                ]

                factory_infos.append(
                    FactoryInfo(
                        method_name=method_name,
                        order=order,
                        external_deps=external_deps,
                    )
                )

            info = ContainerInfo(
                name=type_name,
                kind="Factory",
                dependencies=list(dependencies),
                lazy_dependencies=list(lazy_dependencies),
                factories=factory_infos,
                in_cycle=target_type in cycle_types,
            )
        else:
            # 단일 컨테이너
            container = containers[0]
            kind = _get_container_kind(container)

            info = ContainerInfo(
                name=type_name,
                kind=kind,
                dependencies=list(dependencies),
                lazy_dependencies=list(lazy_dependencies),
                in_cycle=target_type in cycle_types,
            )

        data.add_container(info)

    return data


def _extract_graph_data(manager: "ContainerManager") -> GraphData:
    """ContainerManager에서 GraphData 추출"""
    from bloom.core.container import FactoryContainer
    from bloom.core.container.element import OrderElement

    data = GraphData()

    # 모든 컨테이너 수집
    all_containers: list["Container"] = []
    for containers in manager.get_all_containers().values():
        all_containers.extend(containers)

    if not all_containers:
        return data

    # 타입별 그룹핑
    type_to_containers: dict[type, list["Container"]] = {}
    for container in all_containers:
        if container.target not in type_to_containers:
            type_to_containers[container.target] = []
        type_to_containers[container.target].append(container)

    # 타입 이름 집합 (의존성 필터링용)
    valid_type_names = {t.__name__ for t in type_to_containers.keys()}

    # 각 타입에 대해 ContainerInfo 생성
    for target_type, containers in type_to_containers.items():
        type_name = target_type.__name__

        # 의존성 수집 (유효한 타입만)
        dependencies: set[str] = set()
        lazy_dependencies: set[str] = set()

        for container in containers:
            for dep_type in container.get_dependencies():
                dep_name = dep_type.__name__
                if dep_name in valid_type_names:
                    dependencies.add(dep_name)

            # Lazy 의존성 수집
            for dep_type in container.get_lazy_dependencies():
                dep_name = dep_type.__name__
                if dep_name in valid_type_names:
                    lazy_dependencies.add(dep_name)

        # Factory Chain 확인
        factories = [c for c in containers if isinstance(c, FactoryContainer)]

        if len(factories) >= 2:
            # Factory Chain
            sorted_factories = _sort_factories(factories, target_type)
            factory_infos = []

            for factory in sorted_factories:
                method_name = factory.factory_method.__name__
                order = _get_order(factory)

                # 외부 의존성 (자기 타입 제외)
                external_deps = [
                    d.__name__
                    for d in factory.get_dependencies()
                    if d != target_type and d.__name__ in valid_type_names
                ]

                factory_infos.append(
                    FactoryInfo(
                        method_name=method_name,
                        order=order,
                        external_deps=external_deps,
                    )
                )

            info = ContainerInfo(
                name=type_name,
                kind="Factory",
                dependencies=list(dependencies),
                lazy_dependencies=list(lazy_dependencies),
                factories=factory_infos,
            )
        else:
            # 단일 컨테이너
            container = containers[0]
            kind = _get_container_kind(container)

            info = ContainerInfo(
                name=type_name,
                kind=kind,
                dependencies=list(dependencies),
                lazy_dependencies=list(lazy_dependencies),
            )

        data.add_container(info)

    return data


def _get_container_kind(container: "Container") -> ContainerKind:
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

    def get_sort_key(factory: "FactoryContainer") -> tuple[int, int]:
        order = _get_order(factory)
        if order is not None:
            return (1, order)

        deps = factory.get_dependencies()
        if target_type in deps:
            return (0, 1000)  # Modifier
        else:
            return (0, -1000)  # Creator

    return sorted(factories, key=get_sort_key)
