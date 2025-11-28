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
    lines = [
        "## Summary",
        "-" * 40,
        f"Total Containers: {data.total_containers}",
        f"Unique Types: {len(data.containers)}",
        f"Factory Chains: {len(data.factory_chains)}",
    ]

    # 순환 의존성 정보
    if data.cycle_types:
        lines.append(f"⚠️  Circular Dependencies: {len(data.cycle_types)} types involved")

    lines.append("")
    return lines


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
    """의존성 트리 렌더링 (Lazy 의존성은 점선으로 표시)"""
    lines = [
        "## Dependency Graph",
        "-" * 40,
        "",
        "Legend: ─── = direct dependency, ┄┄┄ = lazy dependency (deferred)",
        "",
    ]

    visited: set[str] = set()

    def draw_tree(
        type_name: str,
        prefix: str = "",
        is_last: bool = True,
        depth: int = 0,
        is_lazy: bool = False,
    ) -> None:
        if depth > 10:
            return

        # Lazy 의존성은 점선 스타일
        if is_lazy:
            connector = "└┄┄ " if is_last else "├┄┄ "
            lazy_marker = " (lazy)"
        else:
            connector = "└── " if is_last else "├── "
            lazy_marker = ""

        if depth == 0:
            lines.append(f"{type_name}")
        else:
            lines.append(f"{prefix}{connector}{type_name}{lazy_marker}")

        if type_name in visited:
            return
        visited.add(type_name)

        # 일반 의존성
        deps = sorted(data.dep_graph.get(type_name, set()))
        # Lazy 의존성
        lazy_deps = sorted(data.lazy_dep_graph.get(type_name, set()))

        all_deps = [(d, False) for d in deps] + [(d, True) for d in lazy_deps]

        for i, (dep, is_lazy_dep) in enumerate(all_deps):
            is_last_dep = i == len(all_deps) - 1
            new_prefix = prefix + ("    " if is_last else "│   ")
            draw_tree(dep, new_prefix, is_last_dep, depth + 1, is_lazy_dep)

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


def render_lazy_dependencies(data: GraphData) -> list[str]:
    """Lazy 의존성 관계 렌더링"""
    if not data.lazy_dep_graph:
        return []

    lines = [
        "## Lazy Dependencies (Deferred Loading)",
        "-" * 40,
        "",
        "Components using @Lazy for deferred initialization:",
        "(Breaks circular dependencies by deferring resolution)",
        "",
    ]

    for type_name in sorted(data.lazy_dep_graph.keys()):
        lazy_deps = sorted(data.lazy_dep_graph[type_name])
        if lazy_deps:
            lines.append(f"  {type_name}")
            for i, dep in enumerate(lazy_deps):
                is_last = i == len(lazy_deps) - 1
                connector = "└┄┄" if is_last else "├┄┄"
                lines.append(f"    {connector} {dep} (lazy)")
            lines.append("")

    return lines


def render_circular_dependencies(data: GraphData) -> list[str]:
    """순환 의존성 시각화"""
    if not data.cycle_types:
        return []

    lines = [
        "",
        "=" * 60,
        "⚠️  CIRCULAR DEPENDENCY DETECTED",
        "=" * 60,
        "",
        "The following components form a circular dependency chain:",
        "",
    ]

    # 순환에 포함된 컴포넌트들의 의존성 표시
    for type_name in sorted(data.cycle_types):
        info = data.containers.get(type_name)
        if info:
            deps = info.dependencies
            cycle_deps = [d for d in deps if d in data.cycle_types]
            other_deps = [d for d in deps if d not in data.cycle_types]

            lines.append(f"  🔄 {type_name}")
            if cycle_deps:
                lines.append(f"      └── Cycle deps: {', '.join(cycle_deps)}")
            if other_deps:
                lines.append(f"      └── Other deps: {', '.join(other_deps)}")
            lines.append("")

    # 순환 경로 시각화 시도
    cycle_path = _find_cycle_path(data)
    if cycle_path:
        lines.append("  Cycle path:")
        lines.append(f"    {' → '.join(cycle_path)} → (cycle back)")
        lines.append("")

    # 해결 방법 제안
    lines.extend([
        "-" * 60,
        "💡 How to resolve:",
        "",
        "  1. Use @Lazy to break the cycle:",
        "     ```python",
        "     @Component",
        "     class ServiceA:",
        "         service_b: Lazy[ServiceB]  # Deferred loading",
        "     ```",
        "",
        "  2. Extract common functionality to a third component",
        "",
        "  3. Reconsider the design - circular dependencies",
        "     often indicate a design issue",
        "",
        "=" * 60,
        "",
    ])

    return lines


