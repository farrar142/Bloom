"""Bloom 프레임워크 예외 클래스들"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .container import Container


class BloomException(Exception):
    """Bloom 프레임워크 기본 예외"""

    pass


class CircularDependencyError(BloomException):
    """순환 의존성 감지 예외

    순환 의존성이 발견되면 이 예외가 발생하며,
    관련된 컨테이너들의 정보와 의존성 그래프를 포함합니다.
    """

    def __init__(
        self,
        message: str,
        unresolved_containers: list[Any] | None = None,
        all_containers: list[Any] | None = None,
    ):
        super().__init__(message)
        self.unresolved_containers: list[Any] = unresolved_containers or []
        self.all_containers: list[Any] = all_containers or []
        self._graph_saved_path: str | None = None

    @property
    def graph_saved_path(self) -> str | None:
        """그래프가 저장된 파일 경로"""
        return self._graph_saved_path

    @graph_saved_path.setter
    def graph_saved_path(self, path: str) -> None:
        self._graph_saved_path = path

    def get_cycle_info(self) -> str:
        """순환 의존성 정보를 문자열로 반환"""
        if not self.unresolved_containers:
            return "No cycle information available"

        lines = ["Circular dependency detected among:"]
        for container in self.unresolved_containers:
            deps = container.get_dependencies()
            dep_names = [d.__name__ for d in deps]
            lines.append(f"  - {container.target.__name__} → {dep_names}")

        return "\n".join(lines)


class AmbiguousProviderError(BloomException):
    """Factory Chain에서 Ambiguous Provider 감지 예외

    동일 타입에 대해 여러 Creator가 있고 Modifier가 있는 경우 발생합니다.
    """

    def __init__(self, target_type: type, creators: list, modifiers: list):
        self.target_type = target_type
        self.creators = creators
        self.modifiers = modifiers

        creator_names = [
            f"{c.owner_type.__name__}.{c.factory_method.__name__}" for c in creators
        ]
        message = (
            f"Ambiguous Provider for {target_type.__name__}: "
            f"Found {len(creators)} creators ({creator_names}) with {len(modifiers)} modifiers. "
            f"Only one creator is allowed when modifiers exist."
        )
        super().__init__(message)
