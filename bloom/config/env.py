"""환경변수 주입 시스템

사용 예시:
    from bloom.config.env import Env, EnvStr, EnvInt

    @Component
    class Service:
        password: EnvStr[Literal["PASSWORD"]]  # str로 PASSWORD 환경변수 주입
        port: EnvInt[Literal["PORT"]]          # int로 PORT 환경변수 주입
        debug: EnvBool[Literal["DEBUG"]]       # bool로 DEBUG 환경변수 주입
"""

import os
from typing import Annotated, Any, Literal, TypeAliasType, get_origin, get_args


class Env[K]:
    """환경변수 마커 클래스

    K는 Literal["ENV_KEY"] 형태로 환경변수 키를 지정합니다.
    """

    pass


# 타입별 환경변수 alias
type EnvStr[K] = Annotated[str, Env[K]]
type EnvInt[K] = Annotated[int, Env[K]]
type EnvFloat[K] = Annotated[float, Env[K]]
type EnvBool[K] = Annotated[bool, Env[K]]


def _resolve_type_alias(hint: Any) -> Any:
    """TypeAliasType을 해석하여 실제 Annotated 타입으로 변환

    EnvStr[Literal["KEY"]] -> Annotated[str, Env[Literal["KEY"]]]
    """
    origin = getattr(hint, "__origin__", None)

    # TypeAliasType인 경우 (EnvStr, EnvInt 등)
    if isinstance(origin, TypeAliasType):
        # __value__: Annotated[str, Env[K]] 형태
        template = getattr(origin, "__value__", None)
        if template is None:
            return hint

        # hint의 __args__: (Literal["KEY"],) - K에 대입될 값
        type_args = getattr(hint, "__args__", ())
        if not type_args:
            return hint

        # template의 origin이 Annotated인지 확인
        if get_origin(template) is not Annotated:
            return hint

        # Annotated[str, Env[K]]에서 args 추출
        template_args = get_args(template)
        if len(template_args) < 2:
            return hint

        value_type = template_args[0]  # str, int 등
        env_marker_template = template_args[1]  # Env[K]

        # Env[K]를 Env[Literal["KEY"]]로 변환
        actual_key = type_args[0]  # Literal["KEY"]
        resolved_marker = Env[actual_key]

        # 새로운 Annotated 생성
        return Annotated[value_type, resolved_marker]

    return hint


def is_env_type(hint: Any) -> bool:
    """주어진 타입 힌트가 Env 타입인지 확인"""
    # TypeAliasType 해석
    resolved = _resolve_type_alias(hint)

    origin = get_origin(resolved)
    if origin is not Annotated:
        return False

    args = get_args(resolved)
    if len(args) < 2:
        return False

    # args[1]이 Env[K] 형태인지 확인
    marker = args[1]
    marker_origin = get_origin(marker)
    if marker_origin is Env:
        return True

    # Env 클래스 자체인 경우도 처리
    if isinstance(marker, type) and issubclass(marker, Env):
        return True

    return False


def resolve_env_value(hint: Any, default: Any = None) -> Any:
    """Env 타입에서 환경변수 값을 해석하여 반환

    Args:
        hint: EnvStr[Literal["KEY"]] 또는 Annotated[T, Env[Literal["KEY"]]] 형태의 타입 힌트
        default: 환경변수가 없을 때 기본값

    Returns:
        환경변수 값 (타입 변환됨)
    """
    # TypeAliasType 해석
    resolved = _resolve_type_alias(hint)

    origin = get_origin(resolved)
    if origin is not Annotated:
        return default

    args = get_args(resolved)
    if len(args) < 2:
        return default

    # args[0]: 실제 타입 (str, int, float, bool)
    # args[1]: Env[Literal["KEY"]]
    value_type = args[0]
    env_marker = args[1]

    # Env[Literal["KEY"]]에서 KEY 추출
    env_key = _extract_env_key(env_marker)
    if env_key is None:
        return default

    # 환경변수 조회
    env_value = os.environ.get(env_key)
    if env_value is None:
        return default

    # 타입 변환
    return _convert_value(env_value, value_type)


def _extract_env_key(env_marker: Any) -> str | None:
    """Env[Literal["KEY"]]에서 "KEY" 문자열 추출"""
    marker_origin = get_origin(env_marker)

    if marker_origin is Env:
        # Env[Literal["KEY"]] 형태
        marker_args = get_args(env_marker)
        if marker_args:
            literal_type = marker_args[0]
            # Literal["KEY"]에서 "KEY" 추출
            literal_args = get_args(literal_type)
            if literal_args:
                return literal_args[0]

    return None


def _convert_value(value: str, target_type: type) -> Any:
    """문자열 값을 대상 타입으로 변환"""
    if target_type is str:
        return value
    elif target_type is int:
        return int(value)
    elif target_type is float:
        return float(value)
    elif target_type is bool:
        return value.lower() in ("true", "1", "yes", "on")
    else:
        # 기본적으로 문자열 반환
        return value
