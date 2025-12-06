import re
from dataclasses import dataclass, field
from typing import Generic, TypeVar, Protocol, runtime_checkable


# =============================================================================
# Protocol Definition
# =============================================================================


@runtime_checkable
class PathIncluded(Protocol):
    """경로를 포함하는 객체를 위한 Protocol

    Route, MessageMapping 등이 이 프로토콜을 구현합니다.
    path 속성을 가진 모든 객체는 이 Protocol을 만족합니다.
    """

    path: str


# Type variable for PathTrie
T = TypeVar("T", bound=PathIncluded)


# =============================================================================
# Match Result
# =============================================================================


@dataclass
class TrieMatch(Generic[T]):
    """Trie 매칭 결과"""

    item: T
    path_params: dict[str, str] = field(default_factory=dict)


# =============================================================================
# Trie Node
# =============================================================================


@dataclass
class TrieNode(Generic[T]):
    """Trie 노드

    각 노드는 경로의 한 세그먼트를 나타냅니다.
    """

    # 정적 자식 노드 (segment -> node)
    children: dict[str, "TrieNode[T]"] = field(default_factory=dict)

    # 동적 파라미터 노드 (하나만 존재 가능)
    param_child: "TrieNode[T] | None" = None
    param_name: str | None = None
    param_type: str | None = None  # int, str, path, uuid, slug

    # wildcard 노드 (path 타입용 - 여러 세그먼트 매칭)
    wildcard_child: "TrieNode[T] | None" = None
    wildcard_name: str | None = None

    # 이 노드에서 끝나는 항목
    item: T | None = None

    # 원본 경로 패턴 (삽입 시 저장)
    path_pattern: str | None = None


# =============================================================================
# Type Pattern Matchers
# =============================================================================


# 타입별 정규식 패턴
TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "int": re.compile(r"^\d+$"),
    "uuid": re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    ),
    "slug": re.compile(r"^[a-zA-Z0-9_-]+$"),
}


def match_type(value: str, param_type: str | None) -> bool:
    """값이 지정된 타입과 매칭되는지 확인"""
    if param_type is None or param_type == "str":
        return True

    if param_type == "path":
        return True  # path는 항상 매칭 (별도 처리)

    pattern = TYPE_PATTERNS.get(param_type)
    if pattern:
        return bool(pattern.match(value))

    return True  # 알 수 없는 타입은 통과


# =============================================================================
# Path Trie
# =============================================================================


