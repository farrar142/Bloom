"""ASCII 렌더링 함수 (순수 함수)"""

import re
from .types import GraphData, ContainerInfo, FactoryInfo, DiamondPattern


def abbreviate_name(name: str, max_length: int) -> str:
    """
    이름을 최대 길이에 맞게 축약

    축약 규칙:
    - 이미 max_length 이하면 그대로 반환
    - PascalCase: 각 단어 앞글자들을 조합 (ErrorHandlerContainer → ErHaCo, ErrHanCon)
    - snake_case: 각 부분 앞글자들 조합 (user_created_handler → UsCreHan)
    - 축약해도 길면 앞부분 + "…" 형태로 자름

    Args:
        name: 원본 이름
        max_length: 최대 길이

    Returns:
        축약된 이름

    Examples:
        >>> abbreviate_name("ErrorHandlerContainer", 12)
        'ErrHanCont'
        >>> abbreviate_name("UserController", 10)
        'UserContro'
    """
    if len(name) <= max_length:
        return name

    # PascalCase 감지: 대문자로 시작하는 단어들 분리
    words = re.findall(r"[A-Z][a-z]*", name)
    if len(words) >= 2:
        return _abbreviate_words(words, max_length)

    # snake_case 감지 (언더바 포함)
    if "_" in name:
        parts = [p.capitalize() for p in name.split("_") if p]
        if len(parts) >= 2:
            return _abbreviate_words(parts, max_length)

    # 기타: 앞부분만 자름
    return name[: max_length - 1] + "…"


