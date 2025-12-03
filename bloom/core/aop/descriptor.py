"""
MethodDescriptor: 메서드에 붙은 인터셉터 정보를 저장
"""

from dataclasses import dataclass, field
from typing import Any, Callable
from collections.abc import Callable as CallableABC


# 메서드에 descriptor를 저장하기 위한 속성명
_METHOD_DESCRIPTOR_ATTR = "__bloom_method_descriptor__"


@dataclass
class InterceptorInfo:
    """개별 인터셉터 정보"""

    interceptor_type: (
        str  # "before", "after", "around", "after_returning", "after_throwing"
    )
    callback: Callable[..., Any] | None = None  # 콜백 함수
    order: int = 0  # 실행 순서

    # 추가 메타데이터 (각 데코레이터별 설정)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MethodDescriptor:
    """
    메서드에 대한 인터셉터/메타데이터 정보를 담는 디스크립터.

    데코레이터들이 이 객체에 정보를 추가하고,
    ComponentProxy가 이 정보를 읽어서 인터셉터 체인을 구성.
    """

    # 인터셉터 정보 목록
    interceptors: list[InterceptorInfo] = field(default_factory=list)

    # 메서드 레벨 메타데이터 (예: @GetMapping의 path, @EventListener의 event_type 등)
    metadata: dict[str, Any] = field(default_factory=dict)

    # 메서드 순서 (@Order)
    order: int = 0

    def add_interceptor(self, info: InterceptorInfo) -> None:
        """인터셉터 정보 추가"""
        self.interceptors.append(info)

    def get_interceptors_by_type(self, interceptor_type: str) -> list[InterceptorInfo]:
        """특정 타입의 인터셉터들 반환"""
        return [i for i in self.interceptors if i.interceptor_type == interceptor_type]

    def has_interceptor_type(self, interceptor_type: str) -> bool:
        """특정 타입의 인터셉터가 있는지 확인"""
        return any(i.interceptor_type == interceptor_type for i in self.interceptors)

    def set_metadata(self, key: str, value: Any) -> None:
        """메타데이터 설정"""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """메타데이터 조회"""
        return self.metadata.get(key, default)


def get_method_descriptor(method: CallableABC) -> MethodDescriptor | None:
    """메서드에서 MethodDescriptor 가져오기"""
    return getattr(method, _METHOD_DESCRIPTOR_ATTR, None)


def set_method_descriptor(method: CallableABC, descriptor: MethodDescriptor) -> None:
    """메서드에 MethodDescriptor 설정"""
    setattr(method, _METHOD_DESCRIPTOR_ATTR, descriptor)


def ensure_method_descriptor(method: CallableABC) -> MethodDescriptor:
    """메서드에 MethodDescriptor가 없으면 생성하여 반환"""
    descriptor = get_method_descriptor(method)
    if descriptor is None:
        descriptor = MethodDescriptor()
        set_method_descriptor(method, descriptor)
    return descriptor
