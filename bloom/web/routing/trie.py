"""Route Trie - Optimized route matching using Radix Tree structure"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .handler import HttpMethodHandler


class RouteNode:
    """
    Radix Tree의 노드

    각 노드는:
    - 정적 경로 세그먼트 (예: "users", "posts")
    - 동적 파라미터 (예: {id}, {name})
    - 핸들러 (리프 노드인 경우)
    를 저장합니다.
    """

    def __init__(self, segment: str = "", is_param: bool = False, param_name: str = ""):
        self.segment = segment  # 경로 세그먼트 (예: "users", "{id}")
        self.is_param = is_param  # 동적 파라미터 여부
        self.param_name = param_name  # 파라미터 이름 (is_param=True일 때)

        # 자식 노드들 (정적 경로)
        self.children: dict[str, RouteNode] = {}

        # 동적 파라미터 자식 (최대 1개)
        self.param_child: RouteNode | None = None

        # HTTP 메서드별 핸들러
        self.handlers: dict[str, "HttpMethodHandler"] = {}

    def __repr__(self) -> str:
        if self.is_param:
            return f"RouteNode({{{self.param_name}}})"
        return f"RouteNode({self.segment})"


class RouteTrie:
    """
    Radix Tree 기반 라우트 매칭

    특징:
    - 정적 경로: O(1) 해시맵 조회
    - 동적 파라미터: O(세그먼트 개수) 트리 순회
    - 우선순위: 정적 > 동적

    예시:
        /users -> 정적
        /users/{id} -> 동적
        /users/{id}/posts -> 동적 + 정적
    """

    def __init__(self):
        self.root = RouteNode()

    def insert(self, method: str, path: str, handler: "HttpMethodHandler") -> None:
        """
        경로를 Trie에 삽입

        Args:
            method: HTTP 메서드 (GET, POST 등)
            path: 경로 (예: /users/{id}/posts)
            handler: 핸들러 인스턴스
        """
        # 경로를 세그먼트로 분리 (빈 문자열 제거)
        segments = [s for s in path.split("/") if s]

        current = self.root

        for segment in segments:
            # 동적 파라미터인지 확인 ({id} 형식)
            if segment.startswith("{") and segment.endswith("}"):
                param_name = segment[1:-1]  # 중괄호 제거

                # 기존 동적 파라미터 자식이 있으면 사용
                if current.param_child:
                    current = current.param_child
                else:
                    # 새 동적 파라미터 노드 생성
                    node = RouteNode(segment, is_param=True, param_name=param_name)
                    current.param_child = node
                    current = node
            else:
                # 정적 세그먼트
                if segment not in current.children:
                    current.children[segment] = RouteNode(segment)
                current = current.children[segment]

        # 리프 노드에 핸들러 등록
        current.handlers[method] = handler

    def search(
        self, method: str, path: str
    ) -> tuple["HttpMethodHandler | None", dict[str, str]]:
        """
        경로에 맞는 핸들러 검색 (반복문 기반)

        Args:
            method: HTTP 메서드
            path: 요청 경로

        Returns:
            (핸들러, 경로 파라미터 딕셔너리)
        """
        # 경로를 세그먼트로 분리
        segments = [s for s in path.split("/") if s]

        if not segments:
            # 루트 경로
            handler = self.root.handlers.get(method)
            return (handler, {}) if handler else (None, {})

        # 스택 기반 탐색: (노드, 세그먼트 인덱스, 파라미터 딕셔너리)
        stack: list[tuple[RouteNode, int, dict[str, str]]] = [(self.root, 0, {})]
        segments_len = len(segments)

        while stack:
            node, idx, params = stack.pop()

            # 모든 세그먼트를 소진했으면 핸들러 확인
            if idx >= segments_len:
                handler = node.handlers.get(method)
                if handler:
                    return handler, params
                continue  # 핸들러 없으면 다음 후보 시도

            current_segment = segments[idx]
            next_idx = idx + 1

            # 동적 파라미터 먼저 스택에 (나중에 처리 = 정적보다 후순위)
            if node.param_child:
                new_params = params.copy()
                new_params[node.param_child.param_name] = current_segment
                stack.append((node.param_child, next_idx, new_params))

            # 정적 경로 스택에 (먼저 처리 = 높은 우선순위)
            if current_segment in node.children:
                stack.append((node.children[current_segment], next_idx, params))

        # 매칭 실패
        return None, {}

    def get_all_routes(self) -> list[tuple[str, str, "HttpMethodHandler"]]:
        """
        등록된 모든 라우트 반환 (디버깅용)

        Returns:
            [(메서드, 경로, 핸들러), ...]
        """
        routes = []
        self._collect_routes(self.root, "", routes)
        return routes

    def _collect_routes(
        self,
        node: RouteNode,
        current_path: str,
        routes: list[tuple[str, str, "HttpMethodHandler"]],
    ) -> None:
        """재귀적으로 모든 라우트 수집"""
        # 현재 노드에 핸들러가 있으면 추가
        for method, handler in node.handlers.items():
            path = current_path if current_path else "/"
            routes.append((method, path, handler))

        # 정적 자식 순회
        for segment, child in node.children.items():
            self._collect_routes(child, f"{current_path}/{segment}", routes)

        # 동적 파라미터 자식 순회
        if node.param_child:
            param_segment = f"{{{node.param_child.param_name}}}"
            self._collect_routes(
                node.param_child, f"{current_path}/{param_segment}", routes
            )