class PathTrie(Generic[T]):
    """경로 매칭을 위한 Trie 자료구조

    HTTP Route와 STOMP MessageMapping 모두에서 사용할 수 있습니다.

    특징:
    - O(k) 시간 복잡도 (k = 경로 세그먼트 수)
    - 정적 경로가 동적 경로보다 우선
    - 경로 파라미터 추출 지원
    - 타입 힌트 지원 ({id:int}, {path:path} 등)

    사용 예:
        trie: PathTrie[Route] = PathTrie()
        trie.insert(Route(path="/users/{id}"))

        result = trie.find("/users/123")
        if result:
            print(result.item)  # Route
            print(result.path_params)  # {"id": "123"}
    """

    def __init__(self) -> None:
        self._root: TrieNode[T] = TrieNode()

    def insert(self, item: T) -> None:
        """항목 삽입

        Args:
            item: path 속성을 가진 객체
        """
        path = item.path
        segments = self._normalize_path(path)
        node = self._root

        i = 0
        while i < len(segments):
            segment = segments[i]

            # 파라미터 세그먼트 확인 ({name} 또는 {name:type})
            param_match = re.match(r"^\{(\w+)(?::(\w+))?\}$", segment)

            if param_match:
                param_name = param_match.group(1)
                param_type = param_match.group(2) or "str"

                # path 타입은 wildcard로 처리
                if param_type == "path":
                    if node.wildcard_child is None:
                        node.wildcard_child = TrieNode()
                    node.wildcard_name = param_name
                    node = node.wildcard_child
                    # path 타입은 나머지 모든 세그먼트를 소비
                    break
                else:
                    # 일반 파라미터
                    if node.param_child is None:
                        node.param_child = TrieNode()
                    node.param_name = param_name
                    node.param_type = param_type
                    node = node.param_child
            else:
                # 정적 세그먼트
                if segment not in node.children:
                    node.children[segment] = TrieNode()
                node = node.children[segment]

            i += 1

        # 끝 노드에 항목 저장
        node.item = item
        node.path_pattern = path

    def find(self, path: str) -> TrieMatch[T] | None:
        """경로 매칭

        Args:
            path: 매칭할 경로

        Returns:
            매칭 결과 또는 None
        """
        segments = self._normalize_path(path)
        return self._find_recursive(self._root, segments, 0, {})

    def _find_recursive(
        self,
        node: TrieNode[T],
        segments: list[str],
        index: int,
        params: dict[str, str],
    ) -> TrieMatch[T] | None:
        """재귀적 경로 매칭

        우선순위:
        1. 정적 매칭
        2. 파라미터 매칭
        3. Wildcard 매칭
        """
        # 모든 세그먼트를 소비한 경우
        if index >= len(segments):
            if node.item is not None:
                return TrieMatch(item=node.item, path_params=dict(params))
            return None

        segment = segments[index]

        # 1. 정적 매칭 시도 (최우선)
        if segment in node.children:
            result = self._find_recursive(
                node.children[segment], segments, index + 1, params
            )
            if result is not None:
                return result

        # 2. 파라미터 매칭 시도
        if node.param_child is not None and node.param_name is not None:
            # 타입 검사
            if match_type(segment, node.param_type):
                new_params = dict(params)
                new_params[node.param_name] = segment
                result = self._find_recursive(
                    node.param_child, segments, index + 1, new_params
                )
                if result is not None:
                    return result

        # 3. Wildcard 매칭 시도 (나머지 모든 세그먼트)
        if node.wildcard_child is not None and node.wildcard_name is not None:
            remaining = "/".join(segments[index:])
            new_params = dict(params)
            new_params[node.wildcard_name] = remaining

            # wildcard 노드에서 끝나야 함
            if node.wildcard_child.item is not None:
                return TrieMatch(item=node.wildcard_child.item, path_params=new_params)

        return None

    def remove(self, path: str) -> bool:
        """경로 삭제

        Args:
            path: 삭제할 경로 패턴 (삽입 시 사용한 패턴)

        Returns:
            삭제 성공 여부
        """
        segments = self._normalize_path(path)
        return self._remove_recursive(self._root, segments, 0)

    def _remove_recursive(
        self, node: TrieNode[T], segments: list[str], index: int
    ) -> bool:
        """재귀적 삭제"""
        if index >= len(segments):
            if node.item is not None:
                node.item = None
                node.path_pattern = None
                return True
            return False

        segment = segments[index]

        # 파라미터 세그먼트 확인
        param_match = re.match(r"^\{(\w+)(?::(\w+))?\}$", segment)

        if param_match:
            param_type = param_match.group(2) or "str"
            if param_type == "path":
                if node.wildcard_child is not None:
                    return self._remove_recursive(
                        node.wildcard_child, segments, len(segments)
                    )
            else:
                if node.param_child is not None:
                    return self._remove_recursive(node.param_child, segments, index + 1)
        else:
            if segment in node.children:
                return self._remove_recursive(
                    node.children[segment], segments, index + 1
                )

        return False

    def contains(self, path: str) -> bool:
        """경로 패턴 포함 여부

        Args:
            path: 확인할 경로 패턴 (삽입 시 사용한 패턴)

        Returns:
            포함 여부
        """
        segments = self._normalize_path(path)
        node = self._root

        for segment in segments:
            param_match = re.match(r"^\{(\w+)(?::(\w+))?\}$", segment)

            if param_match:
                param_type = param_match.group(2) or "str"
                if param_type == "path":
                    if node.wildcard_child is not None:
                        node = node.wildcard_child
                        break
                    return False
                else:
                    if node.param_child is None:
                        return False
                    node = node.param_child
            else:
                if segment not in node.children:
                    return False
                node = node.children[segment]

        return node.item is not None

    def get_all(self) -> list[T]:
        """모든 항목 조회

        Returns:
            저장된 모든 항목 목록
        """
        items: list[T] = []
        self._collect_items(self._root, items)
        return items

    def _collect_items(self, node: TrieNode[T], items: list[T]) -> None:
        """재귀적으로 모든 항목 수집"""
        if node.item is not None:
            items.append(node.item)

        # 정적 자식
        for child in node.children.values():
            self._collect_items(child, items)

        # 파라미터 자식
        if node.param_child is not None:
            self._collect_items(node.param_child, items)

        # Wildcard 자식
        if node.wildcard_child is not None:
            self._collect_items(node.wildcard_child, items)

    def _normalize_path(self, path: str) -> list[str]:
        """경로 정규화

        - 선행/후행 슬래시 제거
        - 빈 세그먼트 제거
        - 세그먼트 목록 반환
        """
        # 슬래시로 분할하고 빈 문자열 제거
        segments = [s for s in path.split("/") if s]
        return segments

    def __len__(self) -> int:
        """저장된 항목 수"""
        return len(self.get_all())

    def __repr__(self) -> str:
        items = self.get_all()
        paths = [item.path for item in items]
        return f"PathTrie({paths})"