def _abbreviate_words(words: list[str], max_length: int) -> str:
    """
    단어 리스트를 max_length에 맞게 축약

    모든 단어를 포함하면서 각 단어에서 2-4글자씩 가져옴
    예: ["Error", "Handler", "Container"], max=12 → "ErrHndCont"
    예: ["User", "Updated", "Handler"], max=14 → "UserUpdaHand"
    예: ["Handler", "Container"], max=12 → "HandlContai"
    """
    if not words:
        return ""

    n_words = len(words)

    # 전체 단어 합쳐도 max_length 이하면 그대로
    full = "".join(words)
    if len(full) <= max_length:
        return full

    # 단어당 최대 4글자로 제한하여 모든 단어가 보이도록
    max_per_word = min(4, max_length // n_words + 1)

    # 각 단어에서 글자 가져오기
    result = []
    remaining = max_length

    for i, word in enumerate(words):
        words_left = n_words - i
        # 남은 단어들에 최소 1글자씩 배분할 공간 확보
        available = remaining - (words_left - 1)
        take = min(len(word), max_per_word, available)
        take = max(1, take)  # 최소 1글자
        result.append(word[:take])
        remaining -= take

    return "".join(result)

    return "".join(result)


def render_header(title: str, timestamp: str) -> list[str]:
    """헤더 렌더링"""
    return [
        "=" * 80,
        f"Bloom Framework - {title}",
        f"Generated at: {timestamp}",
        "=" * 80,
        "",
    ]


def render_summary(data: GraphData) -> list[str]:
    """요약 정보 렌더링"""
    return [
        "## Summary",
        "-" * 40,
        f"Total Containers: {data.total_containers}",
        f"Unique Types: {len(data.containers)}",
        f"Factory Chains: {len(data.factory_chains)}",
        "",
    ]


def render_containers_by_type(data: GraphData) -> list[str]:
    """타입별 컨테이너 목록 렌더링"""
    lines = [
        "## Containers by Type",
        "-" * 40,
    ]

    for name in sorted(data.containers.keys()):
        info = data.containers[name]

        if info.is_factory_chain:
            lines.append(f"  {name} (Factory Chain - {len(info.factories)} factories)")
            for factory in info.factories:
                order_str = (
                    f" @Order({factory.order})" if factory.order is not None else ""
                )
                lines.append(f"    └─ {factory.method_name}(){order_str}")
        else:
            lines.append(f"  {name} ({info.kind})")

    lines.append("")
    return lines


def render_dependency_tree(data: GraphData) -> list[str]:
    """의존성 트리 렌더링"""
    lines = [
        "## Dependency Graph",
        "-" * 40,
        "",
    ]

    visited: set[str] = set()

    def draw_tree(
        type_name: str, prefix: str = "", is_last: bool = True, depth: int = 0
    ) -> None:
        if depth > 10:
            return

        connector = "└── " if is_last else "├── "

        if depth == 0:
            lines.append(f"{type_name}")
        else:
            lines.append(f"{prefix}{connector}{type_name}")

        if type_name in visited:
            return
        visited.add(type_name)

        deps = sorted(data.dep_graph.get(type_name, set()))
        for i, dep in enumerate(deps):
            is_last_dep = i == len(deps) - 1
            new_prefix = prefix + ("    " if is_last else "│   ")
            draw_tree(dep, new_prefix, is_last_dep, depth + 1)

    root_types = data.get_root_types()
    for root_type in sorted(root_types):
        visited.clear()
        draw_tree(root_type)
        lines.append("")

    return lines


def render_factory_chains(data: GraphData) -> list[str]:
    """Factory Chain 상세 렌더링"""
    chains = data.factory_chains
    if not chains:
        return []

    lines = [
        "## Factory Chains (Detailed)",
        "-" * 40,
        "",
    ]

    for name in sorted(chains.keys()):
        info = chains[name]
        lines.append(f"### {name} Chain")
        lines.append("")

        for i, factory in enumerate(info.factories):
            order_str = (
                f" @Order({factory.order})"
                if factory.order is not None
                else " [Creator]"
            )
            method_display = abbreviate_name(factory.method_name, 13) + "()"

            if i == 0:
                lines.append("  ┌─────────────────┐")
                lines.append(f"  │ {method_display:<15} │{order_str}")
                lines.append("  └────────┬────────┘")
            else:
                lines.append("           │")
                for dep in factory.external_deps:
                    lines.append(f"           │ ◀── {dep}")
                lines.append("           ▼")
                lines.append("  ┌─────────────────┐")
                lines.append(f"  │ {method_display:<15} │{order_str}")
                lines.append("  └────────┬────────┘")

        lines.append("           │")
        lines.append("           ▼")
        lines.append(f"      [{name}]")
        lines.append("")

    return lines


def render_multi_level_chains(chains: list[list[str]]) -> list[str]:
    """다중레벨 의존성 체인 렌더링"""
    if not chains:
        return []

    lines = [
        "## Multi-Level Dependencies",
        "-" * 40,
        "",
        "Chains with 3+ levels of dependency depth:",
        "",
    ]

    for chain in chains:
        depth = len(chain)
        lines.append(f"  [{depth} levels] {' → '.join(chain)}")
        lines.append("")

        for i, t in enumerate(chain):
            indent = "    " * i
            if i == 0:
                lines.append(f"  {t}")
            else:
                lines.append(f"  {indent}└── {t}")
        lines.append("")

    return lines


def render_diamond_patterns(patterns: list[DiamondPattern]) -> list[str]:
    """다이아몬드 의존성 패턴 렌더링"""
    if not patterns:
        return []

    lines = [
        "## Diamond Dependencies",
        "-" * 40,
        "",
        "Patterns where multiple paths lead to a common dependency:",
        "",
    ]

    for diamond in patterns:
        top = abbreviate_name(diamond.top, 12)
        left = abbreviate_name(diamond.left, 14)
        right = abbreviate_name(diamond.right, 14)
        bottom = abbreviate_name(diamond.bottom, 14)

        lines.append(
            f"  Diamond: {diamond.top} → ({diamond.left}, {diamond.right}) → {diamond.bottom}"
        )
        lines.append("")
        lines.append("                 ┌──────────────┐")
        lines.append(f"                 │ {top:^12} │")
        lines.append("                 └──────┬───────┘")
        lines.append("              ┌─────────┴─────────┐")
        lines.append("              ▼                   ▼")
        lines.append("     ┌────────────────┐  ┌────────────────┐")
        lines.append(f"     │ {left:^14} │  │ {right:^14} │")
        lines.append("     └───────┬────────┘  └───────┬────────┘")
        lines.append("             └───────────┬───────┘")
        lines.append("                         ▼")
        lines.append("                ┌────────────────┐")
        lines.append(f"                │ {bottom:^14} │")
        lines.append("                └────────────────┘")
        lines.append("")

    return lines


def render_dependency_matrix(data: GraphData) -> list[str]:
    """의존성 매트릭스 렌더링"""
    lines = [
        "## Dependency Matrix",
        "-" * 40,
        "",
    ]

    sorted_types = sorted(data.containers.keys())
    if not sorted_types:
        return lines

    max_name_len = max(len(t) for t in sorted_types)

    # 헤더
    header = " " * (max_name_len + 2)
    for t in sorted_types:
        header += f" {t[0]}"
    lines.append(header)
    lines.append(" " * (max_name_len + 2) + "-" * (len(sorted_types) * 2))

    # 매트릭스
    for row_type in sorted_types:
        row = f"{row_type:<{max_name_len}} │"
        for col_type in sorted_types:
            if col_type in data.dep_graph.get(row_type, set()):
                row += " ●"
            else:
                row += " ·"
        lines.append(row)

    lines.append("")
    lines.append("Legend: ● = depends on, · = no dependency")
    lines.append("")

    return lines


def render_footer() -> list[str]:
    """푸터 렌더링"""
    return [
        "=" * 80,
        "End of Dependency Graph",
        "=" * 80,
    ]
