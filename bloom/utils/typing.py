"""타입 관련 유틸리티 함수들"""

import inspect
from typing import Callable, Union, get_origin, get_args, get_type_hints
from types import UnionType, NoneType


def is_optional(param_type: type) -> bool:
    """타입이 Optional인지 확인 (T | None 또는 Optional[T])"""
    origin = get_origin(param_type)
    if origin is Union or origin is UnionType:
        args = get_args(param_type)
        return NoneType in args or type(None) in args
    return False


def unwrap_optional(param_type: type) -> type:
    """Optional[T]에서 T를 추출, Optional이 아니면 그대로 반환"""
    if not is_optional(param_type):
        return param_type

    args = get_args(param_type)
    # None이 아닌 첫 번째 타입 반환
    for arg in args:
        if arg is not NoneType and arg is not type(None):
            return arg
    return param_type


def extract_parameter_types(
    func: Callable,
    skip_first: int = 0,
) -> list[type]:
    """
    함수의 파라미터 타입 힌트들을 추출

    Args:
        func: 타입 힌트를 추출할 함수
        skip_first: 건너뛸 앞쪽 파라미터 개수 (예: self, fn 등)

    Returns:
        타입 힌트 리스트 (타입이 없는 파라미터는 제외)
    """
    try:
        sig = inspect.signature(func)
        params = list(sig.parameters.values())

        if len(params) <= skip_first:
            return []

        # 타입 힌트 가져오기
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

        result: list[type] = []
        for param in params[skip_first:]:
            param_type = hints.get(param.name)
            if param_type is not None and isinstance(param_type, type):
                result.append(param_type)
            elif param.annotation is not inspect.Parameter.empty:
                # get_type_hints 실패 시 직접 annotation 사용
                if isinstance(param.annotation, type):
                    result.append(param.annotation)

        return result
    except Exception:
        return []
