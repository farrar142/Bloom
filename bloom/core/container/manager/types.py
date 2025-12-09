"""
Manager 모듈 공통 타입 정의
"""

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..base import Container

type COMPONENT_ID = str

# 전역 컨테이너 레지스트리
# { 등록된_타입(클래스/함수): { component_id: Container } }
containers = dict[type | Callable, dict[COMPONENT_ID, "Container"]]()


def get_container_registry() -> dict[type | Callable, dict[COMPONENT_ID, "Container"]]:
    """전역 컨테이너 레지스트리 조회"""
    return containers