def _find_cycle_path(data: GraphData) -> list[str]:
    """순환 경로 찾기 (DFS)"""
    if not data.cycle_types:
        return []

    # 첫 번째 순환 타입에서 시작
    start = sorted(data.cycle_types)[0]
    visited: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> bool:
        if node in visited:
            if node in path:
                # 순환 발견
                cycle_start = path.index(node)
                return True
            return False

        visited.add(node)
        path.append(node)

        info = data.containers.get(node)
        if info:
            for dep in info.dependencies:
                if dep in data.cycle_types:
                    if dfs(dep):
                        return True

        path.pop()
        return False

    dfs(start)
    return path if len(path) > 1 else []


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


def render_initialization_order(
    levels: list[tuple[int, list[str]]],
    waiting: dict[str, list[str]],
) -> list[str]:
    """초기화 순서 및 의존성 대기 관계 렌더링"""
    if not levels:
        return []

    # 박스 너비 상수
    OUTER_BOX_WIDTH = 58
    INNER_BOX_WIDTH = 48
    NAME_MAX_LEN = 18
    DEP_MAX_LEN = 22

    lines = [
        "## Initialization Order (Dependency Resolution)",
        "-" * 40,
        "",
        "Step-by-step initialization sequence:",
        "(Components in same group can be initialized in parallel)",
        "",
    ]

    max_level = max(level for level, _ in levels) if levels else 0
    step = 1

    for level, types in levels:
        # 단계 헤더 - 고정 너비
        if level == 0:
            header_text = f"Step {step}: Initialize base components (no deps)"
        else:
            header_text = f"Step {step}: Initialize after Step {step - 1} completes"

        lines.append(f"  ┌{'─' * OUTER_BOX_WIDTH}┐")
        lines.append(f"  │ {header_text:<{OUTER_BOX_WIDTH - 2}} │")
        lines.append(f"  └{'─' * OUTER_BOX_WIDTH}┘")

        # 병렬 그룹 시각화
        if len(types) > 1:
            group_header = f"Parallel Group ({len(types)} components)"
            lines.append(f"      ┌{'─' * INNER_BOX_WIDTH}┐")
            lines.append(f"      │ {group_header:<{INNER_BOX_WIDTH - 2}} │")
            lines.append(f"      ├{'─' * INNER_BOX_WIDTH}┤")

            for t in types:
                deps = waiting.get(t, [])
                abbrev_name = abbreviate_name(t, NAME_MAX_LEN)

                if deps:
                    # 의존성도 축약
                    abbrev_deps = [abbreviate_name(d, 10) for d in deps[:2]]
                    dep_str = ", ".join(abbrev_deps)
                    if len(deps) > 2:
                        dep_str += f" +{len(deps) - 2}"
                    # 의존성 문자열 길이 제한
                    if len(dep_str) > DEP_MAX_LEN:
                        dep_str = dep_str[: DEP_MAX_LEN - 1] + "…"
                    content = f"• {abbrev_name:<{NAME_MAX_LEN}} ← [{dep_str}]"
                else:
                    content = f"• {abbrev_name}"

                # 박스 내부 패딩
                lines.append(f"      │ {content:<{INNER_BOX_WIDTH - 2}} │")

            lines.append(f"      └{'─' * INNER_BOX_WIDTH}┘")
        else:
            # 단일 컴포넌트
            t = types[0]
            abbrev_t = abbreviate_name(t, 25)
            deps = waiting.get(t, [])
            if deps:
                abbrev_deps = [abbreviate_name(d, 12) for d in deps[:2]]
                dep_str = ", ".join(abbrev_deps)
                if len(deps) > 2:
                    dep_str += f" +{len(deps) - 2}"
                lines.append(f"      [ {abbrev_t} ] ← [{dep_str}]")
            else:
                lines.append(f"      [ {abbrev_t} ]")

        # 다음 단계로 화살표
        if level < max_level:
            lines.append("          │")
            lines.append("          ▼")

        lines.append("")
        step += 1

    # 완료 메시지
    total = sum(len(types) for _, types in levels)
    lines.append(
        f"  ✓ Initialization complete: {total} components in {len(levels)} steps"
    )
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
